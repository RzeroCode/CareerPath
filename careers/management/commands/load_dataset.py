"""Load a dataset file into the careers tables: the one way data from any collector gets in.

The file is JSON: a "source" object, then any of these lists (loaded in this order, so later rows can
refer to earlier ones by name):

  fields         isced_code*, name*, name_tr
  program_types  name*, name_tr, aliases, field (ISCED code or name)
  universities   name*, name_tr, aliases, city, kind (state|foundation), yok_code
  programs       university*, program_type*, name_tr*, osym_code
  skills         name*, name_tr, aliases, onet_hot
  companies      name*, aliases, sector
  outcomes       program_type or field (one)*, metric*, value*, year*, sample_size
  postings       company*, external_id*, title*, url*, first_seen*, last_seen*, location, country, description, skills

(* = required.) Rows refer to each other by code, name, Turkish name or alias, matched ignoring case and
Turkish accents. A row that matches an existing record updates it; otherwise it is added. Aliases only
accumulate (remove one in the admin), and a replaced name becomes an alias. Codes are never erased or
swapped through a name match. Every saved row is stamped with the file's source. A row with an unknown
key, a bad value or a reference that matches nothing (or more than one record) is rejected and reported;
the other rows are still saved, and the command exits with an error.
See tests/fixtures/dataset_example.json.
"""
import json
import unicodedata

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DataError, IntegrityError, transaction

from careers.models import Company, Field, JobPosting, OutcomeStat, Program, ProgramType, Skill, Source, University

SOURCE_KEYS = {"name", "licence", "url", "fetched_at", "refresh_days"}
BAD_VALUE = (DataError, ValueError, TypeError)  # what a wrong type or a NUL character raises below full_clean


class RowError(Exception):
    pass


def norm(text):
    """'İSTANBUL', 'Istanbul' and 'istanbul' all give 'istanbul'; 'Boğaziçi' gives 'bogazici'."""
    text = str(text).replace("ı", "i").replace("İ", "i")
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(text.casefold().split())


class Finder:
    """Finds records of one model by code or by any of their names."""
    AMBIGUOUS = object()

    def __init__(self, model, code_field=None):
        self.model, self.code_field, self.keys = model, code_field, {}
        for obj in model.objects.all():
            self.add(obj)

    def add(self, obj):
        names = [getattr(obj, "name", ""), getattr(obj, "name_tr", ""), *getattr(obj, "aliases", [])]
        for key in {norm(n) for n in names if n}:
            prev = self.keys.get(key)
            self.keys[key] = obj if prev is None or prev == obj else self.AMBIGUOUS

    def find(self, name=None, code=None):
        if code and self.code_field:
            obj = self.model.objects.filter(**{self.code_field: code}).first()
            if obj:
                return obj
        if name:
            obj = self.keys.get(norm(name))
            if obj is self.AMBIGUOUS:
                raise RowError(f"{name!r} matches more than one {self.model._meta.verbose_name}")
            return obj
        return None

    def get(self, ref):
        """A reference from another row: a code or a name that must match exactly one record."""
        obj = self.find(name=ref, code=ref)
        if obj is None:
            raise RowError(f"no {self.model._meta.verbose_name} matches {ref!r}")
        return obj


