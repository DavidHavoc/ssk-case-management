"""Integration review regressions for untrusted IDs and protected person writes."""

from unittest.mock import patch

import pytest
from django.test import RequestFactory
from django.urls import reverse
from django.utils.translation import override

from apps.audit.models import AuditEvent
from apps.casework.forms import BeneficiaryForm
from apps.casework.models import Beneficiary
from apps.core.authorization import active_center_for_request

from .factories import set_active_center

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def restore_request_language():
    # LocaleMiddleware activates the URL language; do not leak it into later tests.
    with override("en"):
        yield


@pytest.mark.parametrize("language", ["en", "ka"])
def test_duplicate_service_submission_is_reviewable_and_atomic(
    client, manager, center_a, beneficiary_a, language
):
    from django.utils import timezone

    client.force_login(manager)
    client.cookies["django_language"] = language
    set_active_center(client, center_a)
    before = beneficiary_a.enrollments.count()
    with override(language):
        url = reverse("enrollment_create", args=[beneficiary_a.pk])
    response = client.post(
        url,
        {
            "offering": str(center_a.service_offerings.get(service__code="LEGACY-OTHER").pk),
            "status": "active",
            "start_date": timezone.localdate().isoformat(),
        },
    )
    assert response.status_code == 200
    assert "offering" in response.context["form"].errors
    assert ("overlapping enrollment" if language == "en" else "გადაფარვ") in str(
        response.context["form"].errors
    )
    assert beneficiary_a.enrollments.count() == before


@pytest.mark.parametrize("language", ["en", "ka"])
def test_reenrollment_rejection_uses_the_current_language(
    client, manager, center_a, beneficiary_a, language
):
    from django.utils import timezone

    client.force_login(manager)
    client.cookies["django_language"] = language
    set_active_center(client, center_a)
    enrollment = beneficiary_a.enrollments.get()
    with override(language):
        url = reverse("enrollment_reenroll", args=[enrollment.pk])
    response = client.post(
        url,
        {
            "offering": str(center_a.service_offerings.get(service__code="LEGACY-OTHER").pk),
            "status": "active",
            "start_date": timezone.localdate().isoformat(),
        },
    )
    assert response.status_code == 200
    assert ("Only a terminal enrollment" if language == "en" else "ხელახალი ჩარიცხვა") in str(
        response.context["form"].errors
    )
    assert beneficiary_a.enrollments.count() == 1


@pytest.mark.parametrize(
    "route", ["beneficiary_detail", "visit_create", "assessment_create", "plan_create"]
)
@pytest.mark.parametrize("invalid_id", ["invalid-episode-id", "x" * 2048])
def test_malformed_enrollment_selection_is_not_a_server_error(
    client, manager, center_a, beneficiary_a, route, invalid_id
):
    client.force_login(manager)
    set_active_center(client, center_a)
    url = reverse(route, args=[beneficiary_a.pk] if route == "beneficiary_detail" else [])
    response = client.get(url, {"enrollment": invalid_id})
    assert response.status_code == 404
    denied = AuditEvent.objects.filter(outcome="denied").get()
    assert denied.target_id is None
    assert denied.metadata == {}


@pytest.mark.parametrize("route", ["visit_create", "assessment_create", "plan_create"])
def test_malformed_legacy_person_post_returns_form_errors(client, manager, center_a, route):
    client.force_login(manager)
    set_active_center(client, center_a)
    response = client.post(reverse(route), {"beneficiary": "invalid-person-id"})
    assert response.status_code == 200
    assert "enrollment" in response.context["form"].errors


def test_malformed_selected_center_is_discarded(coordinator_a, center_a):
    request = RequestFactory().get("/")
    request.user = coordinator_a
    request.session = {"ssk_active_center": "invalid-center-id"}
    assert active_center_for_request(request) == center_a
    assert request.session["ssk_active_center"] == str(center_a.pk)


@pytest.mark.parametrize("route", ["reports", "report_export"])
@pytest.mark.parametrize(
    ("report", "key"),
    [
        ("enrollments", "specialist"),
        ("enrollments", "service"),
        ("beneficiary_breakdown", "region"),
        ("beneficiary_breakdown", "municipality"),
        ("service_delivery", "activity"),
        ("service_delivery", "location"),
    ],
)
def test_malformed_report_filter_is_not_a_server_error(
    client, manager, center_a, route, report, key
):
    client.force_login(manager)
    set_active_center(client, center_a)
    response = client.get(reverse(route), {"type": report, key: "invalid-object-id"})
    assert response.status_code == 404


def test_specialist_person_save_preserves_a_newer_restricted_contact(
    client, specialist_a, center_a, beneficiary_a
):
    client.force_login(specialist_a.staff_profile.user)
    set_active_center(client, center_a)
    original_save = BeneficiaryForm.save

    def intervening_manager_update(form, *args, **kwargs):
        Beneficiary.objects.filter(pk=beneficiary_a.pk).update(
            emergency_contact_name="New synthetic emergency contact",
            emergency_contact_phone="+995 555 000 999",
            guardian_parent="New synthetic supporter",
            personal_id="SYNTHETIC-NEW-IDENTITY",
        )
        return original_save(form, *args, **kwargs)

    with patch.object(BeneficiaryForm, "save", intervening_manager_update):
        response = client.post(
            reverse("beneficiary_update", args=[beneficiary_a.pk]),
            {"full_name": "Synthetic ordinary edit", "emergency_contact_name": "Forged contact"},
        )
    assert response.status_code == 302
    beneficiary_a.refresh_from_db()
    assert beneficiary_a.full_name == "Synthetic ordinary edit"
    assert beneficiary_a.emergency_contact_name == "New synthetic emergency contact"
    assert beneficiary_a.emergency_contact_phone == "+995 555 000 999"
    assert beneficiary_a.guardian_parent == "New synthetic supporter"
    assert beneficiary_a.personal_id == "SYNTHETIC-NEW-IDENTITY"
