# Search (plan Step 2.5) compares names without case or accents, and tolerates typos.
from django.contrib.postgres.operations import TrigramExtension, UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('careers', '0007_program_links'),
    ]

    operations = [
        UnaccentExtension(),
        TrigramExtension(),
    ]