class Command(BaseCommand):
    help = "Load a dataset JSON file (format: see this command's source) into the careers tables. Re-runnable."

    def add_arguments(self, parser):
        parser.add_argument("path")

    def handle(self, path, **options):
        try:
            with open(path, encoding="utf-8-sig") as f:  # -sig: Windows tools add a byte order mark
                data = json.load(f)
        except (OSError, ValueError) as e:
            raise CommandError(f"Can't read {path}: {e}")
        if not isinstance(data, dict) or not isinstance(data.get("source"), dict):
            raise CommandError('The file must be a JSON object with a "source" object.')
        unknown = set(data) - {"source", *SECTIONS}
        if unknown:
            raise CommandError(f"Unknown sections: {', '.join(sorted(unknown))}")

        with transaction.atomic():
            self.source = self.load_source(data["source"])
            self.finders = {}
            report = []
            for section, (loader, allowed, required) in SECTIONS.items():
                rows = data.get(section, [])
                if not isinstance(rows, list):
                    raise CommandError(f'"{section}" must be a list')
                saved = 0
                for i, row in enumerate(rows):
                    try:
                        if not isinstance(row, dict):
                            raise RowError("not an object")
                        if extra := set(row) - allowed:
                            raise RowError(f"unknown keys: {', '.join(sorted(extra))}")
                        if missing := [k for k in required if row.get(k) is None or str(row[k]).strip() == ""]:
                            raise RowError(f"missing: {', '.join(missing)}")
                        with transaction.atomic():
                            loader(self, row)
                        saved += 1
                    except RowError as e:
                        report.append(f"{section}[{i}]: {e}")
                    except ValidationError as e:
                        report.append(f"{section}[{i}]: {'; '.join(_messages(e))}")
                    except IntegrityError as e:
                        report.append(f"{section}[{i}]: database refused it ({e})")
                    except BAD_VALUE as e:
                        report.append(f"{section}[{i}]: bad value ({e})")
                if rows:
                    self.stdout.write(f"{section}: {saved} saved, {len(rows) - saved} rejected")
        for line in report:
            self.stderr.write(f"Rejected {line}")
        if report:  # raised after the commit: good rows stay, and scripts see a failing exit code
            raise CommandError(f"{len(report)} rows rejected; the others were saved.")

    def load_source(self, row):
        if extra := set(row) - SOURCE_KEYS:
            raise CommandError(f"Unknown source keys: {', '.join(sorted(extra))}")
        if not row.get("name"):
            raise CommandError("The source needs a name.")
        try:
            source = Source.objects.filter(name=row["name"]).first() or Source(name=row["name"])
            for k, v in row.items():
                setattr(source, k, v)
            source.full_clean()
            source.save()
        except ValidationError as e:
            raise CommandError(f"Bad source: {'; '.join(_messages(e))}")
        except BAD_VALUE as e:
            raise CommandError(f"Bad source: {e}")
        return source

    def finder(self, model, code_field=None):
        if model not in self.finders:
            self.finders[model] = Finder(model, code_field)
        return self.finders[model]

    def save(self, obj, row, skip=()):
        for k, v in row.items():
            if k not in skip:
                setattr(obj, k, v)
        obj.source = self.source
        obj.full_clean()
        obj.save()
        return obj

    def upsert_named(self, model, row, code_field=None, **refs):
        """Fields, program types, universities, skills and companies: matched by code, then by any name."""
        finder = self.finder(model, code_field)
        new_aliases = _as_list(row.get("aliases"))
        if not all(isinstance(a, str) and a.strip() for a in new_aliases):
            raise RowError("aliases must be a list of non-empty strings")
        names = [row.get("name"), row.get("name_tr"), *new_aliases]
        matches = {m for n in names if n if (m := finder.find(name=n)) is not None}
        code = row.get(code_field) if code_field else None
        by_code = finder.find(code=code) if code else None
        if by_code:
            matches.add(by_code)
        if len(matches) > 1:
            raise RowError(f"its code and names match {len(matches)} different records")
        # A fresh copy, so a rejected row leaves nothing on the cached one.
        obj = model.objects.get(pk=matches.pop().pk) if matches else model()
        if code and not by_code and obj.pk and getattr(obj, code_field) not in (None, "", str(code)):
            raise RowError(f"{obj.name!r} already has a different code ({getattr(obj, code_field)})")
        if code_field and not code:
            row = {k: v for k, v in row.items() if k != code_field}  # an empty code never erases one
        if obj.pk and hasattr(obj, "aliases"):
            replaced = [old for key in ("name", "name_tr")
                        if (old := getattr(obj, key, "")) and key in row and norm(old) != norm(row[key])]
            merged = {}
            for alias in [*obj.aliases, *new_aliases, *replaced]:
                merged.setdefault(norm(alias), alias)
            row = {**row, "aliases": list(merged.values())}
        obj = self.save(obj, {**row, **refs})
        finder.add(obj)
        return obj

    def load_field(self, row):
        self.upsert_named(Field, row, "isced_code")

    def load_program_type(self, row):
        refs = {"field": self.finder(Field, "isced_code").get(row["field"])} if row.get("field") else {}
        self.upsert_named(ProgramType, row, **refs)

    def load_university(self, row):
        self.upsert_named(University, row, "yok_code")

    def load_program(self, row):
        university = self.finder(University, "yok_code").get(row["university"])
        program_type = self.finder(ProgramType).get(row["program_type"])
        code = row.get("osym_code") or None
        obj = Program.objects.filter(osym_code=code).first() if code else None
        if obj is None:  # by university and name; with a new code, only a program that has none yet
            candidates = Program.objects.filter(university=university)
            if code:
                candidates = candidates.filter(osym_code__isnull=True)
            same = [p for p in candidates if norm(p.name_tr) == norm(row["name_tr"])]
            if len(same) > 1:
                raise RowError(f"matches {len(same)} programs; give its osym_code")
            obj = same[0] if same else Program()
        row = {k: v for k, v in row.items() if k != "osym_code"}
        if code:
            row["osym_code"] = code
        self.save(obj, {**row, "university": university, "program_type": program_type})

    def load_skill(self, row):
        self.upsert_named(Skill, row)

    def load_company(self, row):
        self.upsert_named(Company, row)

    def load_outcome(self, row):
        if bool(row.get("program_type")) == bool(row.get("field")):
            raise RowError("give exactly one of program_type and field")
        target = ({"program_type": self.finder(ProgramType).get(row["program_type"]), "field": None} if row.get("program_type")
                  else {"field": self.finder(Field, "isced_code").get(row["field"]), "program_type": None})
        obj = OutcomeStat.objects.filter(**target, metric=row["metric"], year=row["year"], source=self.source).first()
        self.save(obj or OutcomeStat(), {**row, **target})

    def load_posting(self, row):
        company = self.finder(Company).get(row["company"])
        skills = [self.finder(Skill).get(s) for s in _as_list(row.get("skills"))]
        obj = JobPosting.objects.filter(source=self.source, company=company, external_id=row["external_id"]).first()
        obj = self.save(obj or JobPosting(), {**row, "company": company}, skip={"skills"})
        if "skills" in row:
            obj.skills.set(skills)


