from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.accounts.roles import is_coordinator, is_system_manager
from apps.casework.models import Assessment, IndividualPlan, ServiceEnrollment

from .authorization import (
    current_assessments_for_user,
    enrollments_for_user,
    plans_for_user,
    staff_contracts_for_user,
)
from .reporting import data_quality_exception_rows


@dataclass(frozen=True)
class InApplicationReminder:
    category: str
    category_label: str
    urgency: str
    title: str
    detail: str
    due_date: date | None
    url: str


def authorized_reminders(user, center, *, as_of: date) -> list[InApplicationReminder]:
    """Build current reminders from authorized querysets without any delivery side effect."""
    horizon = as_of + timedelta(days=getattr(settings, "SSK_REMINDER_UPCOMING_DAYS", 30))
    enrollments = enrollments_for_user(user, center)
    assessments = current_assessments_for_user(user, center)
    plans = plans_for_user(user, center)
    reminders = []

    latest_assessments = {}
    for assessment in assessments.filter(
        status=Assessment.Status.COMPLETED,
        next_review_date__isnull=False,
    ).order_by("enrollment_id", "-assessment_date", "-created_at"):
        latest_assessments.setdefault(assessment.enrollment_id, assessment)
    for assessment in latest_assessments.values():
        if assessment.next_review_date >= as_of:
            continue
        reminders.append(
            InApplicationReminder(
                category="assessment",
                category_label=str(_("Assessments")),
                urgency="danger",
                title=str(_("Assessment review overdue")),
                detail=(
                    f"{assessment.beneficiary.beneficiary_code}"
                    f" | {assessment.enrollment.episode_code}"
                ),
                due_date=assessment.next_review_date,
                url=reverse("assessment_detail", kwargs={"pk": assessment.pk}),
            )
        )

    for plan in plans.filter(
        status=IndividualPlan.Status.ACTIVE,
        review_due_date__isnull=False,
        review_due_date__lte=horizon,
    ):
        reminders.append(
            InApplicationReminder(
                category="plan_review",
                category_label=str(_("Plan reviews")),
                urgency="danger" if plan.review_due_date < as_of else "warning",
                title=(
                    str(_("Plan review overdue"))
                    if plan.review_due_date < as_of
                    else str(_("Plan review upcoming"))
                ),
                detail=f"{plan.beneficiary.beneficiary_code} | {plan.enrollment.episode_code}",
                due_date=plan.review_due_date,
                url=reverse("plan_detail", kwargs={"pk": plan.pk}),
            )
        )

    for enrollment in enrollments.filter(
        status__in=(
            ServiceEnrollment.Status.PENDING,
            ServiceEnrollment.Status.ACTIVE,
            ServiceEnrollment.Status.SUSPENDED,
        ),
        end_date__isnull=False,
        end_date__lte=horizon,
    ):
        reminders.append(
            InApplicationReminder(
                category="enrollment",
                category_label=str(_("Enrollments")),
                urgency="danger" if enrollment.end_date < as_of else "warning",
                title=(
                    str(_("Enrollment end date has passed"))
                    if enrollment.end_date < as_of
                    else str(_("Enrollment expires soon"))
                ),
                detail=f"{enrollment.beneficiary.beneficiary_code} | {enrollment.episode_code}",
                due_date=enrollment.end_date,
                url=reverse(
                    "beneficiary_detail",
                    kwargs={"pk": enrollment.beneficiary_id},
                )
                + f"?enrollment={enrollment.pk}",
            )
        )

    for staff in staff_contracts_for_user(user, center).filter(
        contract_valid_until__isnull=False,
        contract_valid_until__lte=horizon,
    ):
        can_open_staff = is_system_manager(user) or is_coordinator(user)
        reminders.append(
            InApplicationReminder(
                category="contract",
                category_label=str(_("Contracts")),
                urgency="danger" if staff.contract_valid_until < as_of else "warning",
                title=(
                    str(_("Staff contract has expired"))
                    if staff.contract_valid_until < as_of
                    else str(_("Staff contract expires soon"))
                ),
                detail=f"{staff.employee_number} | {staff.display_name}",
                due_date=staff.contract_valid_until,
                url=(reverse("staff_detail", kwargs={"pk": staff.pk}) if can_open_staff else ""),
            )
        )

    include_restricted_operations = is_system_manager(user) or is_coordinator(user)
    exceptions = data_quality_exception_rows(
        enrollments,
        assessments,
        plans,
        center=center,
        as_of=as_of,
        include_restricted_operations=include_restricted_operations,
    )
    for exception in exceptions:
        if exception.issue_code in {"assessment_review", "plan_review"}:
            continue
        reminders.append(
            InApplicationReminder(
                category="data_quality",
                category_label=str(_("Data quality")),
                urgency=exception.severity,
                title=exception.issue,
                detail=f"{exception.beneficiary_code} | {exception.enrollment_code}",
                due_date=exception.due_date,
                url=exception.url,
            )
        )
    return sorted(
        reminders,
        key=lambda reminder: (
            0 if reminder.urgency == "danger" else 1,
            reminder.due_date or date.max,
            reminder.category,
            reminder.detail,
        ),
    )
