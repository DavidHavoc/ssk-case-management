from django.db import migrations


ROLE_NAMES = ("System Manager", "SSK Center Coordinator", "SSK Specialist")


def create_application_groups(apps, schema_editor):
    group_model = apps.get_model("auth", "Group")
    for name in ROLE_NAMES:
        group_model.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [migrations.RunPython(create_application_groups, migrations.RunPython.noop)]
