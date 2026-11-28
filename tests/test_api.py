"""POST /api/v1/recommendations and friends, on a small made-up dataset."""
import datetime as dt
import json

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from careers.models import Company, Field, JobPosting, Program, ProgramType, Skill, Source, University

URL = "/api/v1/recommendations"


@pytest.fixture(autouse=True)
def fresh_rate_limit():
    cache.clear()  # the rate limit counts in the cache, shared by every test in this process


@pytest.fixture
def d(db):
    src = Source.objects.create(name="Test data", fetched_at=timezone.now())
    health = Field.objects.create(name="Health", isced_code="09", source=src)
    law_f = Field.objects.create(name="Law", isced_code="04", source=src)
    med = ProgramType.objects.create(name="Medicine", field=health, source=src)
    uni = University.objects.create(name="Örnek", source=src)
    Program.objects.create(university=uni, program_type=med, name_tr="Tıp", source=src)
    company = Company.objects.create(name="Clinic", last_fetched=timezone.localdate(), source=src)
    skill = Skill.objects.create(name="Triage", source=src)
    posting = JobPosting.objects.create(company=company, external_id="1", title="Doctor", url="https://example.org",
                                        country="TR", first_seen=dt.date(2026, 11, 1), last_seen=timezone.localdate(),
                                        source=src)
    posting.program_types.add(med)
    posting.skills.add(skill)
    return {"university": uni.pk, "program_type": med.pk, "field": health.pk, "law": law_f.pk,
            "company": company.pk, "skill": skill.pk}


def post(body, client=None, **headers):
    return (client or Client()).post(URL, json.dumps(body) if not isinstance(body, str) else body,
                                     content_type="application/json", **headers)


@pytest.mark.parametrize("key, shown", [
    ("university", {"outcomes", "companies_hiring", "skills"}),
    ("program_type", {"outcomes", "companies_hiring", "skills", "universities"}),
    ("field", {"outcomes", "companies_hiring", "skills", "universities"}),
    ("company", {"companies_hiring", "programs_asked_for"}),
    ("skills", {"companies_hiring", "programs_asked_for"}),
])
def test_each_input_alone(d, key, shown):
    r = post({key: [d["skill"]] if key == "skills" else d[key]})
    assert r.status_code == 200, r.content
    sections = r.json()["sections"]
    assert {k for k, v in sections.items() if v is not None} == shown


def test_full_profile_matches_the_documented_schema(d):
    r = post({"program_type": d["program_type"], "company": d["company"], "skills": [d["skill"], d["skill"]]})
    assert r.status_code == 200, r.content
    body = r.json()
    hiring = body["sections"]["companies_hiring"]
    assert hiring["items"] == [{"company": {"id": d["company"], "name": "Clinic", "name_tr": ""}, "open_postings": 1}]
    assert hiring["evidence"]["as_of"] == timezone.localdate().isoformat()
    assert body["sections"]["skills"]["enough_data"] is False
    assert body["sections"]["universities"]["items"][0]["name"] == "Örnek"
    assert post({"program_type": d["program_type"], "company": d["company"], "skills": [d["skill"]]}).json() == body


def test_empty_scope_is_200_with_a_note(d):
    r = post({"university": d["university"], "field": d["law"]})
    assert r.status_code == 200 and r.json()["notes"]


@pytest.mark.parametrize("body, loc_end", [
    ({}, "profile"),
    ({"skills": []}, "profile"),
    ({"university": None, "program_type": None, "field": None, "company": None, "skills": None}, "profile"),
    ({"role": 1}, "role"),
    ({"univrsity": 1}, "univrsity"),
    ({"university": 999999}, "university"),
    ({"program_type": 999999}, "program_type"),
    ({"field": 999999}, "field"),
    ({"company": 999999}, "company"),
    ({"skills": ["SKILL", 999999]}, "skills"),
    ({"university": "ID_TEXT"}, "university"),  # a real id, but as text: only strict typing rejects it
    ({"university": "ID_FLOAT"}, "university"),
    ({"skills": ["SKILL_TEXT"]}, "skills"),
    ({"university": True}, "university"),
    ({"university": 0}, "university"),
    ({"university": -1}, "university"),
    ({"skills": "1"}, "skills"),
    ({"skills": list(range(1, 52))}, "skills"),
])
def test_bad_profiles_are_422_with_a_message(d, body, loc_end):
    swap = {"SKILL": d["skill"], "SKILL_TEXT": str(d["skill"]), "ID_TEXT": str(d["university"]),
            "ID_FLOAT": float(d["university"])}
    body = {k: [swap.get(s, s) for s in v] if isinstance(v, list) else swap.get(v, v) if isinstance(v, str) else v
            for k, v in body.items()}
    r = post(body)
    assert r.status_code == 422, r.content
    error = r.json()["detail"][0]
    assert error["msg"] and loc_end in [str(part) for part in error["loc"]]


@pytest.mark.parametrize("body", ["not json", "[1, 2]", ""])
def test_malformed_bodies_are_client_errors(d, body):
    assert post(body).status_code in (400, 422)


def test_only_post(d):
    assert Client().get(URL).status_code == 405


def test_csrf_is_checked(d):
    client = Client(enforce_csrf_checks=True)
    r = post({"company": d["company"]}, client)
    assert r.status_code == 403 and "X-CSRFToken" in r.json()["detail"]
    token = client.get("/api/v1/csrf").json()["csrf_token"]
    assert "csrftoken" in client.cookies
    assert post({"company": d["company"]}, client, HTTP_X_CSRFTOKEN=token).status_code == 200


def test_rate_limit_per_address_ignores_forged_forwarded_for(db):
    client = Client()
    for _ in range(60):
        assert client.get("/api/v1/csrf").status_code == 200
    r = client.get("/api/v1/csrf")
    assert r.status_code == 429 and int(r["Retry-After"]) > 0
    assert client.get("/api/v1/csrf", HTTP_X_FORWARDED_FOR="203.0.113.9").status_code == 429
    assert Client(REMOTE_ADDR="198.51.100.7").get("/api/v1/csrf").status_code == 200  # another client


def test_docs_and_schema_are_served(db):
    assert Client().get("/api/docs").status_code == 200
    schema = Client().get("/api/openapi.json").json()
    assert "/api/v1/recommendations" in schema["paths"]
    profile = schema["components"]["schemas"]["ProfileIn"]
    assert profile["additionalProperties"] is False and set(profile["properties"]) == {
        "university", "program_type", "field", "company", "skills"}
