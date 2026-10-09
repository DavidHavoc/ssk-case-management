from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, transaction
from django.urls import reverse
from django.utils import timezone

from apps.casework.forms import BeneficiaryForm
from apps.casework.models import Beneficiary, BeneficiaryCodeSequence

from .factories import set_active_center

pytestmark = pytest.mark.django_db


def create_person(center, **kwargs):
    return Beneficiary.objects.create(
        center=center,
        full_name="Synthetic numbered beneficiary",
        service_type=Beneficiary.ServiceType.OTHER,
        **kwargs,
    )


def test_each_center_has_its_own_sequence(center_a, center_b):
    first = create_person(center_a, beneficiary_code="CLIENT-SUPPLIED-CODE")
    other = create_person(center_b)
    second = create_person(center_a, service_status=Beneficiary.ServiceStatus.EXITED)
    assert first.beneficiary_code == f"{center_a.code}_B001"
    assert other.beneficiary_code == f"{center_b.code}_B001"
    assert second.beneficiary_code == f"{center_a.code}_B002"


def test_deleted_numbers_are_not_reused(center_a):
    person = create_person(center_a)
    person.delete()
    assert create_person(center_a).beneficiary_code == f"{center_a.code}_B002"


def test_number_expands_beyond_three_digits(center_a):
    BeneficiaryCodeSequence.objects.create(center=center_a, last_number=999)
    assert create_person(center_a).beneficiary_code == f"{center_a.code}_B1000"


def test_validation_failure_does_not_consume_a_number(center_a):
    with pytest.raises(ValidationError):
        create_person(center_a, birth_date="2099-01-01")
    assert not BeneficiaryCodeSequence.objects.filter(center=center_a).exists()
    assert create_person(center_a).beneficiary_code == f"{center_a.code}_B001"


def test_outer_transaction_rollback_restores_counter(center_a):
    create_person(center_a)
    with transaction.atomic():
        create_person(center_a)
        transaction.set_rollback(True)
    assert create_person(center_a).beneficiary_code == f"{center_a.code}_B002"


def test_code_stays_stable_on_person_and_center_edits(center_a):
    person = create_person(center_a)
    original_code = person.beneficiary_code
    person.notes = "Synthetic updated note"
    person.save()
    center_a.code = "RENAMED-SYNTHETIC"
    center_a.save()
    person.refresh_from_db()
    assert person.beneficiary_code == original_code
    assert create_person(center_a).beneficiary_code == "RENAMED-SYNTHETIC_B002"


def test_previously_used_prefix_does_not_cause_duplicate_codes(center_a, center_b):
    create_person(center_a)
    create_person(center_a)
    original_prefix = center_a.code
    center_a.code = "RENAMED-SYNTHETIC"
    center_a.save()
    center_b.code = original_prefix
    center_b.save()
    assert create_person(center_b).beneficiary_code == f"{original_prefix}_B003"


def test_existing_code_cannot_be_changed(center_a):
    person = create_person(center_a)
    person.beneficiary_code = "MANUAL-REPLACEMENT"
    with pytest.raises(ValidationError, match="assigned automatically"):
        person.save()


def test_form_assigns_code_and_ignores_submitted_code(center_a, coordinator_a):
    form = BeneficiaryForm(
        data={"full_name": "Synthetic form beneficiary", "beneficiary_code": "TAMPERED"},
        user=coordinator_a,
        center=center_a,
    )
    assert form.fields["beneficiary_code"].disabled
    assert form.is_valid(), form.errors
    assert form.save().beneficiary_code == f"{center_a.code}_B001"


def test_create_view_does_not_require_a_beneficiary_code(
    client, coordinator_a, center_a, specialist_a
):
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    offering = center_a.service_offerings.get(service__code="HOME-CARE")
    response = client.post(
        reverse("beneficiary_create"),
        {
            "full_name": "Synthetic view beneficiary",
            "enrollment-offering": str(offering.pk),
            "enrollment-status": "active",
            "enrollment-start_date": "2026-10-01",
            "staffing-lead": str(specialist_a.pk),
            "staffing-effective_date": timezone.localdate().isoformat(),
        },
    )
    assert response.status_code == 302
    assert Beneficiary.objects.get().beneficiary_code == f"{center_a.code}_B001"


def test_previous_code_search_keeps_center_authorization(
    client, coordinator_a, center_a, beneficiary_a, beneficiary_b
):
    Beneficiary.objects.filter(pk__in=[beneficiary_a.pk, beneficiary_b.pk]).update(
        legacy_beneficiary_code="WB-SYNTHETIC-SEARCH"
    )
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    response = client.get(reverse("beneficiary_list"), {"q": "WB-SYNTHETIC-SEARCH"})
    assert response.status_code == 200
    assert list(response.context["page_obj"]) == [beneficiary_a]


def test_legacy_creation_requests_without_codes_get_distinct_enrollments(
    client, coordinator_a, center_a, specialist_a
):
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    for number in (1, 2):
        response = client.post(
            reverse("beneficiary_create"),
            {
                "full_name": f"Synthetic legacy intake {number}",
                "service_type": "other",
                "service_status": "active",
                "enrollment_date": "01/01/2026",
                "staffing-lead": str(specialist_a.pk),
                "staffing-effective_date": timezone.localdate().isoformat(),
            },
        )
        assert response.status_code == 302
        person = Beneficiary.objects.get(beneficiary_code=f"{center_a.code}_B{number:03d}")
        assert person.enrollments.get().episode_code is None


@pytest.mark.django_db(transaction=True)
def test_concurrent_creation_assigns_distinct_numbers(center_a):
    if connection.vendor != "postgresql":
        pytest.skip("Center row locking requires PostgreSQL.")
    barrier = Barrier(2)

    def create_concurrently():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return create_person(center_a).beneficiary_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(create_concurrently) for _ in range(2)]
        codes = {future.result(timeout=20) for future in futures}
    assert codes == {f"{center_a.code}_B001", f"{center_a.code}_B002"}
    assert create_person(center_a).beneficiary_code == f"{center_a.code}_B003"
