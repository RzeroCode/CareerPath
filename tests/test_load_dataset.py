import json
from pathlib import Path

import pytest
from django.apps import apps
from django.core.management import CommandError, call_command

from careers.management.commands.load_dataset import norm
from careers.models import Company, Field, JobPosting, OutcomeStat, Program, ProgramType, Skill, Source, University

EXAMPLE = Path(__file__).parent / "fixtures" / "dataset_example.json"
DATA_MODELS = [m for m in apps.get_app_config("careers").get_models() if m is not Source]


def load(tmp_path, data, capsys=None):
    path = tmp_path / "data.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    if capsys is None:
        call_command("load_dataset", str(path))
        return None
    capsys.readouterr()
    with pytest.raises(CommandError, match="rejected"):  # rejected rows must fail the command
        call_command("load_dataset", str(path))
    return capsys.readouterr().err


def example():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def counts():
    return {m.__name__: m.objects.count() for m in DATA_MODELS}


@pytest.mark.parametrize("a, b", [("İSTANBUL", "istanbul"), ("Istanbul", "istanbul"), ("Boğaziçi", "bogazici"),
                                  ("IŞIK", "isik"), ("  Tıp  (İngilizce) ", "tip (ingilizce)")])
def test_norm_ignores_case_and_turkish_accents(a, b):
    assert norm(a) == b


@pytest.mark.django_db
def test_example_loads_every_row_with_its_source(capsys):
    call_command("load_dataset", str(EXAMPLE))
    assert capsys.readouterr().err == ""
    assert counts() == {"University": 2, "Field": 1, "ProgramType": 2, "Program": 3, "Occupation": 0, "Skill": 2,
                        "Company": 1, "OutcomeStat": 2, "JobPosting": 1, "SkillDemandMonthly": 0}
    source = Source.objects.get(name="Example dataset")
    assert source.refresh_days == 30 and source.fetched_at is not None
    for model in DATA_MODELS:
        assert not model.objects.exclude(source=source).exists()
    assert Program.objects.get(name_tr="Tıp (İngilizce)").university.name == "Example Medical University"
    assert set(JobPosting.objects.get().skills.values_list("name", flat=True)) == {"Patient care", "Electronic health records"}
    assert OutcomeStat.objects.get(field__isnull=False).sample_size == 1200


@pytest.mark.django_db
def test_rerun_adds_nothing():
    call_command("load_dataset", str(EXAMPLE))
    before = counts()
    call_command("load_dataset", str(EXAMPLE))
    assert counts() == before


@pytest.mark.django_db
def test_row_matching_an_alias_updates_the_record(tmp_path):
    call_command("load_dataset", str(EXAMPLE))
    load(tmp_path, {"source": {"name": "Second source"},
                    "universities": [{"name": "EMU", "city": "Manisa"}],
                    "program_types": [{"name": "doctor of medicine", "aliases": ["Doctor of Medicine", "MD", "Hekimlik"]}]})
    uni = University.objects.get(name="EMU")  # the row's name wins; the old one stays as an alias
    assert uni.city == "Manisa" and uni.source.name == "Second source" and University.objects.count() == 2
    assert "Example Medical University" in uni.aliases
    load(tmp_path, {"source": {"name": "Third source"}, "universities": [{"name": "Example Medical University", "city": "İzmir"}]})
    assert University.objects.count() == 2
    assert {"Hekimlik", "Medicine"} <= set(ProgramType.objects.get(name_tr="Tıp").aliases)


@pytest.mark.django_db
def test_bad_rows_are_rejected_and_the_rest_saved(tmp_path, capsys):
    call_command("load_dataset", str(EXAMPLE))
    capsys.readouterr()
    err = load(tmp_path, {"source": {"name": "Example dataset"},
                          "companies": [{"name": "Good Co"}, {"name": "Typo Co", "secter": "x"}, {"sector": "no name"}],
                          "outcomes": [{"program_type": "Dentistry", "metric": "employment_rate", "value": 1, "year": 2025},
                                       {"program_type": "Medicine", "field": "09", "metric": "employment_rate", "value": 1, "year": 2025},
                                       {"program_type": "Medicine", "metric": "happiness", "value": 1, "year": 2025}],
                          "postings": [{"company": "Good Co", "external_id": "1", "title": "T", "url": "not a url",
                                        "first_seen": "2026-11-01", "last_seen": "2026-11-01"},
                                       {"company": "Good Co", "external_id": "3", "title": "T", "url": "https://example.org/3",
                                        "first_seen": "2026-11-02", "last_seen": "2026-11-01"},
                                       {"company": "Good Co", "external_id": "2", "title": "T", "url": "https://example.org/2",
                                        "first_seen": "2026-11-01", "last_seen": "2026-11-01", "skills": ["Surgery"]}]},
               capsys)
    assert Company.objects.filter(name="Good Co").exists() and Company.objects.count() == 2
    for expected in ["companies[1]: unknown keys: secter", "companies[2]: missing: name",
                     "outcomes[0]: no program type matches 'Dentistry'", "outcomes[1]: give exactly one",
                     "outcomes[2]: metric:", "postings[0]: url:", "postings[2]: no skill matches 'Surgery'", "postings[1]: Constraint"]:
        assert expected in err
    assert JobPosting.objects.count() == 1


@pytest.mark.django_db
def test_names_matching_two_records_are_rejected(tmp_path, capsys):
    call_command("load_dataset", str(EXAMPLE))
    err = load(tmp_path, {"source": {"name": "S"}, "universities": [{"name": "Example Medical University", "aliases": ["Sample Health University"]}]},
               capsys)
    assert "universities[0]: its code and names match 2 different records" in err


