from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone, translation

from apps.accounts.roles import COORDINATOR
from apps.casework.models import (
    CenterServiceOffering,
    EnrollmentSpecialistAssignment,
    ServiceEnrollment,
    ServiceVisit,
)
from apps.casework.services import create_enrollment, transition_enrollment

from .factories import (
    add_specialist_center,
    ensure_visit_catalogs,
    make_assessment,
    make_beneficiary,
    make_plan,
    make_specialist,
    make_visit,
    set_active_center,
)

pytestmark = pytest.mark.django_db

PASSWORD = "Synthetic-Test-Password-42!"


def _login(client, user):
    return client.post(
        reverse("login"),
        {"username": user.username, "password": PASSWORD},
    )


def test_specialist_login_goes_directly_to_assigned_beneficiaries(
    client,
    specialist_a,
    beneficiary_a,
):
    response = _login(client, specialist_a.staff_profile.user)

    assert response.status_code == 302
    assert response.url == reverse("specialist_workspace")
    workspace = client.get(response.url)
    assert workspace.status_code == 200
    assert beneficiary_a.full_name in workspace.content.decode()


def test_multi_center_specialist_selects_center_then_returns_to_workspace(
    client,
    specialist_a,
    center_a,
    center_b,
    beneficiary_a,
):
    add_specialist_center(specialist_a, center_b)
    login = _login(client, specialist_a.staff_profile.user)

    selection = client.get(login.url)
    assert selection.status_code == 302
    assert selection.url.startswith(reverse("center_select"))
    assert "my-beneficiaries" in selection.url

    response = client.post(
        reverse("center_select"),
        {"center": str(center_a.pk), "next": reverse("specialist_workspace")},
    )
    assert response.status_code == 302
    assert response.url == reverse("specialist_workspace")
    assert beneficiary_a.full_name in client.get(response.url).content.decode()


@pytest.mark.parametrize("role_fixture", ["coordinator_a", "manager"])
def test_management_roles_retain_dashboard(
    request,
    client,
    role_fixture,
    center_a,
    beneficiary_a,
):
    user = request.getfixturevalue(role_fixture)
    response = _login(client, user)

    assert response.status_code == 302
    assert response.url == reverse("dashboard")
    dashboard = client.get(response.url)
    assert dashboard.status_code == 200
    assert "Center metrics" in dashboard.content.decode()


def test_mixed_role_defaults_to_dashboard_and_can_open_bounded_specialist_workspace(
    client,
    specialist_a,
    center_a,
    beneficiary_a,
):
    user = specialist_a.staff_profile.user
    user.groups.add(Group.objects.get(name=COORDINATOR))

    login = _login(client, user)
    assert login.url == reverse("dashboard")

    dashboard = client.get(login.url)
    assert dashboard.status_code == 200
    assert reverse("specialist_workspace") in dashboard.content.decode()
    workspace = client.get(reverse("specialist_workspace"))
    assert workspace.status_code == 200
    assert beneficiary_a.full_name in workspace.content.decode()


def test_assigned_workspace_excludes_same_center_unassigned_beneficiary(
    client,
    specialist_a,
    center_a,
    beneficiary_a,
):
    other_specialist = make_specialist(center_a, "workspace-other")
    other_beneficiary = make_beneficiary(
        center_a,
        other_specialist,
        name="Synthetic Unassigned Beneficiary",
    )
    client.force_login(specialist_a.staff_profile.user)
    set_active_center(client, center_a)

    response = client.get(reverse("specialist_workspace"))
    body = response.content.decode()

    assert response.status_code == 200
    assert beneficiary_a.full_name in body
    assert other_beneficiary.full_name not in body
    assert beneficiary_a.personal_id not in body
    assert beneficiary_a.address not in body
    assert beneficiary_a.application_contract_number not in body


def test_beneficiary_workspace_has_semantic_navigation_and_contextual_actions(
    client,
    specialist_a,
    center_a,
    beneficiary_a,
):
    client.force_login(specialist_a.staff_profile.user)
    set_active_center(client, center_a)
    enrollment = beneficiary_a.enrollments.get()

    response = client.get(
        reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}),
        {"enrollment": enrollment.pk},
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert body.count("<h1>") == 1
    assert 'class="workspace-nav"' in body
    for anchor in (
        "#overview",
        "#enrollments",
        "#visits-schedules",
        "#assessments",
        "#plans-goals",
        "#documents",
        "#timeline",
    ):
        assert f'href="{anchor}"' in body
    assert f"{reverse('visit_create')}?enrollment={enrollment.pk}" in body
    assert f"{reverse('assessment_create')}?enrollment={enrollment.pk}" in body
    assert f"{reverse('plan_create')}?enrollment={enrollment.pk}" in body
    assert 'class="status status-active"' in body
    assert beneficiary_a.personal_id not in body
    assert beneficiary_a.address not in body


