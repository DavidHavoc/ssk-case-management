from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation

from apps.casework.models import (
    AttachmentParentType,
    PrivateAttachment,
)
from apps.casework.timeline import (
    ASSESSMENT,
    ATTACHMENT,
    INDIVIDUAL_PLAN,
    PLAN_GOAL,
    SERVICE_VISIT,
    TIMELINE_PAGE_SIZE,
)

from .factories import (
    make_assessment,
    make_plan,
    make_specialist,
    make_visit,
    set_active_center,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def private_media_root(tmp_path, settings):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    return settings.PRIVATE_MEDIA_ROOT


def _attachment(*, parent, parent_type: str, user, filename: str) -> PrivateAttachment:
    return PrivateAttachment.objects.create(
        parent_type=parent_type,
        parent_id=parent.pk,
        center=parent.center if hasattr(parent, "center") else parent.primary_center,
        document_type=(
            PrivateAttachment.DocumentType.ADDITIONAL_DOCUMENTATION
            if parent_type == AttachmentParentType.STAFF_PROFILE
            else ""
        ),
        file=SimpleUploadedFile(
            filename,
            b"%PDF-1.7\nSynthetic timeline document",
            content_type="application/pdf",
        ),
        original_filename=filename,
        content_type="application/pdf",
        uploaded_by=user,
    )


def _timeline_entries(response):
    return list(response.context["timeline_page"].object_list)


def _make_complete_activity(beneficiary, specialist, uploader):
    visit = make_visit(beneficiary, specialist, visit_date=date(2026, 2, 10))
    assessment = make_assessment(
        beneficiary,
        specialist,
        assessment_date=date(2026, 2, 5),
    )
    plan = make_plan(beneficiary, specialist)
    goal = plan.goals.get()
    goal.target_date = date(2026, 3, 1)
    goal.goal = "Synthetic timeline goal"
    goal.save()
    attachment = _attachment(
        parent=assessment,
        parent_type=AttachmentParentType.ASSESSMENT,
        user=uploader,
        filename="assessment-timeline.pdf",
    )
    PrivateAttachment.objects.filter(pk=attachment.pk).update(
        created_at=datetime(2026, 2, 7, 12, tzinfo=UTC)
    )
    attachment.refresh_from_db()
    return visit, assessment, plan, goal, attachment


@pytest.mark.parametrize("role_fixture", ["coordinator_a", "manager"])
def test_coordinator_and_manager_see_complete_authorized_timeline(
    request,
    role_fixture,
    client,
    center_a,
    specialist_a,
    beneficiary_a,
):
    user = request.getfixturevalue(role_fixture)
    visit, assessment, plan, goal, attachment = _make_complete_activity(
        beneficiary_a, specialist_a, user
    )
    client.force_login(user)
    set_active_center(client, center_a)

    response = client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}))

    assert response.status_code == 200
    entries = _timeline_entries(response)
    assert [entry.stable_identifier for entry in entries] == [
        f"{PLAN_GOAL}:{goal.pk}",
        f"{SERVICE_VISIT}:{visit.pk}",
        f"{ATTACHMENT}:{attachment.pk}",
        f"{ASSESSMENT}:{assessment.pk}",
        f"{INDIVIDUAL_PLAN}:{plan.pk}",
    ]
    assert {entry.entry_type for entry in entries} == {
        SERVICE_VISIT,
        ASSESSMENT,
        INDIVIDUAL_PLAN,
        PLAN_GOAL,
        ATTACHMENT,
    }
    assert {entry.stable_identifier for entry in entries} == {
        f"{SERVICE_VISIT}:{visit.pk}",
        f"{ASSESSMENT}:{assessment.pk}",
        f"{INDIVIDUAL_PLAN}:{plan.pk}",
        f"{PLAN_GOAL}:{goal.pk}",
        f"{ATTACHMENT}:{attachment.pk}",
    }
    assert entries[2].display_date == attachment.created_at


def test_specialist_sees_case_attachments_but_not_beneficiary_or_staff_attachments(
    client,
    coordinator_a,
    specialist_a,
    center_a,
    beneficiary_a,
):
    user = specialist_a.staff_profile.user
    visit = make_visit(beneficiary_a, specialist_a, visit_date=date(2026, 4, 1))
    assessment = make_assessment(beneficiary_a, specialist_a, assessment_date=date(2026, 4, 2))
    plan = make_plan(beneficiary_a, specialist_a)
    beneficiary_attachment = _attachment(
        parent=beneficiary_a,
        parent_type=AttachmentParentType.BENEFICIARY,
        user=coordinator_a,
        filename="beneficiary-hidden.pdf",
    )
    authorized_attachments = [
        _attachment(
            parent=visit,
            parent_type=AttachmentParentType.SERVICE_VISIT,
            user=coordinator_a,
            filename="visit-visible.pdf",
        ),
        _attachment(
            parent=assessment,
            parent_type=AttachmentParentType.ASSESSMENT,
            user=coordinator_a,
            filename="assessment-visible.pdf",
        ),
        _attachment(
            parent=plan,
            parent_type=AttachmentParentType.INDIVIDUAL_PLAN,
            user=coordinator_a,
            filename="plan-visible.pdf",
        ),
    ]
    staff_attachment = _attachment(
        parent=coordinator_a.staff_profile,
        parent_type=AttachmentParentType.STAFF_PROFILE,
        user=coordinator_a,
        filename="staff-hidden.pdf",
    )
    client.force_login(user)
    set_active_center(client, center_a)

    response = client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}))

    assert response.status_code == 200
    body = response.content.decode()
    attachment_entries = [
        entry for entry in _timeline_entries(response) if entry.entry_type == ATTACHMENT
    ]
    assert {entry.title for entry in attachment_entries} == {
        attachment.original_filename for attachment in authorized_attachments
    }
    for attachment in authorized_attachments:
        assert reverse("attachment_download", kwargs={"pk": attachment.pk}) in body
    assert beneficiary_attachment.original_filename not in body
    assert staff_attachment.original_filename not in body
    assert beneficiary_a.personal_id not in body
    assert beneficiary_a.address not in body
    assert beneficiary_a.email not in body


