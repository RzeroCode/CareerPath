"""Link each job posting to the program types its description asks for (careers.matching.DegreeMatcher).

Names come from the database (each program type's name, Turkish name, aliases and degree terms), so new data or a
term added in the admin needs no code change; run this again after loading postings or changing terms.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from careers.matching import DegreeMatcher, strings
from careers.models import JobPosting, ProgramType


class Command(BaseCommand):
    help = "Link job postings to the program types their descriptions ask for. Re-runnable."

    @transaction.atomic
    def handle(self, *args, **options):
        types = list(ProgramType.objects.all())
        matcher = DegreeMatcher(
            (t.pk, [t.name, t.name_tr, *strings(t.aliases), *strings(t.degree_terms)]) for t in types)
        Link = JobPosting.program_types.through
        Link.objects.all().delete()
        links = [Link(jobposting_id=pk, programtype_id=type_pk)
                 for pk, description in JobPosting.objects.values_list("pk", "description").iterator()
                 for type_pk in matcher.match(description)]
        Link.objects.bulk_create(links)
        linked = len({link.jobposting_id for link in links})
        self.stdout.write(f"{linked} of {JobPosting.objects.count()} postings linked to a program, {len(links)} links")
        for t in sorted(types, key=lambda t: t.name):
            self.stdout.write(f"  {t.name}: {sum(1 for link in links if link.programtype_id == t.pk)}")