def test_specialist_workspace_context_excludes_unassigned_service_on_same_identity(
    client,
    specialist_a,
    coordinator_a,
    center_a,
    beneficiary_a,
):
    other_specialist = make_specialist(center_a, "other-service-specialist")
    offering = CenterServiceOffering.objects.get(
        center=center_a,
        service__code="HOME-CARE",
    )
    hidden_enrollment = create_enrollment(
        beneficiary=beneficiary_a,
        offering=offering,
        episode_code=f"{beneficiary_a.beneficiary_code}-HIDDEN",
        start_date=date(2026, 1, 1),
        status=ServiceEnrollment.Status.ACTIVE,
        application_contract_number="SYNTHETIC-HIDDEN-CONTRACT",
        notes="Synthetic hidden service notes.",
        actor=coordinator_a,
    )
    EnrollmentSpecialistAssignment.objects.create(
        enrollment=hidden_enrollment,
        specialist=other_specialist,
        valid_from=date(2026, 1, 1),
    )
    visible_enrollment = beneficiary_a.enrollments.exclude(pk=hidden_enrollment.pk).get()
    client.force_login(specialist_a.staff_profile.user)
    set_active_center(client, center_a)

    response = client.get(
        reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}),
        {"enrollment": visible_enrollment.pk},
    )
    context_enrollment_ids = {row.pk for row in response.context["enrollments"]}
    body = response.content.decode()

    assert response.status_code == 200
    assert context_enrollment_ids == {visible_enrollment.pk}
    assert hidden_enrollment.episode_code not in body
    assert hidden_enrollment.application_contract_number not in body
    assert hidden_enrollment.notes not in body
    denied = client.get(
        reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}),
        {"enrollment": hidden_enrollment.pk},
    )
    assert denied.status_code == 404


@pytest.mark.parametrize("route", ["visit_create", "assessment_create", "plan_create"])
def test_contextual_create_forms_prefill_only_an_authorized_enrollment(
    client,
    route,
    specialist_a,
    center_a,
    beneficiary_a,
    beneficiary_b,
):
    client.force_login(specialist_a.staff_profile.user)
    set_active_center(client, center_a)
    enrollment = beneficiary_a.enrollments.get()

    allowed = client.get(reverse(route), {"enrollment": enrollment.pk})
    denied = client.get(
        reverse(route),
        {"enrollment": beneficiary_b.enrollments.get().pk},
    )

    assert allowed.status_code == 200
    assert allowed.context["form"].instance.enrollment_id == enrollment.pk
    assert denied.status_code == 404


def test_suspended_enrollment_hides_actions_and_rejects_direct_visit_post(
    client,
    specialist_a,
    center_a,
    beneficiary_a,
):
    user = specialist_a.staff_profile.user
    enrollment = beneficiary_a.enrollments.get()
    today = timezone.localdate()
    transition_enrollment(
        enrollment,
        new_state=ServiceEnrollment.Status.SUSPENDED,
        effective_date=today,
        reason="Synthetic daily-workflow suspension",
        actor=user,
    )
    activity, location = ensure_visit_catalogs()
    client.force_login(user)
    set_active_center(client, center_a)

    detail = client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}))
    body = detail.content.decode()
    assert detail.status_code == 200
    assert f"{reverse('visit_create')}?enrollment={enrollment.pk}" not in body
    assert f"{reverse('assessment_create')}?enrollment={enrollment.pk}" not in body
    assert f"{reverse('plan_create')}?enrollment={enrollment.pk}" not in body

    response = client.post(
        reverse("visit_create"),
        {
            "enrollment": enrollment.pk,
            "specialist": specialist_a.pk,
            "visit_date": today.isoformat(),
            "activity": activity.pk,
            "delivery_location": location.pk,
            "participation_format": "individual",
            "status": ServiceVisit.Status.COMPLETED,
            "service_units": "1",
            "duration_minutes": "30",
            "participants": "1",
            "notes": "Synthetic denied visit.",
        },
    )
    assert response.status_code == 200
    assert "not effective on the selected record date" in response.content.decode()
    assert not ServiceVisit.objects.filter(notes="Synthetic denied visit.").exists()


def test_workspace_surfaces_due_work_latest_activity_plan_and_responsibility(
    client,
    coordinator_a,
    specialist_a,
    center_a,
    beneficiary_a,
):
    today = timezone.localdate()
    visit = make_visit(beneficiary_a, specialist_a, visit_date=today - timedelta(days=2))
    assessment = make_assessment(
        beneficiary_a,
        specialist_a,
        assessment_date=today - timedelta(days=30),
    )
    assessment.next_review_date = today + timedelta(days=5)
    assessment.save(update_fields=["next_review_date", "updated_at"])
    plan = make_plan(beneficiary_a, specialist_a)
    plan.review_due_date = today - timedelta(days=1)
    plan.save(update_fields=["review_due_date", "updated_at"])
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    response = client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}))
    body = response.content.decode()

    assert response.status_code == 200
    assert visit.visit_date.strftime("%d/%m/%Y") in body
    assert assessment.next_review_date.strftime("%d/%m/%Y") in body
    assert "Plan review" in body
    assert "Overdue" in body
    assert plan.get_status_display() in body
    assert str(specialist_a) in body


def test_georgian_workspace_labels_and_responsive_contract_render(
    client,
    specialist_a,
    center_a,
    beneficiary_a,
    settings,
):
    client.force_login(specialist_a.staff_profile.user)
    set_active_center(client, center_a)

    with translation.override("ka"):
        response = client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}))

    body = response.content.decode()
    assert response.status_code == 200
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in body
    assert "ბენეფიციარის სამუშაო სივრცე" in body
    assert "მიმოხილვა" in body
    assert "ვიზიტები და გრაფიკები" in body
    assert "გეგმები და მიზნები" in body
    assert "დოკუმენტები" in body
    assert "ავტორიზებული ქრონოლოგია" in body
    css = (settings.BASE_DIR / "static/css/app.css").read_text()
    assert "@media (max-width: 48rem)" in css
    assert ".workspace-nav" in css
    assert ":focus-visible" in css
