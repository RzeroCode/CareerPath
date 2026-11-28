"""CareerPath data model (plan section 1e). Every data row points to the Source it came from."""
from datetime import timedelta

from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Source(models.Model):
    name = models.CharField(max_length=200, unique=True)
    licence = models.CharField(max_length=200, blank=True)
    url = models.URLField(max_length=500, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True, help_text="When the data was last fetched")
    refresh_days = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Refresh at least this often, in days; empty for data that doesn't go stale")

    def __str__(self):
        return self.name

    @property
    def is_stale(self):
        if self.refresh_days is None:
            return False
        return self.fetched_at is None or self.fetched_at < timezone.now() - timedelta(days=self.refresh_days)


class Sourced(models.Model):
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="+")

    class Meta:
        abstract = True


class University(Sourced):
    class Kind(models.TextChoices):
        STATE = "state", "State"
        FOUNDATION = "foundation", "Foundation"

    name = models.CharField(max_length=200, unique=True)
    name_tr = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, blank=True)
    yok_code = models.CharField(max_length=20, unique=True, null=True, blank=True)

    class Meta:
        verbose_name_plural = "universities"

    def __str__(self):
        return self.name


class Field(Sourced):
    """An ISCED-F 2013 field of education, the classification TÜİK uses."""
    name = models.CharField(max_length=200)
    name_tr = models.CharField(max_length=200, blank=True)
    isced_code = models.CharField(max_length=4, unique=True)

    def __str__(self):
        return f"{self.isced_code} {self.name}"


class ProgramType(Sourced):
    """A kind of degree program across universities (TÜİK "bölüm"), e.g. Computer Engineering."""
    name = models.CharField(max_length=200, unique=True)
    name_tr = models.CharField(max_length=200, blank=True)
    field = models.ForeignKey(Field, on_delete=models.PROTECT, null=True, blank=True, related_name="program_types")

    def __str__(self):
        return self.name


class Program(Sourced):
    """One university's program, identified by its ÖSYM program code."""
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name="programs")
    program_type = models.ForeignKey(ProgramType, on_delete=models.PROTECT, related_name="programs")
    name_tr = models.CharField(max_length=300, help_text="Full name as YÖK Atlas lists it, e.g. with language")
    osym_code = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return f"{self.university} · {self.name_tr}"


class Occupation(Sourced):
    name = models.CharField(max_length=300)
    name_tr = models.CharField(max_length=300, blank=True)
    esco_uri = models.URLField(max_length=300, unique=True)
    isco_code = models.CharField(max_length=10, blank=True)

    def __str__(self):
        return self.name


class Skill(Sourced):
    name = models.CharField(max_length=300)
    name_tr = models.CharField(max_length=300, blank=True)
    aliases = models.JSONField(default=list, blank=True, help_text="Other spellings, Turkish and English")
    esco_uri = models.URLField(max_length=300, unique=True, null=True, blank=True)
    onet_hot = models.BooleanField(default=False, help_text="O*NET Hot Technology")

    def __str__(self):
        return self.name


class Company(Sourced):
    class Ats(models.TextChoices):
        NONE = "", "None"
        GREENHOUSE = "greenhouse", "Greenhouse"
        LEVER = "lever", "Lever"
        ASHBY = "ashby", "Ashby"
        SMARTRECRUITERS = "smartrecruiters", "SmartRecruiters"
        WORKABLE = "workable", "Workable"

    name = models.CharField(max_length=200, unique=True)
    aliases = models.JSONField(default=list, blank=True)
    sector = models.CharField(max_length=100, blank=True)
    ats_provider = models.CharField(max_length=20, choices=Ats.choices, blank=True)
    ats_board_token = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name_plural = "companies"
        constraints = [
            models.UniqueConstraint(
                fields=["ats_provider", "ats_board_token"],
                condition=~Q(ats_board_token=""),
                name="company_unique_ats_board",
            ),
            models.CheckConstraint(
                condition=Q(ats_provider="", ats_board_token="") | (~Q(ats_provider="") & ~Q(ats_board_token="")),
                name="company_ats_both_or_neither",
            ),
        ]

    def __str__(self):
        return self.name


class OutcomeStat(Sourced):
    """A graduate-outcome figure for a program type or a field (TÜİK publishes both, national only)."""
    class Metric(models.TextChoices):
        EMPLOYMENT_RATE = "employment_rate", "Registered employment rate (%)"
        MONTHS_TO_FIRST_JOB = "months_to_first_job", "Months to first job"
        FIELD_MATCH_RATE = "field_match_rate", "Working in own field (%)"

    program_type = models.ForeignKey(ProgramType, on_delete=models.CASCADE, null=True, blank=True, related_name="outcomes")
    field = models.ForeignKey(Field, on_delete=models.CASCADE, null=True, blank=True, related_name="outcomes")
    metric = models.CharField(max_length=30, choices=Metric.choices)
    value = models.DecimalField(max_digits=7, decimal_places=2)
    sample_size = models.PositiveIntegerField(null=True, blank=True, help_text="Empty when the source doesn't publish it")
    year = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(program_type__isnull=False, field__isnull=True) | Q(program_type__isnull=True, field__isnull=False),
                name="outcome_one_target",
            ),
            models.UniqueConstraint(
                fields=["program_type", "field", "metric", "year", "source"],
                nulls_distinct=False,
                name="outcome_unique",
            ),
        ]

    def __str__(self):
        return f"{self.program_type or self.field} {self.metric} {self.year}: {self.value}"


class JobPosting(Sourced):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="postings")
    external_id = models.CharField(max_length=200, help_text="The job board's own id for the posting")
    title = models.CharField(max_length=300)
    occupation = models.ForeignKey(Occupation, on_delete=models.SET_NULL, null=True, blank=True, related_name="postings")
    location = models.CharField(max_length=300, blank=True)
    country = models.CharField(max_length=2, blank=True, help_text="ISO 3166-1 alpha-2, e.g. TR")
    url = models.URLField(max_length=500)
    description = models.TextField(blank=True, help_text="Plain text of the posting, for skill extraction")
    first_seen = models.DateField()
    last_seen = models.DateField()
    skills = models.ManyToManyField(Skill, blank=True, related_name="postings")

    class Meta:
        constraints = [
            # Some boards (e.g. Workable) number postings per company, so the company is part of the key.
            models.UniqueConstraint(fields=["source", "company", "external_id"], name="posting_unique_per_company"),
            models.CheckConstraint(condition=Q(last_seen__gte=F("first_seen")), name="posting_seen_order"),
        ]

    def __str__(self):
        return f"{self.company} · {self.title}"


class SkillDemandMonthly(Sourced):
    """How many postings in a month mention a skill. occupation empty = all postings."""
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="monthly_demand")
    occupation = models.ForeignKey(Occupation, on_delete=models.CASCADE, null=True, blank=True)
    month = models.DateField(help_text="First day of the month")
    mentions = models.PositiveIntegerField()
    total_postings = models.PositiveIntegerField()

    class Meta:
        verbose_name_plural = "skill demand (monthly)"
        constraints = [
            models.UniqueConstraint(fields=["skill", "occupation", "month", "source"], nulls_distinct=False, name="demand_unique"),
            models.CheckConstraint(condition=Q(mentions__lte=F("total_postings")), name="demand_mentions_le_total"),
            models.CheckConstraint(condition=Q(month__day=1), name="demand_month_first_day"),
        ]

    def __str__(self):
        return f"{self.skill} {self.month:%Y-%m}: {self.mentions}/{self.total_postings}"
