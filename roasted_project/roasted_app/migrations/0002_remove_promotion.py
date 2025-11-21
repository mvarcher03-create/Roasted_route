# Generated migration to remove Promotion model

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('roasted_app', '0001_initial'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Promotion',
        ),
    ]
