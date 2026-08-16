import django.core.validators
from django.db import migrations, models


def copy_specialist_descriptions(apps, schema_editor):
    specialist_model = apps.get_model("centers", "SpecialistProfile")
    for specialist in specialist_model.objects.exclude(description="").iterator():
        staff = specialist.staff_profile
        if not staff.description:
            staff.description = specialist.description
            staff.save(update_fields=["description"])


class Migration(migrations.Migration):
    dependencies = [
        ("centers", "0002_alter_center_phone"),
    ]

    operations = [
        migrations.AddField(
            model_name="staffprofile",
            name="contact_number",
            field=models.CharField(
                blank=True,
                max_length=40,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Enter a valid phone number.",
                        regex="^\\+?[0-9][0-9() .-]{4,39}$",
                    )
                ],
                verbose_name="Contact number",
            ),
        ),
        migrations.AddField(
            model_name="staffprofile",
            name="contract_signed_on",
            field=models.DateField(blank=True, null=True, verbose_name="Contract signing date"),
        ),
        migrations.AddField(
            model_name="staffprofile",
            name="contract_valid_until",
            field=models.DateField(blank=True, null=True, verbose_name="Contract valid until"),
        ),
        migrations.AddField(
            model_name="staffprofile",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="staffprofile",
            name="notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="staffprofile",
            name="project_program",
            field=models.CharField(blank=True, max_length=180, verbose_name="Project or program"),
        ),
        migrations.AlterField(
            model_name="staffprofile",
            name="job_title",
            field=models.CharField(blank=True, max_length=120, verbose_name="Position"),
        ),
        migrations.AlterField(
            model_name="staffprofile",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("inactive", "Inactive"),
                    ("finished", "Finished"),
                ],
                default="active",
                max_length=16,
            ),
        ),
        migrations.AddConstraint(
            model_name="staffprofile",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("contract_signed_on__isnull", True))
                    | models.Q(("contract_valid_until__isnull", True))
                    | models.Q(("contract_valid_until__gte", models.F("contract_signed_on")))
                ),
                name="staff_contract_dates_ordered",
            ),
        ),
        migrations.RunPython(copy_specialist_descriptions, migrations.RunPython.noop),
    ]
