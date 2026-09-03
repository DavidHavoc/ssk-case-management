from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.db.models import Q, QuerySet
from django.urls import reverse
from django.utils.translation import gettext as _

from .models import (
    Assessment,
    AttachmentParentType,
    EnrollmentSpecialistAssignment,
    IndividualPlan,
    PrivateAttachment,
    ServiceEnrollment,
    ServiceVisit,
)


@dataclass(frozen=True, slots=True)
class WorkspaceAlert:
    label: str
    status_key: str


@dataclass(frozen=True, slots=True)
class EnrollmentWorkspaceRow:
    enrollment: ServiceEnrollment
    current_assignments: tuple[EnrollmentSpecialistAssignment, ...]
    latest_visit: ServiceVisit | None
    next_planned_visit: ServiceVisit | None
    latest_assessment: Assessment | None
    assessment_due_date: date | None
    active_plan: IndividualPlan | None
    latest_plan: IndividualPlan | None
    next_due_label: str
    next_due_date: date | None
    assessment_overdue: bool
    review_overdue: bool
    alerts: tuple[WorkspaceAlert, ...]

    @property
    def displayed_plan(self) -> IndividualPlan | None:
        return self.active_plan or self.latest_plan


@dataclass(frozen=True, slots=True)
class WorkspaceDocument:
    attachment: PrivateAttachment
    source_label: str
    source_url: str


def _first_by_enrollment(rows, *, predicate=None):
    result = {}
    for row in rows:
        if row.enrollment_id in result:
            continue
        if predicate is None or predicate(row):
            result[row.enrollment_id] = row
    return result


def build_enrollment_workspace_rows(
    enrollments,
    *,
    visits: QuerySet,
    assessments: QuerySet,
    plans: QuerySet,
    as_of: date,
) -> list[EnrollmentWorkspaceRow]:
    """Build authorized workspace summaries from already scoped querysets."""
    enrollment_rows = list(enrollments)
    enrollment_ids = [row.pk for row in enrollment_rows]
    if not enrollment_ids:
        return []

    scoped_visits = list(
        visits.filter(enrollment_id__in=enrollment_ids)
        .select_related("activity", "specialist__staff_profile__user")
        .order_by("enrollment_id", "-visit_date", "-created_at")
    )
    latest_visits = _first_by_enrollment(scoped_visits)
    planned_visits = _first_by_enrollment(
        row
        for row in scoped_visits
        if row.status == ServiceVisit.Status.PLANNED and row.visit_date >= as_of
    )

    scoped_assessments = list(
        assessments.filter(enrollment_id__in=enrollment_ids)
        .select_related("template_version__instrument")
        .order_by("enrollment_id", "-assessment_date", "-created_at")
    )
    latest_assessments = _first_by_enrollment(scoped_assessments)

    scoped_plans = list(
        plans.filter(enrollment_id__in=enrollment_ids)
        .select_related("specialist__staff_profile__user")
        .prefetch_related("goals")
        .order_by("enrollment_id", "-plan_start_date", "-created_at")
    )
    latest_plans = _first_by_enrollment(scoped_plans)
    active_plans = _first_by_enrollment(
        row for row in scoped_plans if row.status == IndividualPlan.Status.ACTIVE
    )

    current_assignments = {}
    assignments = (
        EnrollmentSpecialistAssignment.objects.filter(
            enrollment_id__in=enrollment_ids,
            valid_from__lte=as_of,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=as_of))
        .select_related("specialist__staff_profile__user")
        .order_by("assignment_role", "specialist__staff_profile__user__last_name")
    )
    for assignment in assignments:
        current_assignments.setdefault(assignment.enrollment_id, []).append(assignment)

    results = []
    for enrollment in enrollment_rows:
        assessment = latest_assessments.get(enrollment.pk)
        active_plan = active_plans.get(enrollment.pk)
        assessment_due_date = assessment.next_review_date if assessment else None
        review_due_date = active_plan.review_due_date if active_plan else None
        planned_visit = planned_visits.get(enrollment.pk)
        due_candidates = []
        if assessment_due_date:
            due_candidates.append((assessment_due_date, str(_("Assessment review"))))
        if review_due_date:
            due_candidates.append((review_due_date, str(_("Plan review"))))
        if planned_visit:
            due_candidates.append((planned_visit.visit_date, str(_("Planned visit"))))
        next_due_date, next_due_label = (
            min(due_candidates, key=lambda candidate: candidate[0])
            if due_candidates
            else (None, str(_("No due work recorded")))
        )
        assessment_overdue = bool(assessment_due_date and assessment_due_date < as_of)
        review_overdue = bool(review_due_date and review_due_date < as_of)
        alerts = []
        if assessment_overdue:
            alerts.append(WorkspaceAlert(str(_("Assessment review overdue")), "danger"))
        if review_overdue:
            alerts.append(WorkspaceAlert(str(_("Plan review overdue")), "danger"))
        results.append(
            EnrollmentWorkspaceRow(
                enrollment=enrollment,
                current_assignments=tuple(current_assignments.get(enrollment.pk, ())),
                latest_visit=latest_visits.get(enrollment.pk),
                next_planned_visit=planned_visit,
                latest_assessment=assessment,
                assessment_due_date=assessment_due_date,
                active_plan=active_plan,
                latest_plan=latest_plans.get(enrollment.pk),
                next_due_label=next_due_label,
                next_due_date=next_due_date,
                assessment_overdue=assessment_overdue,
                review_overdue=review_overdue,
                alerts=tuple(alerts),
            )
        )
    return results


def build_workspace_documents(
    related_attachments,
    *,
    beneficiary_attachments=(),
    beneficiary_id,
) -> list[WorkspaceDocument]:
    documents = [
        WorkspaceDocument(
            attachment=attachment,
            source_label=str(_("Beneficiary record")),
            source_url=reverse("beneficiary_detail", kwargs={"pk": beneficiary_id}) + "#documents",
        )
        for attachment in beneficiary_attachments
    ]
    routes = {
        AttachmentParentType.SERVICE_VISIT: ("visit_detail", _("Service visit")),
        AttachmentParentType.ASSESSMENT: ("assessment_detail", _("Assessment")),
        AttachmentParentType.INDIVIDUAL_PLAN: ("plan_detail", _("Individual plan")),
    }
    for attachment in related_attachments:
        route, label = routes[attachment.parent_type]
        documents.append(
            WorkspaceDocument(
                attachment=attachment,
                source_label=str(label),
                source_url=reverse(route, kwargs={"pk": attachment.parent_id}),
            )
        )
    return sorted(documents, key=lambda row: row.attachment.created_at, reverse=True)
