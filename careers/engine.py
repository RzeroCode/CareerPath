"""Scoring engine v2 (plan Step 2): a profile in, sections with their evidence out.

Plain functions over the careers tables: no HTTP, no AI, and nothing tied to today's data. Every section says
where its numbers come from (sources, as_of = oldest fetch used, sample size).
"""
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timedelta
from fractions import Fraction

from django.db.models import Count, F, Q
from django.utils import timezone

from careers.matching import tr_key
from careers.models import OPEN_DAYS, Company, Field, JobPosting, OutcomeStat, Program, ProgramType, Skill, University

MIN_SCOPE_POSTINGS = 20  # skill ranking needs this many postings in scope...
MIN_SCOPE_COMPANIES = 3  # ...from this many companies...
MIN_SKILL_POSTINGS = 5  # ...and a skill needs this many of them
COUNTRY = "TR"  # "hiring now" means jobs in Turkey

ProgramLink = JobPosting.program_types.through
SkillLink = JobPosting.skills.through


class ProfileError(ValueError):
    """Bad input; `field` names the profile key at fault (None: the profile as a whole)."""

    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


@dataclass
class Profile:
    university: int | None = None
    program_type: int | None = None
    field: int | None = None
    company: int | None = None
    skills: list[int] = dc_field(default_factory=list)


def recommend(profile, today=None):
    today = today or timezone.localdate()
    university = _get(University, profile.university, "university")
    program_type = _get(ProgramType, profile.program_type, "program_type")
    field = _get(Field, profile.field, "field")
    company = _get(Company, profile.company, "company")
    skills = _get_skills(profile.skills)
    if not (university or program_type or field or company or skills):
        raise ProfileError(None, "Give at least one of university, program_type, field, company or skills.")

    education = university or program_type or field
    scope = _scope(university, program_type, field)  # None: no program filter
    notes, sections = [], {}
    if scope == []:
        given = ", ".join(o.name for o in (university, program_type, field) if o)
        notes.append(f"No program matches all of: {given}.")
    if education:
        sections["outcomes"] = _outcomes(scope)
    sections["companies_hiring"] = _companies_hiring(scope, company, skills, today)
    if education:
        sections["skills"] = _skills(scope, skills)
    if company or skills:
        sections["programs_asked_for"] = _programs_asked_for(scope, company, skills, today)
    if (program_type or field) and not university:
        sections["universities"] = _universities(scope)
    return {"notes": notes, "sections": sections}


# --- input --------------------------------------------------------------------------------------

def _get(model, pk, name):
    if pk is None:
        return None
    obj = model.objects.filter(pk=pk).first()
    if obj is None:
        raise ProfileError(name, f"No {model._meta.verbose_name} with id {pk}.")
    return obj


def _get_skills(ids):
    ids = list(dict.fromkeys(ids or []))
    found = {s.pk: s for s in Skill.objects.filter(pk__in=ids)}
    if missing := [i for i in ids if i not in found]:
        raise ProfileError("skills", f"No skill with id {', '.join(map(str, missing))}.")
    return [found[i] for i in ids]


def _scope(university, program_type, field):
    if not (university or program_type or field):
        return None
    types = ProgramType.objects.all()
    if university:
        types = types.filter(programs__university=university)
    if program_type:
        types = types.filter(pk=program_type.pk)
    if field:
        types = types.filter(field=field)
    return sorted(types.distinct(), key=lambda t: tr_key(t.name))


# --- shared helpers -----------------------------------------------------------------------------

def _ref(obj):
    return {"id": obj.pk, "name": obj.name, "name_tr": getattr(obj, "name_tr", "")}


def _in_scope(postings, scope):
    if scope is None:
        return postings
    return postings.filter(pk__in=ProgramLink.objects.filter(programtype__in=scope).values("jobposting_id"))


def _naming_any(postings, skills):
    if not skills:
        return postings
    return postings.filter(pk__in=SkillLink.objects.filter(skill__in=skills).values("jobposting_id"))


def _open_in_turkey(today):
    return JobPosting.objects.open(today).filter(country=COUNTRY)


def _evidence(sources, dates, sample_size):
    dates = [timezone.localdate(d) if isinstance(d, datetime) else d for d in dates if d]
    return {"sources": sorted(set(sources), key=tr_key), "as_of": min(dates, default=None), "sample_size": sample_size}


def _posting_evidence(postings, sample_size, dates=None):
    rows = list(postings.values_list("source__name", "source__fetched_at").distinct())
    return _evidence([r[0] for r in rows], dates if dates is not None else [r[1] for r in rows], sample_size)


# --- sections -----------------------------------------------------------------------------------

