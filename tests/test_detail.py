"""GET /api/v1/{universities,program-types,companies,skills}/{id} on a small made-up dataset."""
import datetime as dt

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from careers.models import Company, Field, Program, ProgramType, Skill, Source, University


@pytest.fixture(autouse=True)
def fresh_rate_limit():
    cache.clear()


@pytest.fixture
def d(db):
    src = Source.objects.create(name="Test data", url="https://example.org/data", licence="CC BY 4.0",
                                fetched_at=timezone.now())
    health = Field.objects.create(name="Health", name_tr="Sağlık", isced_code="09", source=src)
    nursing = ProgramType.objects.create(name="Nursing", name_tr="Hemşirelik", field=health, source=src,
                                         aliases=["Nurse"], degree_terms=["Nursing Science"])
    med = ProgramType.objects.create(name="Medicine", name_tr="Tıp", source=src)
    zonguldak = University.objects.create(name="Zonguldak Üniversitesi", city="Zonguldak", kind="state", source=src,
                                          yok_code="Z1", aliases=["ZBEU"])
    cukurova = University.objects.create(name="Çukurova Üniversitesi", city="Adana", kind="state", source=src)
    Program.objects.create(university=zonguldak, program_type=nursing, name_tr="Hemşirelik", source=src, osym_code="1")
    Program.objects.create(university=zonguldak, program_type=med, name_tr="Tıp (İngilizce)", source=src)
    Program.objects.create(university=cukurova, program_type=nursing, name_tr="Hemşirelik", source=src)
    Program.objects.create(university=cukurova, program_type=nursing, name_tr="Hemşirelik (İÖ)", source=src)
    company = Company.objects.create(name="Clinic", sector="Health", ats_provider="lever", ats_board_token="clinic",
                                     last_fetched=dt.date(2026, 11, 20), source=src)
    skill = Skill.objects.create(name="Triage", name_tr="Triyaj", onet_hot=True, esco_uri="https://esco.example/1",
                                 aliases=["Triaging"], source=src)
    return {"src": src, "health": health, "nursing": nursing, "med": med, "zonguldak": zonguldak,
            "cukurova": cukurova, "company": company, "skill": skill}


def get(path):
    return Client().get("/api/v1/" + path)


def test_university(d):
    r = get(f"universities/{d['zonguldak'].pk}")
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["source"]["name"] == "Test data" and body["source"]["licence"] == "CC BY 4.0"
    del body["source"]
    assert body == {
        "id": d["zonguldak"].pk, "name": "Zonguldak Üniversitesi", "name_tr": "", "city": "Zonguldak", "kind": "state",
        "programs": [  # Turkish order: H < T
            {"program_type": {"id": d["nursing"].pk, "name": "Nursing", "name_tr": "Hemşirelik"}, "name_tr": "Hemşirelik"},
            {"program_type": {"id": d["med"].pk, "name": "Medicine", "name_tr": "Tıp"}, "name_tr": "Tıp (İngilizce)"},
        ]}


def test_program_type_lists_each_university_once_in_turkish_order(d):
    body = get(f"program-types/{d['nursing'].pk}").json()
    assert [u["name"] for u in body["universities"]] == ["Çukurova Üniversitesi", "Zonguldak Üniversitesi"]
    assert body["field"] == {"id": d["health"].pk, "name": "Health", "name_tr": "Sağlık"}
    assert get(f"program-types/{d['med'].pk}").json()["field"] is None


def test_company(d):
    body = get(f"companies/{d['company'].pk}").json()
    assert {k: v for k, v in body.items() if k != "source"} == {
        "id": d["company"].pk, "name": "Clinic", "sector": "Health", "last_fetched": "2026-11-20"}


def test_skill(d):
    body = get(f"skills/{d['skill'].pk}").json()
    assert {k: v for k, v in body.items() if k != "source"} == {
        "id": d["skill"].pk, "name": "Triage", "name_tr": "Triyaj", "onet_hot": True,
        "esco_uri": "https://esco.example/1"}


@pytest.mark.parametrize("path", ["universities/{zonguldak}", "program-types/{nursing}", "companies/{company}",
                                  "skills/{skill}"])
def test_internal_fields_stay_out(d, path):
    body = get(path.format(**{k: v.pk for k, v in d.items()})).json()
    assert not {"aliases", "degree_terms", "ats_provider", "ats_board_token", "yok_code", "osym_code"} & set(body)
    assert "osym_code" not in str(body)


@pytest.mark.parametrize("kind", ["universities", "program-types", "companies", "skills"])
@pytest.mark.parametrize("id_", ["999999", "0", "-1", "abc", "1.5", "99999999999999999999"])
def test_unknown_ids_are_404(d, kind, id_):
    assert get(f"{kind}/{id_}").status_code == 404


def test_queries_do_not_grow_with_programs(d):
    with CaptureQueriesContext(connection) as small:
        get(f"universities/{d['zonguldak'].pk}")
    for i in range(10):
        pt = ProgramType.objects.create(name=f"Type {i}", source=d["src"])
        Program.objects.create(university=d["zonguldak"], program_type=pt, name_tr=f"P {i}", source=d["src"])
    with CaptureQueriesContext(connection) as big:
        get(f"universities/{d['zonguldak'].pk}")
    assert len(big) == len(small)


def test_detail_paths_are_in_the_docs(db):
    paths = Client().get("/api/openapi.json").json()["paths"]
    assert {"/api/v1/universities/{id}", "/api/v1/program-types/{id}", "/api/v1/companies/{id}",
            "/api/v1/skills/{id}"} <= set(paths)


def test_university_programs_in_turkish_order(d):
    for name in ["Diş Hekimliği", "Çocuk Gelişimi"]:  # plain sorting puts Ç after D
        pt = ProgramType.objects.create(name=name, source=d["src"])
        Program.objects.create(university=d["cukurova"], program_type=pt, name_tr=name, source=d["src"])
    programs = get(f"universities/{d['cukurova'].pk}").json()["programs"]
    assert [p["name_tr"] for p in programs] == ["Çocuk Gelişimi", "Diş Hekimliği", "Hemşirelik", "Hemşirelik (İÖ)"]
