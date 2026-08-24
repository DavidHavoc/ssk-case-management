from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

from django.db.models import QuerySet
from django.utils.translation import gettext as _

from apps.casework.models import IndividualPlanGoal


@dataclass(frozen=True)
class PlanOutcomeReportRow:
    plan: object
    category: object | None
    total_goals: int
    planned_goals: int
    in_progress_goals: int
    achieved_goals: int
    deferred_goals: int
    cancelled_goals: int
    condition_outcome: str

    @property
    def category_label(self):
        return self.category or _("Overall")


def plan_outcome_rows(queryset: QuerySet, *, as_of: date | None = None):
    plans = queryset.prefetch_related(
        "goals__category",
        "goals__status_history",
        "reviews",
    )
    rows = []
    for plan in plans:
        statuses_by_category = {}
        all_statuses = []
        for goal in plan.goals.all():
            if as_of and goal.created_at.date() > as_of:
                continue
            status = goal.status
            if as_of:
                transition = next(
                    (
                        item
                        for item in reversed(list(goal.status_history.all()))
                        if item.transition_date <= as_of
                    ),
                    None,
                )
                if transition:
                    status = transition.to_status
            statuses_by_category.setdefault(goal.category, []).append(status)
            all_statuses.append(status)
        reviews = [
            review for review in plan.reviews.all() if as_of is None or review.review_date <= as_of
        ]
        latest_review = max(
            reviews, key=lambda review: (review.review_date, review.created_at), default=None
        )
        outcome = (
            latest_review.get_condition_outcome_display()
            if latest_review
            else _("Not yet assessed")
        )
        for category, statuses in sorted(
            statuses_by_category.items(),
            key=lambda item: (item[0].reporting_order, item[0].name_en),
        ):
            rows.append(_plan_outcome_row(plan, category, statuses, outcome))
        rows.append(_plan_outcome_row(plan, None, all_statuses, outcome))
    return rows


def _plan_outcome_row(plan, category, statuses, outcome):
    return PlanOutcomeReportRow(
        plan=plan,
        category=category,
        total_goals=len(statuses),
        planned_goals=statuses.count(IndividualPlanGoal.Status.PLANNED),
        in_progress_goals=statuses.count(IndividualPlanGoal.Status.IN_PROGRESS),
        achieved_goals=statuses.count(IndividualPlanGoal.Status.ACHIEVED),
        deferred_goals=statuses.count(IndividualPlanGoal.Status.DEFERRED),
        cancelled_goals=statuses.count(IndividualPlanGoal.Status.CANCELLED),
        condition_outcome=outcome,
    )


def safe_csv_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        text = value.strftime("%d/%m/%Y %H:%M")
    elif isinstance(value, date):
        text = value.strftime("%d/%m/%Y")
    else:
        text = str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return f"'{text}"
    return text


def report_headers(report_type: str) -> list[str]:
    return {
        "beneficiaries": [
            _("Person code"),
            _("Name"),
            _("Age"),
            _("SSK age band"),
            _("Region"),
            _("Municipality"),
        ],
        "enrollments": [
            _("Enrollment code"),
            _("Person code"),
            _("Beneficiary"),
            _("Service"),
            _("Status"),
            _("Start date"),
            _("End date"),
        ],
        "visits": [
            _("Beneficiary code"),
            _("Beneficiary"),
            _("Enrollment code"),
            _("Service"),
            _("Specialist"),
            _("Visit date"),
            _("Activity"),
            _("Delivery location"),
            _("Format"),
            _("Status"),
            _("Units"),
            _("Duration minutes"),
            _("Participants"),
            _("Cancellation reason"),
        ],
        "assessments": [
            _("Beneficiary code"),
            _("Beneficiary"),
            _("Enrollment code"),
            _("Service"),
            _("Specialist"),
            _("Date"),
            _("Type"),
            _("Instrument"),
            _("Template version"),
            _("Total score"),
            _("Classification"),
            _("Delayed domains"),
        ],
        "plans": [
            _("Beneficiary code"),
            _("Beneficiary"),
            _("Enrollment code"),
            _("Service"),
            _("Specialist"),
            _("Status"),
            _("Start date"),
            _("End date"),
            _("Review frequency"),
        ],
        "plan_outcomes": [
            _("Beneficiary code"),
            _("Beneficiary"),
            _("Enrollment code"),
            _("Service"),
            _("Plan version"),
            _("Plan status"),
            _("Category"),
            _("Total goals"),
            _("Planned goals"),
            _("In-progress goals"),
            _("Achieved goals"),
            _("Deferred goals"),
            _("Cancelled goals"),
            _("Child condition outcome"),
        ],
    }[report_type]


def report_rows(report_type: str, queryset: QuerySet) -> Iterable[list[str]]:
    if report_type == "plan_outcomes":
        for row in queryset:
            values = [
                row.plan.beneficiary.beneficiary_code,
                row.plan.beneficiary.full_name,
                row.plan.enrollment.episode_code,
                row.plan.enrollment.service,
                row.plan.version_number,
                row.plan.get_status_display(),
                row.category_label,
                row.total_goals,
                row.planned_goals,
                row.in_progress_goals,
                row.achieved_goals,
                row.deferred_goals,
                row.cancelled_goals,
                row.condition_outcome,
            ]
            yield [safe_csv_value(value) for value in values]
        return
    for row in queryset.iterator(chunk_size=500):
        if report_type == "beneficiaries":
            values = [
                row.beneficiary_code,
                row.full_name,
                row.age_years_months,
                row.ssk_age_band,
                row.region_ref or row.region,
                row.municipality_ref or row.municipality,
            ]
        elif report_type == "enrollments":
            values = [
                row.episode_code,
                row.beneficiary.beneficiary_code,
                row.beneficiary.full_name,
                row.service,
                row.get_status_display(),
                row.start_date,
                row.end_date,
            ]
        elif report_type == "visits":
            values = [
                row.beneficiary.beneficiary_code,
                row.beneficiary.full_name,
                row.enrollment.episode_code,
                row.enrollment.service,
                str(row.specialist),
                row.visit_date,
                row.activity,
                row.delivery_location,
                row.get_participation_format_display(),
                row.get_status_display(),
                row.service_units,
                row.duration_minutes,
                row.participants,
                row.cancellation_reason,
            ]
        elif report_type == "assessments":
            values = [
                row.beneficiary.beneficiary_code,
                row.beneficiary.full_name,
                row.enrollment.episode_code,
                row.enrollment.service,
                str(row.specialist),
                row.assessment_date,
                row.get_assessment_type_display(),
                row.template_version.instrument.name,
                row.template_version.version,
                row.total_score,
                row.derived_classification,
                row.delayed_domain_count,
            ]
        else:
            values = [
                row.beneficiary.beneficiary_code,
                row.beneficiary.full_name,
                row.enrollment.episode_code,
                row.enrollment.service,
                str(row.specialist),
                row.get_status_display(),
                row.plan_start_date,
                row.plan_end_date,
                row.get_review_frequency_display(),
            ]
        yield [safe_csv_value(value) for value in values]
