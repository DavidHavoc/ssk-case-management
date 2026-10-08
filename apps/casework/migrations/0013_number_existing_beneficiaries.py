from django.db import migrations


def assign_center_codes(apps, schema_editor):
    Beneficiary = apps.get_model("casework", "Beneficiary")
    Sequence = apps.get_model("casework", "BeneficiaryCodeSequence")
    using = schema_editor.connection.alias
    people = list(
        Beneficiary.objects.using(using).select_related("center").order_by(
            "center_id", "created_at", "id"
        )
    )
    # Vacate all old codes first, including codes that already match the new format.
    for person in people:
        Beneficiary.objects.using(using).filter(pk=person.pk).update(
            legacy_beneficiary_code=person.beneficiary_code,
            beneficiary_code=f"~B-{person.pk.hex}",
        )
    counters = {}
    for person in people:
        number = counters.get(person.center_id, 0) + 1
        counters[person.center_id] = number
        Beneficiary.objects.using(using).filter(pk=person.pk).update(
            beneficiary_code=f"{person.center.code}_B{number:03d}"
        )
    for center_id, number in counters.items():
        Sequence.objects.using(using).update_or_create(
            center_id=center_id, defaults={"last_number": number}
        )


def restore_previous_codes(apps, schema_editor):
    Beneficiary = apps.get_model("casework", "Beneficiary")
    using = schema_editor.connection.alias
    people = list(Beneficiary.objects.using(using).all())
    codes = [person.legacy_beneficiary_code or person.beneficiary_code for person in people]
    if len(codes) != len(set(codes)) or any(len(code) > 32 for code in codes):
        raise RuntimeError("Previous beneficiary codes require reconciliation before rollback.")
    for person in people:
        Beneficiary.objects.using(using).filter(pk=person.pk).update(
            beneficiary_code=f"~B-{person.pk.hex}"
        )
    for person, code in zip(people, codes, strict=True):
        Beneficiary.objects.using(using).filter(pk=person.pk).update(beneficiary_code=code)


class Migration(migrations.Migration):
    dependencies = [("casework", "0012_center_beneficiary_codes")]

    operations = [migrations.RunPython(assign_center_codes, restore_previous_codes)]
