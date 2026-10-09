import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse
from django.utils import timezone, translation

from apps.casework.forms import BeneficiaryForm
from apps.casework.models import Beneficiary
from apps.core.views import REPORT_TYPES

from .factories import make_assessment, make_plan, make_visit, set_active_center

pytestmark = pytest.mark.django_db

CONTACT_NAME = "Synthetic emergency supporter"
CONTACT_PHONE = "+995 (555) 123-456"
LABELS = {
    "en": (
        "Guardian/parent or supporter",
        "Emergency contact name",
        "Emergency contact phone number",
        "Restricted person information",
        "Enter a valid phone number.",
    ),
    "ka": (
        "მეურვე/მშობელი ან მხარდამჭერი",
        "სასწრაფო კავშირის პირის სახელი",
        "სასწრაფო კავშირის პირის ტელეფონის ნომერი",
        "პირის შეზღუდული ინფორმაცია",
        "შეიყვანეთ სწორი ტელეფონის ნომერი.",
    ),
}


@pytest.fixture(autouse=True)
def contact_test_language(request):
    language = request.getfixturevalue("language") if "language" in request.fixturenames else "en"
    with translation.override(language):
        yield


@pytest.mark.parametrize("role", ["manager", "coordinator_a"])
@pytest.mark.parametrize("language", ["en", "ka"])
@pytest.mark.parametrize("with_contacts", [False, True])
def test_contact_create_edit_and_clear_round_trip(
    client, request, center_a, role, language, with_contacts, specialist_a
):
    client.force_login(request.getfixturevalue(role))
    set_active_center(client, center_a)
    guardian, name_label, phone_label, restricted_label, _ = LABELS[language]
    offering = center_a.service_offerings.get(service__code="HOME-CARE")
    data = {
        "full_name": "Synthetic contact beneficiary",
        "guardian_parent": "Synthetic existing guardian",
        "enrollment-offering": str(offering.pk),
        "enrollment-status": "active",
        "enrollment-start_date": "2026-10-01",
        "staffing-lead": str(specialist_a.pk),
        "staffing-effective_date": timezone.localdate().isoformat(),
    }
    if with_contacts:
        data.update(emergency_contact_name=CONTACT_NAME, emergency_contact_phone=CONTACT_PHONE)
    create_url = reverse("beneficiary_create")
    response = client.get(create_url)
    assert response.status_code == 200
    body = response.content.decode()
    assert guardian in body
    restricted_section = body.split(f"<h2>{restricted_label}</h2>")[1].split("</section>")[0]
    assert name_label in restricted_section
    assert phone_label in restricted_section
    assert 'aria-describedby="id_emergency_contact_name-help"' in restricted_section
    assert 'aria-describedby="id_emergency_contact_phone-help"' in restricted_section
    assert body.count('name="emergency_contact_name"') == 1
    assert body.count('name="emergency_contact_phone"') == 1
    response = client.post(create_url, data)
    assert response.status_code == 302
    person = Beneficiary.objects.get(full_name=data["full_name"])
    original_code = person.beneficiary_code
    assert original_code == f"{center_a.code}_B001"
    assert person.emergency_contact_name == (CONTACT_NAME if with_contacts else "")
    assert person.emergency_contact_phone == (CONTACT_PHONE if with_contacts else "")
    edit_url = reverse("beneficiary_update", args=[person.pk])
    detail_url = reverse("beneficiary_detail", args=[person.pk])
    for url in (edit_url, detail_url):
        response = client.get(url)
        assert response.status_code == 200
        body = response.content.decode()
        assert all(label in body for label in (guardian, name_label, phone_label, restricted_label))
        assert "Guardian or parent" not in body
        assert person.guardian_parent in body
        if with_contacts:
            assert CONTACT_NAME in body
            assert CONTACT_PHONE in body
    for name, phone in (("Synthetic updated supporter", "+49 30 123456"), ("", "")):
        response = client.post(
            edit_url,
            {
                "full_name": person.full_name,
                "guardian_parent": person.guardian_parent,
                "emergency_contact_name": name,
                "emergency_contact_phone": phone,
                "beneficiary_code": "FORGED-CODE",
            },
        )
        assert response.status_code == 302
        person.refresh_from_db()
        assert person.emergency_contact_name == name
        assert person.emergency_contact_phone == phone
        assert person.guardian_parent == "Synthetic existing guardian"
        assert person.beneficiary_code == original_code


