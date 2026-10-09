from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone, translation

from apps.casework.forms import EnrollmentIntakeForm, EnrollmentUpdateForm, ServiceVisitForm
from apps.casework.models import (
    CenterServiceOffering,
    EnrollmentSpecialistAssignment,
    ServiceEnrollment,
)
from apps.core.reporting import report_headers, report_rows

from .factories import make_assessment, make_plan, make_visit, set_active_center

pytestmark = pytest.mark.django_db


def _intake(offering, start="02/02/2026", **extra):
    return {
        "offering": offering.pk,
        "status": "active",
        "start_date": start,
        "first_service_date": "",
        **extra,
    }


def test_concurrent_services_and_reenrollment_need_only_beneficiary_code(
    client, beneficiary_a, coordinator_a, center_a
):
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    enrollments = []
    for code in ("HOME-CARE", "FOOD-DELIVERY"):
        offering = center_a.service_offerings.get(service__code=code)
        url = reverse("enrollment_create", kwargs={"beneficiary_pk": beneficiary_a.pk})
        page = client.get(url)
        assert 'name="episode_code"' not in page.content.decode()
        response = client.post(url, _intake(offering, episode_code="FORGED-SECOND-CODE"))
        assert response.status_code == 302
        row = beneficiary_a.enrollments.get(service=offering.service)
        assert row.episode_code is None
        assert response.url.endswith(f"?enrollment={row.pk}")
        assert row.start_date == date(2026, 2, 2)
        enrollments.append(row)
    home, food = enrollments
    assert home.pk != food.pk
    assert beneficiary_a.beneficiary_code in str(home)
    assert beneficiary_a.beneficiary_code in str(food)
    assert "02/02/2026" in str(home)
    assert home.service.name_en in str(home)
    assert "Active" in str(home)
    response = client.post(
        reverse("enrollment_transition", kwargs={"pk": home.pk, "action": "exit"}),
        {"effective_date": "01/04/2026", "reason": "Synthetic exit"},
    )
    assert response.status_code == 302
    old_row = ServiceEnrollment.objects.values().get(pk=home.pk)
    old_events = list(home.state_events.values())
    response = client.post(
        reverse("enrollment_reenroll", kwargs={"pk": home.pk}),
        _intake(
            center_a.service_offerings.get(service=home.service),
            "01/06/2026",
            first_service_date="02/06/2026",
        ),
    )
    assert response.status_code == 302
    later = ServiceEnrollment.objects.get(prior_enrollment=home)
    assert later.pk != home.pk
    assert later.episode_code is None
    assert later.first_service_date == date(2026, 6, 2)
    assert later.start_date == date(2026, 6, 1)
    assert ServiceEnrollment.objects.values().get(pk=home.pk) == old_row
    assert list(home.state_events.values()) == old_events
    food.refresh_from_db()
    assert food.status == "active"
    later_before = ServiceEnrollment.objects.values().get(pk=later.pk)
    response = client.post(
        reverse("enrollment_update", kwargs={"pk": food.pk}),
        _intake(
            center_a.service_offerings.get(service=food.service),
            notes="Synthetic exact food enrollment update",
            episode_code="FORGED-UPDATE-CODE",
        ),
    )
    assert response.status_code == 302
    food.refresh_from_db()
    assert food.notes == "Synthetic exact food enrollment update"
    assert food.episode_code is None
    assert ServiceEnrollment.objects.values().get(pk=later.pk) == later_before
    assert ServiceEnrollment.objects.values().get(pk=home.pk) == old_row


