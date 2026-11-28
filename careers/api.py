"""CareerPath API v1 (Django Ninja): the engine over HTTP, with typed requests and responses.

Docs: /api/docs (OpenAPI schema at /api/openapi.json). Every response number carries its evidence.
"""
from datetime import date
from typing import Annotated, Literal

from django.middleware.csrf import get_token
from ninja import Field, NinjaAPI, Schema
from ninja.errors import HttpError, ValidationError
from ninja.throttling import AnonRateThrottle
from ninja.utils import check_csrf
from pydantic import ConfigDict

from careers.engine import Profile, ProfileError, recommend

api = NinjaAPI(
    title="CareerPath API",
    version="1",
    description="Graduate outcomes, who is hiring, and which skills employers ask for. "
                "Every number comes with its sources, date and sample size.",
    urls_namespace="api",
    # Per client address (settings.NINJA_NUM_PROXIES). shortcut: counts live in the default per-process cache;
    # use a shared cache (e.g. Redis) when the app runs as more than one process.
    throttle=[AnonRateThrottle("60/m")],
)

Id = Annotated[int, Field(strict=True, gt=0)]  # strict: "5", 5.0 and true are not ids


# --- request ------------------------------------------------------------------------------------

class ProfileIn(Schema):
    """Any combination; at least one. Ids come from the search and detail endpoints."""
    model_config = ConfigDict(extra="forbid")  # a misspelled key is an error, not silently ignored

    university: Id | None = None
    program_type: Id | None = None
    field: Id | None = None
    company: Id | None = None
    skills: list[Id] | None = Field(None, max_length=50, description="Skills the user has")


# --- response -----------------------------------------------------------------------------------

class Ref(Schema):
    id: int
    name: str
    name_tr: str = ""


class Evidence(Schema):
    sources: list[str] = Field(description="Where the numbers come from")
    as_of: date | None = Field(description="Date of the oldest data used")
    sample_size: int = Field(description="Records the section is based on")


class OutcomeFigure(Schema):
    metric: Literal["employment_rate", "months_to_first_job", "field_match_rate"]
    label: str
    value: float
    year: int
    level: Literal["program_type", "field"] = Field(
        description="field: no figure for the program, so its broader field's figure is shown")
    source: str
    sample_size: int | None = Field(description="Graduates counted; null when the source doesn't publish it")
    sample_size_note: str


class OutcomeItem(Schema):
    program_type: Ref
    figures: list[OutcomeFigure]


class Outcomes(Schema):
    items: list[OutcomeItem]
    evidence: Evidence


class CompanyItem(Schema):
    company: Ref
    open_postings: int


class CompaniesHiring(Schema):
    items: list[CompanyItem] = Field(description="Companies with open postings in Turkey, most postings first")
    companies_tracked: int = Field(description="Companies whose job boards were read in the last 28 days")
    evidence: Evidence


class SkillItem(Schema):
    skill: Ref
    lift: float = Field(description="How many times more often these postings name the skill than all postings do")
    mentions: int
    share_in_scope: float
    held: bool = Field(description="The user listed this skill")
    onet_hot: bool = Field(description="O*NET (US) Hot Technology")


class Needs(Schema):
    postings: int
    companies: int
    per_skill: int


class Skills(Schema):
    enough_data: bool = Field(description="false: too few postings or companies to rank skills; see needs")
    scope_postings: int
    scope_companies: int
    all_postings: int
    needs: Needs
    scope_label: str
    items: list[SkillItem]
    evidence: Evidence


class ProgramItem(Schema):
    program_type: Ref
    open_postings: int


class ProgramsAskedFor(Schema):
    items: list[ProgramItem]
    evidence: Evidence


class Universities(Schema):
    items: list[Ref] = Field(description="Universities offering the programs, alphabetical (not ranked)")
    evidence: Evidence


class Sections(Schema):
    outcomes: Outcomes | None = Field(None, description="With a university, program type or field")
    companies_hiring: CompaniesHiring
    skills: Skills | None = Field(None, description="With a university, program type or field")
    programs_asked_for: ProgramsAskedFor | None = Field(None, description="With a company or skills")
    universities: Universities | None = Field(None, description="With a program type or field, and no university")


class RecommendationOut(Schema):
    notes: list[str]
    sections: Sections


class ErrorOut(Schema):
    detail: str | list[dict]


class CsrfOut(Schema):
    csrf_token: str


# --- endpoints ----------------------------------------------------------------------------------

@api.get("/v1/csrf", response=CsrfOut, summary="Get a CSRF token",
         description="Sets the csrftoken cookie. Send the token back in the X-CSRFToken header on POST requests.")
def csrf(request):
    return {"csrf_token": get_token(request)}


@api.post("/v1/recommendations", response={200: RecommendationOut, 403: ErrorOut, 422: ErrorOut, 429: ErrorOut},
          summary="Recommendations for a profile")
def recommendations(request, profile: ProfileIn):
    # Ninja skips Django's CSRF check for views without cookie auth, so it is done here.
    if check_csrf(request) is not None:
        raise HttpError(403, "CSRF check failed: get a token from GET /api/v1/csrf and send it in the X-CSRFToken header.")
    try:
        return recommend(Profile(**{k: v for k, v in profile.dict().items() if v is not None}))
    except ProfileError as e:
        loc = ["body", "profile"] + ([e.field] if e.field else [])
        raise ValidationError([{"loc": loc, "msg": str(e), "type": "value_error"}])