@pytest.mark.parametrize("language", ["en", "ka"])
@pytest.mark.parametrize("phone", ["", "+995 (555) 123-456", "+49 30 123456", "555123456"])
def test_optional_contacts_and_international_phone_validation(
    center_a, coordinator_a, language, phone
):
    with translation.override(language):
        form = BeneficiaryForm(
            data={"full_name": "Synthetic phone validation", "emergency_contact_phone": phone},
            user=coordinator_a,
            center=center_a,
        )
        assert not form.fields["emergency_contact_name"].required
        assert not form.fields["emergency_contact_phone"].required
        assert form.is_valid(), form.errors
        person = form.save()
        assert person.emergency_contact_name == ""
        assert person.emergency_contact_phone == phone


@pytest.mark.parametrize("language", ["en", "ka"])
@pytest.mark.parametrize("phone", ["abc", "123", "+995 invalid", "1" * 41])
def test_invalid_contact_phone_is_rejected_by_form_and_model(
    client, center_a, coordinator_a, beneficiary_a, language, phone
):
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    response = client.post(
        reverse("beneficiary_update", args=[beneficiary_a.pk]),
        {"full_name": beneficiary_a.full_name, "emergency_contact_phone": phone},
    )
    assert response.status_code == 200
    assert "emergency_contact_phone" in response.context["form"].errors
    if len(phone) <= 40:
        assert LABELS[language][4] in response.content.decode()
    beneficiary_a.refresh_from_db()
    assert beneficiary_a.emergency_contact_phone == ""
    beneficiary_a.emergency_contact_phone = phone
    with pytest.raises(ValidationError) as error:
        beneficiary_a.full_clean()
    assert "emergency_contact_phone" in error.value.message_dict


@pytest.mark.parametrize("language", ["en", "ka"])
def test_assigned_specialist_cannot_read_or_forge_contacts(
    client, specialist_a, center_a, beneficiary_a, language
):
    beneficiary_a.emergency_contact_name = CONTACT_NAME
    beneficiary_a.emergency_contact_phone = CONTACT_PHONE
    beneficiary_a.save()
    user = specialist_a.staff_profile.user
    client.force_login(user)
    set_active_center(client, center_a)
    update_url = reverse("beneficiary_update", args=[beneficiary_a.pk])
    for url in (update_url, reverse("beneficiary_detail", args=[beneficiary_a.pk])):
        response = client.get(url)
        assert response.status_code == 200
        body = response.content.decode()
        assert CONTACT_NAME not in body
        assert CONTACT_PHONE not in body
        assert "emergency_contact_name" not in body
        assert "emergency_contact_phone" not in body
        assert LABELS[language][1] not in body
        assert LABELS[language][2] not in body
        assert LABELS[language][3] not in body
    data = {
        "full_name": beneficiary_a.full_name,
        "notes": "Synthetic permitted note",
        "emergency_contact_name": "Forged supporter",
        "emergency_contact_phone": "invalid forged phone",
    }
    form = BeneficiaryForm(data=data, instance=beneficiary_a, user=user, center=center_a)
    assert "emergency_contact_name" not in form.fields
    assert "emergency_contact_phone" not in form.fields
    assert not form.restricted_fields
    assert form.is_valid(), form.errors
    response = client.post(update_url, data)
    assert response.status_code == 302
    beneficiary_a.refresh_from_db()
    assert beneficiary_a.notes == data["notes"]
    assert beneficiary_a.emergency_contact_name == CONTACT_NAME
    assert beneficiary_a.emergency_contact_phone == CONTACT_PHONE
    assert client.get(reverse("beneficiary_create")).status_code == 403
    assert client.post(reverse("beneficiary_create"), data).status_code == 403