def _as_list(value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise RowError("aliases and skills must be lists")
    return value


def _messages(error):
    if hasattr(error, "message_dict"):
        return [" ".join(v) if k == "__all__" else f"{k}: {' '.join(v)}" for k, v in error.message_dict.items()]
    return error.messages


SECTIONS = {  # section: (loader, allowed keys, required keys)
    "fields": (Command.load_field, {"isced_code", "name", "name_tr"}, ["isced_code", "name"]),
    "program_types": (Command.load_program_type, {"name", "name_tr", "aliases", "field"}, ["name"]),
    "universities": (Command.load_university, {"name", "name_tr", "aliases", "city", "kind", "yok_code"}, ["name"]),
    "programs": (Command.load_program, {"university", "program_type", "name_tr", "osym_code"}, ["university", "program_type", "name_tr"]),
    "skills": (Command.load_skill, {"name", "name_tr", "aliases", "onet_hot"}, ["name"]),
    "companies": (Command.load_company, {"name", "aliases", "sector"}, ["name"]),
    "outcomes": (Command.load_outcome, {"program_type", "field", "metric", "value", "year", "sample_size"}, ["metric", "value", "year"]),
    "postings": (Command.load_posting, {"company", "external_id", "title", "url", "first_seen", "last_seen", "location",
                                        "country", "description", "skills"}, ["company", "external_id", "title", "url", "first_seen", "last_seen"]),
}
