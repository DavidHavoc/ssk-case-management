from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("casework", "0002_alter_beneficiary_phone_and_more"),
        ("centers", "0003_staff_contract_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="privateattachment",
            name="document_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("project_agreement", "Project agreement"),
                    ("employee_contract", "Employee contract"),
                    ("additional_documentation", "Additional documentation"),
                ],
                max_length=32,
            ),
        ),
    ]