@pytest.mark.django_db
@pytest.mark.parametrize("data, message", [
    ("not json", "Can't read"),
    ([], 'must be a JSON object with a "source"'),
    ({"source": {}}, "needs a name"),
    ({"source": {"name": "S"}, "jobs": []}, "Unknown sections: jobs"),
    ({"source": {"name": "S", "fetched_at": "yesterday"}}, "Bad source"),
])
def test_bad_file_saves_nothing(tmp_path, data, message):
    path = tmp_path / "data.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    with pytest.raises(CommandError, match=message):
        call_command("load_dataset", str(path))
    assert not Source.objects.exists()


S = {"name": "S"}


def program(**extra):
    return {"source": S, "programs": [{"university": "EMU", "program_type": "Nursing", "name_tr": "Hemşirelik", **extra}]}


@pytest.fixture
def loaded(db):
    call_command("load_dataset", str(EXAMPLE))


def test_program_code_is_added_kept_and_never_duplicates(loaded, tmp_path):
    load(tmp_path, program(osym_code="222"))  # the example saved this program without a code
    assert Program.objects.count() == 3 and Program.objects.get(university__name="Example Medical University",
                                                                program_type__name="Nursing").osym_code == "222"
    load(tmp_path, program(name_tr="HEMSIRELIK"))  # no code, other spelling: same program, code stays
    assert Program.objects.count() == 3 and Program.objects.filter(osym_code="222").count() == 1


def test_program_row_matching_several_programs_is_rejected(loaded, tmp_path, capsys):
    load(tmp_path, program(osym_code="1"))
    load(tmp_path, {"source": S, "programs": [{"university": "EMU", "program_type": "Nursing", "name_tr": "Hemşirelik İÖ",
                                               "osym_code": "2"}]})
    Program.objects.filter(osym_code="2").update(name_tr="Hemşirelik")
    assert "matches 2 programs" in load(tmp_path, program(), capsys)


def test_aliases_are_merged_and_old_names_kept(loaded, tmp_path):
    load(tmp_path, {"source": S, "program_types": [{"name": "Medical Studies", "name_tr": "Tıp Bilimleri", "aliases": ["MD", "Hekimlik"]},
                                                  {"name": "MD", "aliases": ["Physician"]}]})
    # the second row finds the record through an alias the first row sent
    medicine = ProgramType.objects.get(field__isced_code="09", name="MD")
    assert {"Doctor of Medicine", "Medicine", "Tıp", "Medical Studies", "Hekimlik", "Physician"} <= set(medicine.aliases)
    assert ProgramType.objects.count() == 2


@pytest.mark.parametrize("section, row", [
    ("fields", {"isced_code": "0912", "name": "Health and Welfare"}),
    ("universities", {"name": "EMU", "yok_code": "3"}),
])
def test_new_code_on_a_name_with_another_code_is_rejected(loaded, tmp_path, capsys, section, row):
    University.objects.filter(name="Example Medical University").update(yok_code="1")
    assert "different code" in load(tmp_path, {"source": S, section: [row]}, capsys)
    assert Field.objects.get().isced_code == "09" and University.objects.get(name="Example Medical University").yok_code == "1"


@pytest.mark.parametrize("section, row", [
    ("companies", {"name": "Nul Co", "sector": "a\u0000b"}),
    ("outcomes", {"program_type": "Medicine", "metric": "employment_rate", "value": 1, "year": "abc"}),
    ("outcomes", {"program_type": "Medicine", "metric": "employment_rate", "value": 1, "year": [2025]}),
    ("companies", {"name": "   "}),
])
def test_odd_values_reject_only_their_row(loaded, tmp_path, capsys, section, row):
    data = {"source": S, section: [row], "skills": [{"name": "Still saved"}]}
    assert f"{section}[0]" in load(tmp_path, data, capsys)
    assert Skill.objects.filter(name="Still saved").exists()


def test_rejected_row_leaves_nothing_behind_for_later_rows(loaded, tmp_path, capsys):
    load(tmp_path, {"source": S, "universities": [{"name": "EMU", "city": "Wrongtown", "kind": "castle"},
                                                  {"name": "EMU"}]}, capsys)
    assert University.objects.get(name="EMU").city == "İzmir"


def test_outcomes_and_postings_update_in_place(loaded, tmp_path):
    data = example()
    data["outcomes"][0]["value"] = 80
    data["postings"][0].update(title="Senior Ward Nurse", skills=["EHR"])
    load(tmp_path, data)
    assert counts()["OutcomeStat"] == 2 and counts()["JobPosting"] == 1
    assert OutcomeStat.objects.get(program_type__isnull=False).value == 80
    posting = JobPosting.objects.get()
    assert posting.title == "Senior Ward Nurse" and posting.skills.count() == 1


@pytest.mark.parametrize("content, message", [
    (b"\xff\xfe not utf-8", "Can't read"),
    (b'{"source": {"name": "a\u0000b"}}', "Bad source"),
])
def test_unreadable_input_fails_cleanly(db, tmp_path, content, message):
    path = tmp_path / "data.json"
    path.write_bytes(content)
    with pytest.raises(CommandError, match=message):
        call_command("load_dataset", str(path))


def test_file_with_a_byte_order_mark_loads(db, tmp_path):
    path = tmp_path / "data.json"
    path.write_bytes(b"\xef\xbb\xbf" + EXAMPLE.read_bytes())
    call_command("load_dataset", str(path))
    assert University.objects.count() == 2