def _outcomes(scope):
    types = scope or []
    rows = (OutcomeStat.objects
            .filter(Q(program_type__in=types) | Q(field_id__in={t.field_id for t in types if t.field_id}))
            .select_related("source")
            .order_by("-year", F("source__fetched_at").desc(nulls_last=True), "-pk"))  # same year: fetched last
    latest = {}  # one query for every type and field; the first row per target and metric is the latest
    for row in rows:
        target = ("program_type", row.program_type_id) if row.program_type_id else ("field", row.field_id)
        latest.setdefault((*target, row.metric), row)
    items, used = [], []
    for pt in types:
        figures = []
        for metric in OutcomeStat.Metric:
            row, level = latest.get(("program_type", pt.pk, metric.value)), "program_type"
            if row is None and pt.field_id:
                row, level = latest.get(("field", pt.field_id, metric.value)), "field"
            if row is None:
                continue
            used.append(row)
            figures.append({
                "metric": metric.value, "label": metric.label, "value": float(row.value), "year": row.year,
                "level": level, "source": row.source.name, "sample_size": row.sample_size,
                "sample_size_note": "" if row.sample_size is not None else "not published",
            })
        items.append({"program_type": _ref(pt), "figures": figures})
    return {"items": items,
            "evidence": _evidence([r.source.name for r in used], [r.source.fetched_at for r in used], len(used))}


def _companies_hiring(scope, company, skills, today):
    postings = _naming_any(_in_scope(_open_in_turkey(today), scope), skills)
    if company:
        postings = postings.filter(company=company)
    rows = list(postings.values("company_id", "company__name", "company__last_fetched").annotate(n=Count("pk")))
    rows.sort(key=lambda r: (-r["n"], tr_key(r["company__name"])))
    tracked = Company.objects.filter(last_fetched__gte=today - timedelta(days=OPEN_DAYS)).count()
    return {
        "items": [{"company": {"id": r["company_id"], "name": r["company__name"]}, "open_postings": r["n"]} for r in rows],
        "companies_tracked": tracked,
        "evidence": _posting_evidence(postings, sum(r["n"] for r in rows), [r["company__last_fetched"] for r in rows]),
    }


def _skills(scope, held):
    """Lift: how much more often in-scope postings name a skill than all postings do. Global: every country,
    open or closed, since skills move slower than openings."""
    scoped = _in_scope(JobPosting.objects.all(), scope)  # scope is a list here: education was given
    scope_total = scoped.count()
    scope_companies = scoped.values("company").distinct().count()
    all_total = JobPosting.objects.count()
    section = {
        "scope_postings": scope_total, "scope_companies": scope_companies, "all_postings": all_total,
        "needs": {"postings": MIN_SCOPE_POSTINGS, "companies": MIN_SCOPE_COMPANIES, "per_skill": MIN_SKILL_POSTINGS},
        "scope_label": "global: postings from every country, open or closed",
        # Lift divides by all postings, so every posting's source is evidence.
        "evidence": _posting_evidence(JobPosting.objects.all(), scope_total),
    }
    if scope_total < MIN_SCOPE_POSTINGS or scope_companies < MIN_SCOPE_COMPANIES:
        return {**section, "enough_data": False, "items": []}

    counts = (SkillLink.objects.filter(jobposting__in=scoped).values("skill_id")
              .annotate(n=Count("jobposting_id", distinct=True)).filter(n__gte=MIN_SKILL_POSTINGS))
    mentions = {r["skill_id"]: r["n"] for r in counts}
    totals = dict(SkillLink.objects.filter(skill_id__in=mentions).values("skill_id")
                  .annotate(n=Count("jobposting_id", distinct=True)).values_list("skill_id", "n"))
    held_ids = {s.pk for s in held}
    ranked = []
    for skill in Skill.objects.filter(pk__in=mentions):
        lift = Fraction(mentions[skill.pk] * all_total, scope_total * totals[skill.pk])
        if lift > 1:
            ranked.append((lift, mentions[skill.pk], skill))
    ranked.sort(key=lambda r: (-r[0], -r[1], tr_key(r[2].name)))
    return {
        **section, "enough_data": True,
        "items": [{"skill": _ref(s), "lift": round(float(lift), 2), "mentions": n,
                   "share_in_scope": round(n / scope_total, 3), "held": s.pk in held_ids,
                   "onet_hot": s.onet_hot}  # badge source: O*NET (US)
                  for lift, n, s in ranked],
    }


def _programs_asked_for(scope, company, skills, today):
    postings = _naming_any(_open_in_turkey(today), skills)
    if company:
        postings = postings.filter(company=company)
    links = ProgramLink.objects.filter(jobposting__in=postings)
    if scope is not None:
        links = links.filter(programtype__in=scope)
    rows = list(links.values("programtype_id", "programtype__name", "programtype__name_tr")
                .annotate(n=Count("jobposting_id", distinct=True)))
    rows.sort(key=lambda r: (-r["n"], tr_key(r["programtype__name"])))
    counted = postings.filter(pk__in=links.values("jobposting_id"))  # only postings that name a program in scope
    return {
        "items": [{"program_type": {"id": r["programtype_id"], "name": r["programtype__name"],
                                    "name_tr": r["programtype__name_tr"]}, "open_postings": r["n"]} for r in rows],
        "evidence": _posting_evidence(counted, counted.count(),
                                      counted.values_list("company__last_fetched", flat=True).distinct()),
    }


def _universities(scope):
    universities = sorted(University.objects.filter(programs__program_type__in=scope).distinct(),
                          key=lambda u: tr_key(u.name))
    sources = list(Program.objects.filter(program_type__in=scope)
                   .values_list("source__name", "source__fetched_at").distinct())
    return {"items": [_ref(u) for u in universities],
            "evidence": _evidence([s[0] for s in sources], [s[1] for s in sources], len(universities))}