@pytest.mark.parametrize("language,label", [("en", "Enrollment date"), ("ka", "ჩარიცხვის თარიღი")])
def test_labels_dates_legacy_identifier_and_unknown_history(
    client, beneficiary_a, coordinator_a, center_a, language, label
):
    enrollment = beneficiary_a.enrollments.get()
    ServiceEnrollment.objects.filter(pk=enrollment.pk).update(
        episode_code="Synthetic-Preserved-E01",
        start_date=None,
        first_service_date=None,
        legacy_dates_incomplete=True,
    )
    enrollment.refresh_from_db()
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    with translation.override(language):
        form = EnrollmentIntakeForm(center=center_a)
        assert str(form.fields["start_date"].label) == label
        assert "episode_code" not in form.fields
        assert "episode_code" not in EnrollmentUpdateForm(instance=enrollment).fields
        valid = EnrollmentIntakeForm(
            _intake(center_a.service_offerings.get(service=enrollment.service)), center=center_a
        )
        assert valid.is_valid(), valid.errors
        assert valid.cleaned_data["start_date"] == date(2026, 2, 2)
        assert label in report_headers("enrollments")
        rows = list(report_rows("enrollments", [enrollment]))
        assert rows[0][0] == beneficiary_a.beneficiary_code
        assert rows[0][-2] == ""
        assert "Synthetic-Preserved-E01" not in rows[0]
        assert len(rows[0]) == len(report_headers("enrollments"))
    with translation.override(language):
        response = client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}))
    body = response.content.decode()
    assert label in body
    assert "Synthetic-Preserved-E01" in body
    assert beneficiary_a.beneficiary_code in body
    assert ("Unknown legacy date" if language == "en" else "ძველი ჩანაწერის უცნობი თარიღი") in body
    assert 'name="episode_code"' not in body
    form = EnrollmentUpdateForm(
        {
            "first_service_date": "",
            "notes": "Synthetic edit",
            "episode_code": "FORGED-LEGACY-IDENTIFIER",
            "start_date": "01/01/2026",
        },
        instance=enrollment,
    )
    assert form.is_valid(), form.errors
    form.save()
    enrollment.refresh_from_db()
    assert enrollment.episode_code == "Synthetic-Preserved-E01"
    assert enrollment.start_date is None


def test_first_service_date_stays_separate_and_validated(center_a, beneficiary_a):
    offering = center_a.service_offerings.get(service__code="HOME-CARE")
    form = EnrollmentIntakeForm(_intake(offering, first_service_date="01/02/2026"), center=center_a)
    assert not form.is_valid()
    assert "enrollment date" in str(form.errors["first_service_date"])
    enrollment = beneficiary_a.enrollments.get()
    enrollment.first_service_date = date(2025, 12, 31)
    with pytest.raises(ValidationError, match="enrollment date"):
        enrollment.full_clean()
    # Other start dates keep their existing wording.
    assert CenterServiceOffering._meta.get_field("valid_from").verbose_name == "valid from"


@pytest.mark.parametrize(
    "route,factory",
    [("visit_list", make_visit), ("assessment_list", make_assessment), ("plan_list", make_plan)],
)
def test_shared_display_code_links_filter_exact_enrollment(
    client, beneficiary_a, specialist_a, coordinator_a, center_a, route, factory
):
    from apps.casework.services import create_enrollment

    first = beneficiary_a.enrollments.get()
    second = create_enrollment(
        beneficiary=beneficiary_a,
        offering=center_a.service_offerings.get(service__code="HOME-CARE"),
        start_date=date(2026, 1, 1),
        actor=coordinator_a,
        status="active",
    )
    from .factories import capture_legacy_assignment

    capture_legacy_assignment(
        EnrollmentSpecialistAssignment.objects.create(
            enrollment=second, specialist=specialist_a, valid_from=date(2026, 1, 1)
        )
    )
    records = [
        factory(beneficiary_a, specialist_a, enrollment=enrollment)
        for enrollment in (first, second)
    ]
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    response = client.get(reverse(route), {"enrollment": second.pk})
    assert response.status_code == 200
    assert {row.pk for row in response.context["page_obj"]} == {records[1].pk}
    assert f'name="enrollment" value="{second.pk}"' in response.content.decode()
    page = client.get(
        reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}), {"enrollment": second.pk}
    )
    assert f"{reverse(route)}?enrollment={second.pk}" in page.content.decode()
    form = ServiceVisitForm(user=coordinator_a, center=center_a)
    choices = list(form.fields["enrollment"].choices)
    assert {str(value) for value, label in choices if value} == {str(first.pk), str(second.pk)}
    assert all(beneficiary_a.beneficiary_code in label for value, label in choices if value)