def test_timeline_enforces_cross_center_and_unassigned_specialist_isolation(
    client,
    center_a,
    beneficiary_a,
    specialist_a,
    specialist_b,
):
    same_center_unassigned = make_specialist(center_a, "timeline-unassigned")
    make_visit(beneficiary_a, specialist_a)

    client.force_login(specialist_b.staff_profile.user)
    set_active_center(client, specialist_b.staff_profile.primary_center)
    cross_center = client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}))

    client.force_login(same_center_unassigned.staff_profile.user)
    set_active_center(client, center_a)
    unassigned = client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}))

    assert cross_center.status_code == 404
    assert unassigned.status_code == 404


def test_timeline_order_is_newest_first_and_deterministic_for_ties(
    client,
    coordinator_a,
    center_a,
    specialist_a,
    beneficiary_a,
):
    older = make_visit(beneficiary_a, specialist_a, visit_date=date(2026, 5, 1))
    tied_visit = make_visit(beneficiary_a, specialist_a, visit_date=date(2026, 6, 1))
    tied_assessment = make_assessment(
        beneficiary_a,
        specialist_a,
        assessment_date=date(2026, 6, 1),
    )
    tied_created_at = datetime(2026, 6, 2, 9, tzinfo=UTC)
    type(tied_visit).objects.filter(pk=tied_visit.pk).update(created_at=tied_created_at)
    type(tied_assessment).objects.filter(pk=tied_assessment.pk).update(created_at=tied_created_at)
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    response = client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}))

    identifiers = [entry.stable_identifier for entry in _timeline_entries(response)]
    assert identifiers[:3] == [
        f"{SERVICE_VISIT}:{tied_visit.pk}",
        f"{ASSESSMENT}:{tied_assessment.pk}",
        f"{SERVICE_VISIT}:{older.pk}",
    ]


def test_goal_without_target_date_falls_back_to_plan_start_date(
    client,
    coordinator_a,
    center_a,
    specialist_a,
    beneficiary_a,
):
    plan = make_plan(beneficiary_a, specialist_a)
    goal = plan.goals.get()
    goal.target_date = None
    goal.save()
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    response = client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}))

    goal_entry = next(
        entry for entry in _timeline_entries(response) if entry.entry_type == PLAN_GOAL
    )
    assert goal_entry.display_date == plan.plan_start_date


def test_empty_timeline_has_accessible_empty_state(client, coordinator_a, center_a, beneficiary_a):
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    response = client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}))

    assert response.context["timeline_page"].paginator.count == 0
    body = response.content.decode()
    assert 'class="empty-state compact" role="status"' in body
    assert "No case activity yet" in body


def test_timeline_paginates_and_preserves_query_parameters(
    client, coordinator_a, center_a, specialist_a, beneficiary_a
):
    for day in range(1, TIMELINE_PAGE_SIZE + 2):
        make_visit(beneficiary_a, specialist_a, visit_date=date(2026, 7, day))
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    first = client.get(
        reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}),
        {"context": "timeline", "timeline_page": 1},
    )
    second = client.get(
        reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}),
        {"context": "timeline", "timeline_page": 2},
    )

    assert len(_timeline_entries(first)) == TIMELINE_PAGE_SIZE
    assert len(_timeline_entries(second)) == 1
    assert first.context["timeline_page"].has_next()
    assert second.context["timeline_page"].has_previous()
    body = first.content.decode()
    assert "context=timeline" in body
    assert "timeline_page=2" in body


def test_timeline_html_exposes_display_name_but_not_private_file_metadata(
    client,
    coordinator_a,
    center_a,
    beneficiary_a,
    private_media_root,
):
    attachment = _attachment(
        parent=beneficiary_a,
        parent_type=AttachmentParentType.BENEFICIARY,
        user=coordinator_a,
        filename="safe-display-name.pdf",
    )
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    response = client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}))

    body = response.content.decode()
    assert attachment.original_filename in body
    assert attachment.file.name not in body
    assert str(Path(private_media_root)) not in body
    assert attachment.sha256 not in body


def test_timeline_query_count_does_not_grow_per_entry(
    client, coordinator_a, center_a, specialist_a, beneficiary_a
):
    make_visit(beneficiary_a, specialist_a, visit_date=date(2026, 8, 1))
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    detail_url = reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk})
    with CaptureQueriesContext(connection) as baseline:
        assert client.get(detail_url).status_code == 200

    for day in range(2, 29):
        make_visit(beneficiary_a, specialist_a, visit_date=date(2026, 8, day))
    with CaptureQueriesContext(connection) as expanded:
        assert client.get(detail_url).status_code == 200

    assert len(expanded) <= len(baseline) + 2


def test_georgian_timeline_labels_render(
    client, coordinator_a, center_a, specialist_a, beneficiary_a
):
    make_visit(beneficiary_a, specialist_a)
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    with translation.override("ka"):
        response = client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}))

    body = response.content.decode()
    assert "საქმის აქტივობების ქრონოლოგია" in body
    assert "მომსახურების ვიზიტი" in body
    assert "ჩანაწერის ნახვა" in body