@pytest.mark.parametrize("role", ["manager", "coordinator_a", "specialist_a"])
def test_cross_center_contact_get_and_post_denied(client, request, center_a, beneficiary_b, role):
    actor = request.getfixturevalue(role)
    if role == "specialist_a":
        actor = actor.staff_profile.user
    beneficiary_b.emergency_contact_name = CONTACT_NAME
    beneficiary_b.emergency_contact_phone = CONTACT_PHONE
    beneficiary_b.save()
    client.force_login(actor)
    set_active_center(client, center_a)
    for route in ("beneficiary_detail", "beneficiary_update"):
        response = client.get(reverse(route, args=[beneficiary_b.pk]))
        assert response.status_code == 404
        assert CONTACT_NAME not in response.content.decode()
        assert CONTACT_PHONE not in response.content.decode()
    assert (
        client.post(
            reverse("beneficiary_update", args=[beneficiary_b.pk]),
            {"emergency_contact_name": "Forged", "emergency_contact_phone": "+49 123456"},
        ).status_code
        == 404
    )
    beneficiary_b.refresh_from_db()
    assert beneficiary_b.emergency_contact_name == CONTACT_NAME
    assert beneficiary_b.emergency_contact_phone == CONTACT_PHONE


@pytest.mark.parametrize("role", ["manager", "coordinator_a", "specialist_a"])
def test_all_reports_exports_and_lists_omit_emergency_contacts(
    client, request, role, center_a, beneficiary_a, specialist_a
):
    beneficiary_a.emergency_contact_name = CONTACT_NAME
    beneficiary_a.emergency_contact_phone = CONTACT_PHONE
    beneficiary_a.save()
    make_visit(beneficiary_a, specialist_a)
    make_assessment(beneficiary_a, specialist_a)
    make_plan(beneficiary_a, specialist_a)
    actor = request.getfixturevalue(role)
    if role == "specialist_a":
        actor = actor.staff_profile.user
    client.force_login(actor)
    set_active_center(client, center_a)
    for report_type in REPORT_TYPES:
        response = client.get(reverse("reports"), {"type": report_type})
        assert response.status_code == 200
        export = client.get(reverse("report_export"), {"type": report_type})
        assert export.status_code == (403 if role == "specialist_a" else 200)
        for output in (response, export):
            body = output.content.decode("utf-8-sig")
            assert CONTACT_NAME not in body
            assert CONTACT_PHONE not in body
            assert "emergency_contact_name" not in body
            assert "emergency_contact_phone" not in body
    home_route = "specialist_workspace" if role == "specialist_a" else "dashboard"
    for route in ("beneficiary_list", home_route, "visit_list", "assessment_list", "plan_list"):
        response = client.get(reverse(route))
        assert response.status_code == 200
        body = response.content.decode()
        assert CONTACT_NAME not in body
        assert CONTACT_PHONE not in body


@pytest.mark.django_db(transaction=True)
def test_contact_migration_preserves_existing_people_and_codes_and_reverses():
    before = [("casework", "0013_number_existing_beneficiaries")]
    after = [("casework", "0014_beneficiary_emergency_contacts")]
    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(before)
        old_apps = executor.loader.project_state(before).apps
        Center = old_apps.get_model("centers", "Center")
        Person = old_apps.get_model("casework", "Beneficiary")
        Sequence = old_apps.get_model("casework", "BeneficiaryCodeSequence")
        center = Center.objects.create(code="SYN-CONTACT", name="Synthetic contact migration")
        person = Person.objects.create(
            center=center,
            full_name="Synthetic existing person",
            beneficiary_code="SYN-CONTACT_B001",
            guardian_parent="Synthetic preserved guardian",
            phone="+49 123456",
        )
        Sequence.objects.create(center=center, last_number=1)
        original = Person.objects.values().get(pk=person.pk)
        original_sequence = Sequence.objects.values().get(center=center)
        executor = MigrationExecutor(connection)
        executor.migrate(after)
        new_apps = executor.loader.project_state(after).apps
        migrated = new_apps.get_model("casework", "Beneficiary").objects.values().get(pk=person.pk)
        assert migrated.pop("emergency_contact_name") == ""
        assert migrated.pop("emergency_contact_phone") == ""
        assert migrated == original
        assert (
            new_apps.get_model("casework", "BeneficiaryCodeSequence")
            .objects.values()
            .get(center_id=center.pk)
            == original_sequence
        )
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        restored = executor.loader.project_state(before).apps.get_model("casework", "Beneficiary")
        assert restored.objects.values().get(pk=person.pk) == original
    finally:
        MigrationExecutor(connection).migrate(leaves)