def test_old_code_searches_remain_authorized_and_exact_filters_deny_cross_center(
    client, beneficiary_a, beneficiary_b, specialist_a, specialist_b, coordinator_a, center_a
):
    first = beneficiary_a.enrollments.get()
    other = beneficiary_b.enrollments.get()
    ServiceEnrollment.objects.filter(pk=first.pk).update(episode_code="SYN-OLD-EPISODE")
    ServiceEnrollment.objects.filter(pk=other.pk).update(episode_code="SYN-HIDDEN-EPISODE")
    visit = make_visit(beneficiary_a, specialist_a)
    make_visit(beneficiary_b, specialist_b)
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    for query in ("SYN-OLD-EPISODE", beneficiary_a.legacy_beneficiary_code):
        for route in ("beneficiary_list", "visit_list"):
            response = client.get(reverse(route), {"q": query})
            expected = beneficiary_a.pk if route == "beneficiary_list" else visit.pk
            assert {row.pk for row in response.context["page_obj"]} == {expected}
        response = client.get(reverse("reports"), {"type": "enrollments", "q": query})
        assert {row.pk for row in response.context["rows"]} == {first.pk}
    for route in ("beneficiary_list", "visit_list"):
        response = client.get(reverse(route), {"q": "SYN-HIDDEN-EPISODE"})
        assert not list(response.context["page_obj"])
    assert client.get(reverse("visit_list"), {"enrollment": other.pk}).status_code == 404
    assert (
        client.post(
            reverse("enrollment_update", kwargs={"pk": other.pk}), {"notes": "Forged"}
        ).status_code
        == 404
    )


def test_legacy_intake_does_not_invent_a_date(client, coordinator_a, center_a, specialist_a):
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    response = client.post(
        reverse("beneficiary_create"),
        {
            "full_name": "Synthetic unknown intake date",
            "service_type": "other",
            "service_status": "active",
            "staffing-lead": str(specialist_a.pk),
            "staffing-effective_date": timezone.localdate().isoformat(),
        },
    )
    assert response.status_code == 200
    assert "start_date" in response.context["enrollment_form"].errors
    assert not ServiceEnrollment.objects.exists()


def test_exact_enrollment_filter_survives_pagination_and_form_submission(
    client, beneficiary_a, specialist_a, coordinator_a, center_a
):
    enrollment = beneficiary_a.enrollments.get()
    for day in range(1, 32):
        make_visit(beneficiary_a, specialist_a, visit_date=date(2026, 1, day))
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    response = client.get(
        reverse("visit_list"), {"enrollment": enrollment.pk, "q": beneficiary_a.beneficiary_code}
    )
    assert response.context["page_obj"].paginator.num_pages == 2
    body = response.content.decode()
    assert f"enrollment={enrollment.pk}&amp;q={beneficiary_a.beneficiary_code}&amp;page=2" in body
    second_page = client.get(reverse("visit_list"), {"enrollment": enrollment.pk, "page": 2})
    assert len(second_page.context["page_obj"]) == 1
    assert all(row.enrollment_id == enrollment.pk for row in second_page.context["page_obj"])
    assert client.get(reverse("visit_list"), {"enrollment": "malformed"}).status_code == 404


@pytest.mark.parametrize("language", ["en", "ka"])
def test_operational_pages_have_no_enrollment_code_entry(
    client, beneficiary_a, coordinator_a, center_a, language
):
    enrollment = beneficiary_a.enrollments.get()
    ServiceEnrollment.objects.filter(pk=enrollment.pk).update(
        status="exited", end_date=date(2026, 7, 1)
    )
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    with translation.override(language):
        for name, kwargs in [
            ("beneficiary_create", {}),
            ("enrollment_create", {"beneficiary_pk": beneficiary_a.pk}),
            ("enrollment_update", {"pk": enrollment.pk}),
            ("enrollment_reenroll", {"pk": enrollment.pk}),
        ]:
            response = client.get(reverse(name, kwargs=kwargs))
            assert response.status_code == 200
            body = response.content.decode()
            assert 'name="episode_code"' not in body
            assert 'name="enrollment-episode_code"' not in body
            assert ("Enrollment code" if language == "en" else "ჩარიცხვის კოდი") not in body
            code_label = "Beneficiary code" if language == "en" else "ბენეფიციარის კოდი"
            if name == "beneficiary_create":
                assert code_label not in body
                assert 'name="beneficiary_code"' not in body
            else:
                assert code_label in body
            if name != "enrollment_update":
                assert ("Enrollment date" if language == "en" else "ჩარიცხვის თარიღი") in body
        invalid = EnrollmentIntakeForm(
            _intake(
                center_a.service_offerings.get(service=enrollment.service),
                first_service_date="01/02/2026",
            ),
            center=center_a,
        )
        assert not invalid.is_valid()
        assert ("enrollment date" if language == "en" else "ჩარიცხვის თარიღზე") in str(
            invalid.errors["first_service_date"]
        )
