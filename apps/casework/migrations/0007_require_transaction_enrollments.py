import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("casework", "0006_seed_catalogs_and_backfill_enrollments")]

    operations = [
        migrations.AlterField(
            model_name="assessment",
            name="enrollment",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="assessments",
                to="casework.serviceenrollment",
            ),
        ),
        migrations.AlterField(
            model_name="individualplan",
            name="enrollment",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="plans",
                to="casework.serviceenrollment",
            ),
        ),
        migrations.AlterField(
            model_name="servicevisit",
            name="enrollment",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="visits",
                to="casework.serviceenrollment",
            ),
        ),
    ]
