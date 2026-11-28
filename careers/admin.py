from django.apps import apps
from django.contrib import admin
from django.db.models import Count, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from . import models as m


def rows_per_source():
    """Data rows pointing at each source, summed over every table that has a source."""
    total = Value(0)
    for model in apps.get_app_config("careers").get_models():
        if issubclass(model, m.Sourced):
            count = model.objects.filter(source=OuterRef("pk")).order_by().values("source").annotate(n=Count("pk")).values("n")
            total = total + Coalesce(Subquery(count, output_field=IntegerField()), 0)
    return total


@admin.register(m.Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ["name", "rows", "fetched_at", "refresh_days", "stale", "licence"]
    search_fields = ["name"]
    ordering = ["name"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(rows=rows_per_source())

    @admin.display(ordering="rows")
    def rows(self, obj):
        return obj.rows

    @admin.display(boolean=True)
    def stale(self, obj):
        return obj.is_stale and obj.rows > 0  # a source left with no rows has been replaced, not neglected


class SourcedAdmin(admin.ModelAdmin):
    list_filter = ["source"]
    list_select_related = ["source"]


@admin.register(m.University)
class UniversityAdmin(SourcedAdmin):
    list_display = ["name", "name_tr", "city", "kind", "source"]
    list_filter = ["kind", "source"]
    search_fields = ["name", "name_tr", "yok_code"]


@admin.register(m.Field)
class FieldAdmin(SourcedAdmin):
    list_display = ["isced_code", "name", "name_tr", "source"]
    search_fields = ["name", "name_tr", "isced_code"]


@admin.register(m.ProgramType)
class ProgramTypeAdmin(SourcedAdmin):
    list_display = ["name", "name_tr", "field", "source"]
    search_fields = ["name", "name_tr"]


@admin.register(m.Program)
class ProgramAdmin(SourcedAdmin):
    list_display = ["name_tr", "university", "program_type", "osym_code"]
    list_select_related = ["university", "program_type"]
    search_fields = ["name_tr", "osym_code", "university__name"]
    autocomplete_fields = ["university", "program_type"]


@admin.register(m.Occupation)
class OccupationAdmin(SourcedAdmin):
    list_display = ["name", "name_tr", "isco_code", "source"]
    search_fields = ["name", "name_tr", "isco_code"]


@admin.register(m.Skill)
class SkillAdmin(SourcedAdmin):
    list_display = ["name", "name_tr", "onet_hot", "source"]
    list_filter = ["onet_hot", "source"]
    search_fields = ["name", "name_tr"]


@admin.register(m.Company)
class CompanyAdmin(SourcedAdmin):
    list_display = ["name", "sector", "ats_provider", "ats_board_token", "source"]
    list_filter = ["ats_provider", "sector", "source"]
    search_fields = ["name"]


@admin.register(m.OutcomeStat)
class OutcomeStatAdmin(SourcedAdmin):
    list_display = ["__str__", "metric", "year", "value", "sample_size", "source"]
    list_filter = ["metric", "year", "source"]
    list_select_related = ["program_type", "field", "source"]


@admin.register(m.JobPosting)
class JobPostingAdmin(SourcedAdmin):
    list_display = ["title", "company", "country", "first_seen", "last_seen", "source"]
    list_filter = ["country", "source"]
    list_select_related = ["company", "source"]
    search_fields = ["title", "company__name"]
    autocomplete_fields = ["company", "occupation", "skills"]


@admin.register(m.SkillDemandMonthly)
class SkillDemandMonthlyAdmin(SourcedAdmin):
    list_display = ["skill", "occupation", "month", "mentions", "total_postings", "source"]
    list_filter = ["month", "source"]
    list_select_related = ["skill", "occupation", "source"]
    autocomplete_fields = ["skill", "occupation"]
