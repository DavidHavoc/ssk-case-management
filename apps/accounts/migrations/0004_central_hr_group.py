from django.db import migrations


CENTRAL_HR_ROLE = "SSK Central HR"


def create_central_hr_group(apps, schema_editor):
    group_model = apps.get_model("auth", "Group")
    group_model.objects.get_or_create(name=CENTRAL_HR_ROLE)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_user_unique_nonblank_user_email_ci"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_central_hr_group, migrations.RunPython.noop),
    ]
