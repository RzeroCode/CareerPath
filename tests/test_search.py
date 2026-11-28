"""GET /api/v1/search on a small made-up dataset."""
import pytest
from django.core.cache import cache
from django.test import Client

from careers.models import Company, Field, ProgramType, Skill, Source, University

URL = "/api/v1/search"


@pytest.fixture(autouse=True)
def fresh_rate_limit():
    cache.clear()


@pytest.fixture
def d(db):
    src = Source.objects.create(name="Test data")
    health = Field.objects.create(name="Health and welfare", name_tr="Sağlık", isced_code="09", source=src)
    for name in ["Boğaziçi Üniversitesi", "İstanbul Üniversitesi", "Işık Üniversitesi", "Hacettepe Üniversitesi",
                 "Ankara Üniversitesi", "Marmara Üniversitesi", "Çukurova Üniversitesi"]:
        University.objects.create(name=name, source=src)
    ProgramType.objects.create(name="Nursing", name_tr="Hemşirelik", field=health, source=src)
    Company.objects.create(name="Clinic Group", source=src)
    Skill.objects.create(name="Wound care", source=src)
    Skill.objects.create(name="Telemedicine", source=src)


def search(**params):
    return Client().get(URL, params)


def names(r, kind):
    assert r.status_code == 200, r.content
    return [x["name"] for x in r.json()["results"][kind]]


@pytest.mark.parametrize("q, expected", [
    ("bogazici", "Boğaziçi Üniversitesi"),
    ("BOĞAZİÇİ", "Boğaziçi Üniversitesi"),
    ("istanbul", "İstanbul Üniversitesi"),
    ("İSTANBUL", "İstanbul Üniversitesi"),
    ("ISTANBUL", "İstanbul Üniversitesi"),
    ("isik", "Işık Üniversitesi"),
    ("cukurova", "Çukurova Üniversitesi"),
])
def test_case_and_turkish_letters_are_ignored(d, q, expected):
    assert names(search(q=q, type="university"), "university") == [expected]


@pytest.mark.parametrize("q, kind, expected", [
    ("hemsire", "program_type", "Nursing"),  # only the Turkish name matches
    ("saglik", "field", "Health and welfare"),
    ("hacettepe", "university", "Hacettepe Üniversitesi"),
    ("clinic", "company", "Clinic Group"),
    ("wound", "skill", "Wound care"),
])
def test_each_kind_is_findable(d, q, kind, expected):
    assert expected in names(search(q=q), kind)


def test_result_carries_id_and_both_names(d):
    item = search(q="hemsire", type="program_type").json()["results"]["program_type"][0]
    assert item == {"id": ProgramType.objects.get().pk, "name": "Nursing", "name_tr": "Hemşirelik"}


def test_type_filters_and_no_type_returns_every_kind(d):
    assert set(search(q="clinic", type="company").json()["results"]) == {"company"}
    assert set(search(q="clinic").json()["results"]) == {"university", "program_type", "field", "company", "skill"}


@pytest.mark.parametrize("params", [{"q": "x"}, {"q": ""}, {"q": " i "}, {}, {"q": "ab", "type": "city"},
                                    {"q": "a" * 101}])
def test_bad_queries_are_422(d, params):
    assert search(**params).status_code == 422


@pytest.mark.parametrize("q", ["%%", "''", "a%", "_e", "' OR 1=1 --", "\\\\"])
def test_special_characters_are_plain_text(d, q):
    r = search(q=q)
    assert r.status_code == 200 and not any(r.json()["results"].values())  # % and _ are not wildcards


def test_no_match_is_empty(d):
    assert search(q="zzzz").json()["results"]["university"] == []


def test_at_most_20_per_kind(db):
    src = Source.objects.create(name="Test data")
    Skill.objects.bulk_create(Skill(name=f"Skill {i}", source=src) for i in range(21))
    assert len(names(search(q="skill", type="skill"), "skill")) == 20


@pytest.mark.parametrize("q, expected", [
    ("bogazci", "Boğaziçi Üniversitesi"),  # a letter missing
    ("hacetepe", "Hacettepe Üniversitesi"),
    ("ankarra", "Ankara Üniversitesi"),  # a letter extra
])
def test_one_typo_matches(d, q, expected):
    assert names(search(q=q, type="university"), "university")[0] == expected


def test_short_queries_skip_typo_matching(d):
    Skill.objects.create(name="Wood", source=Source.objects.get())
    assert names(search(q="wod", type="skill"), "skill") == []  # would be a typo match at 4+ letters
    assert names(search(q="are", type="skill"), "skill") == ["Wound care"]


def test_name_start_before_word_start_before_inside(d):
    src = Source.objects.get()
    for name in ["Care planning", "Daycare", "Patient care"]:
        Skill.objects.create(name=name, source=src)
    assert names(search(q="care", type="skill"), "skill") == ["Care planning", "Patient care", "Wound care", "Daycare"]
