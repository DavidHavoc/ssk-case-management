from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from django.db.models import QuerySet
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.casework.assessment_engine import templates_are_comparable
from apps.casework.models import (
    Assessment,
    AttachmentParentType,
    EnrollmentStateEvent,
    IndividualPlanGoal,
    IndividualPlanReview,
    PrivateAttachment,
    ServiceEnrollment,
    ServiceVisit,
)


def _choice_label(choices, value) -> str:
    return str(dict(choices).get(value, value or _("Unknown")))


@dataclass(frozen=True)
class BeneficiaryBreakdownReportRow:
    center: str
    service: str
    enrollment_status: str
    age_band: str
    region: str
    municipality: str
    beneficiary_count: int
    enrollment_count: int


@dataclass(frozen=True)
class CaseloadReportRow:
    specialist: object
    beneficiary_count: int
    enrollment_count: int
    active_assignment_count: int
    pending_count: int
    active_count: int
    suspended_count: int


@dataclass(frozen=True)
class VisitExceptionReportRow:
    visit: ServiceVisit
    exception_kind: str
    exception_label: str
    days_overdue: int


@dataclass(frozen=True)
class AssessmentProgressReportRow:
    assessment: Assessment
    previous: Assessment | None
    comparison_status: str
    total_change: Decimal | None
    delayed_domain_change: int | None


@dataclass(frozen=True)
class PlanGoalReportRow:
    category: object
    status: str
    status_label: str
    goal_count: int
    plan_count: int
    beneficiary_count: int
    overdue_count: int


@dataclass(frozen=True)
class BeneficiaryOutcomeReportRow:
    plan: object
    condition_outcome: str
    total_goals: int
    achieved_goals: int
    active_goals: int
    deferred_goals: int
    achieved_percent: Decimal


@dataclass(frozen=True)
class EnrollmentTrendReportRow:
    month: date | None
    event_kind: str
    event_label: str
    service: object
    event_count: int
    beneficiary_count: int


@dataclass(frozen=True)
class DataQualityExceptionReportRow:
    issue_code: str
    issue: str
    severity: str
    record_type: str
    beneficiary_code: str
    enrollment_code: str
    service: object | str
    due_date: date | None
    url: str


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


def beneficiary_breakdown_rows(
    enrollments: QuerySet,
    *,
    center_name: str,
    as_of: date,
    selected_age_band: str = "",
) -> list[BeneficiaryBreakdownReportRow]:
    """Group authorized enrollments without reading restricted beneficiary columns."""
    groups = defaultdict(lambda: {"beneficiaries": set(), "enrollments": set()})
    rows = enrollments.select_related(
        "beneficiary__region_ref",
        "beneficiary__municipality_ref",
        "service",
    )
    for enrollment in rows:
        beneficiary = enrollment.beneficiary
        raw_age_band = beneficiary.ssk_age_band_on(as_of)
        age_band_key = raw_age_band or ("unknown" if not beneficiary.birth_date else "outside")
        if selected_age_band and age_band_key != selected_age_band:
            continue
        age_band = {
            "unknown": str(_("Unknown")),
            "outside": str(_("Outside 0-7")),
        }.get(age_band_key, age_band_key)
        region = beneficiary.region_ref or beneficiary.region or _("Not recorded")
        municipality = beneficiary.municipality_ref or beneficiary.municipality or _("Not recorded")
        key = (
            center_name,
            str(enrollment.service),
            enrollment.get_status_display(),
            str(age_band),
            str(region),
            str(municipality),
        )
        groups[key]["beneficiaries"].add(beneficiary.pk)
        groups[key]["enrollments"].add(enrollment.pk)
    return [
        BeneficiaryBreakdownReportRow(
            center=key[0],
            service=key[1],
            enrollment_status=str(key[2]),
            age_band=key[3],
            region=key[4],
            municipality=key[5],
            beneficiary_count=len(counts["beneficiaries"]),
            enrollment_count=len(counts["enrollments"]),
        )
        for key, counts in sorted(groups.items(), key=lambda item: item[0])
    ]


def specialist_caseload_rows(assignments: QuerySet) -> list[CaseloadReportRow]:
    groups = defaultdict(
        lambda: {
            "beneficiaries": set(),
            "enrollments": set(),
            "assignments": set(),
            "statuses": defaultdict(int),
        }
    )
    for assignment in assignments:
        group = groups[assignment.specialist]
        group["beneficiaries"].add(assignment.enrollment.beneficiary_id)
        group["enrollments"].add(assignment.enrollment_id)
        group["assignments"].add(assignment.pk)
        group["statuses"][assignment.enrollment.status] += 1
    return [
        CaseloadReportRow(
            specialist=specialist,
            beneficiary_count=len(values["beneficiaries"]),
            enrollment_count=len(values["enrollments"]),
            active_assignment_count=len(values["assignments"]),
            pending_count=values["statuses"][ServiceEnrollment.Status.PENDING],
            active_count=values["statuses"][ServiceEnrollment.Status.ACTIVE],
            suspended_count=values["statuses"][ServiceEnrollment.Status.SUSPENDED],
        )
        for specialist, values in sorted(groups.items(), key=lambda item: str(item[0]))
    ]


def visit_exception_rows(visits: QuerySet, *, as_of: date) -> list[VisitExceptionReportRow]:
    rows = []
    for visit in visits:
        if visit.status == ServiceVisit.Status.PLANNED and visit.visit_date < as_of:
            rows.append(
                VisitExceptionReportRow(
                    visit=visit,
                    exception_kind="overdue",
                    exception_label=str(_("Overdue planned visit")),
                    days_overdue=(as_of - visit.visit_date).days,
                )
            )
        elif visit.status == ServiceVisit.Status.NO_SHOW:
            rows.append(
                VisitExceptionReportRow(
                    visit=visit,
                    exception_kind=ServiceVisit.Status.NO_SHOW,
                    exception_label=str(_("No show")),
                    days_overdue=0,
                )
            )
        elif visit.status == ServiceVisit.Status.CANCELLED:
            rows.append(
                VisitExceptionReportRow(
                    visit=visit,
                    exception_kind=ServiceVisit.Status.CANCELLED,
                    exception_label=str(_("Cancelled")),
                    days_overdue=0,
                )
            )
    return rows


def assessment_progress_rows(queryset: QuerySet) -> list[AssessmentProgressReportRow]:
    assessments = queryset.select_related(
        "previous_assessment__template_version__instrument",
    ).prefetch_related(
        "previous_assessment__corrections__template_version__instrument",
    )
    rows = []
    for assessment in assessments:
        previous = assessment.previous_assessment
        if previous is not None:
            corrections = [
                item
                for item in previous.corrections.all()
                if item.status == Assessment.Status.COMPLETED
            ]
            if corrections:
                previous = max(corrections, key=lambda item: item.revision_number)
        if previous is None:
            comparison_status = str(_("Baseline assessment"))
            total_change = None
            delayed_change = None
        elif templates_are_comparable(assessment.template_version, previous.template_version):
            comparison_status = str(_("Comparable"))
            total_change = assessment.total_score - previous.total_score
            delayed_change = assessment.delayed_domain_count - previous.delayed_domain_count
        else:
            comparison_status = str(_("Not comparable"))
            total_change = None
            delayed_change = None
        rows.append(
            AssessmentProgressReportRow(
                assessment=assessment,
                previous=previous,
                comparison_status=comparison_status,
                total_change=total_change,
                delayed_domain_change=delayed_change,
            )
        )
    return rows


def plan_goal_rows(
    queryset: QuerySet,
    *,
    as_of: date | None = None,
    selected_status: str = "",
) -> list[PlanGoalReportRow]:
    plans = queryset.prefetch_related("goals__category", "goals__status_history")
    groups = defaultdict(
        lambda: {"goals": set(), "plans": set(), "beneficiaries": set(), "overdue": 0}
    )
    effective_date = as_of or date.max
    for plan in plans:
        for goal in plan.goals.all():
            if as_of and goal.created_at.date() > as_of:
                continue
            status = goal.status
            if as_of:
                transitions = [
                    item for item in goal.status_history.all() if item.transition_date <= as_of
                ]
                if transitions:
                    status = max(
                        transitions,
                        key=lambda item: (item.transition_date, item.created_at),
                    ).to_status
            if selected_status and status != selected_status:
                continue
            key = (goal.category, status)
            groups[key]["goals"].add(goal.pk)
            groups[key]["plans"].add(plan.pk)
            groups[key]["beneficiaries"].add(plan.beneficiary_id)
            if (
                goal.target_date
                and goal.target_date < effective_date
                and status
                not in {IndividualPlanGoal.Status.ACHIEVED, IndividualPlanGoal.Status.CANCELLED}
            ):
                groups[key]["overdue"] += 1
    return [
        PlanGoalReportRow(
            category=key[0],
            status=key[1],
            status_label=_choice_label(IndividualPlanGoal.Status.choices, key[1]),
            goal_count=len(values["goals"]),
            plan_count=len(values["plans"]),
            beneficiary_count=len(values["beneficiaries"]),
            overdue_count=values["overdue"],
        )
        for key, values in sorted(
            groups.items(),
            key=lambda item: (item[0][0].reporting_order, str(item[0][0]), item[0][1]),
        )
    ]


def beneficiary_outcome_rows(
    queryset: QuerySet,
    *,
    as_of: date | None = None,
    selected_outcome: str = "",
) -> list[BeneficiaryOutcomeReportRow]:
    plans = queryset.prefetch_related("goals__status_history", "reviews").order_by(
        "enrollment_id", "-version_number", "-created_at"
    )
    latest_plans = {}
    for plan in plans:
        latest_plans.setdefault(plan.enrollment_id, plan)
    rows = []
    for plan in latest_plans.values():
        statuses = []
        for goal in plan.goals.all():
            if as_of and goal.created_at.date() > as_of:
                continue
            status = goal.status
            if as_of:
                transitions = [
                    item for item in goal.status_history.all() if item.transition_date <= as_of
                ]
                if transitions:
                    status = max(
                        transitions,
                        key=lambda item: (item.transition_date, item.created_at),
                    ).to_status
            statuses.append(status)
        reviews = [
            review for review in plan.reviews.all() if as_of is None or review.review_date <= as_of
        ]
        latest_review = max(
            reviews,
            key=lambda review: (review.review_date, review.created_at),
            default=None,
        )
        outcome_code = (
            latest_review.condition_outcome
            if latest_review
            else IndividualPlanReview.ConditionOutcome.NOT_YET_ASSESSED
        )
        if selected_outcome and outcome_code != selected_outcome:
            continue
        achieved = statuses.count(IndividualPlanGoal.Status.ACHIEVED)
        active = statuses.count(IndividualPlanGoal.Status.PLANNED) + statuses.count(
            IndividualPlanGoal.Status.IN_PROGRESS
        )
        total = len(statuses)
        rows.append(
            BeneficiaryOutcomeReportRow(
                plan=plan,
                condition_outcome=_choice_label(
                    IndividualPlanReview.ConditionOutcome.choices,
                    outcome_code,
                ),
                total_goals=total,
                achieved_goals=achieved,
                active_goals=active,
                deferred_goals=statuses.count(IndividualPlanGoal.Status.DEFERRED),
                achieved_percent=(
                    (Decimal(achieved) * Decimal("100") / Decimal(total)).quantize(Decimal("0.1"))
                    if total
                    else Decimal("0.0")
                ),
            )
        )
    return rows


def enrollment_trend_rows(events: QuerySet) -> list[EnrollmentTrendReportRow]:
    groups = defaultdict(lambda: {"events": 0, "beneficiaries": set()})
    for event in events:
        month = event.effective_date.replace(day=1) if event.effective_date else None
        key = (month, event.kind, event.enrollment.service)
        groups[key]["events"] += 1
        groups[key]["beneficiaries"].add(event.enrollment.beneficiary_id)
    return [
        EnrollmentTrendReportRow(
            month=key[0],
            event_kind=key[1],
            event_label=_choice_label(EnrollmentStateEvent.Kind.choices, key[1]),
            service=key[2],
            event_count=values["events"],
            beneficiary_count=len(values["beneficiaries"]),
        )
        for key, values in sorted(
            groups.items(),
            key=lambda item: (item[0][0] or date.min, str(item[0][2]), item[0][1]),
            reverse=True,
        )
    ]


def data_quality_exception_rows(
    enrollments: QuerySet,
    assessments: QuerySet,
    plans: QuerySet,
    *,
    center,
    as_of: date,
    include_restricted_operations: bool,
) -> list[DataQualityExceptionReportRow]:
    """Derive unresolved exceptions from authorized casework querysets."""
    enrollment_rows = list(
        enrollments.select_related(
            "beneficiary__region_ref",
            "beneficiary__municipality_ref",
            "service",
        )
    )
    rows = []

    def add(issue_code, issue, severity, record_type, enrollment, due_date=None, url=""):
        rows.append(
            DataQualityExceptionReportRow(
                issue_code=issue_code,
                issue=str(issue),
                severity=severity,
                record_type=str(record_type),
                beneficiary_code=enrollment.beneficiary.beneficiary_code,
                enrollment_code=enrollment.episode_code,
                service=enrollment.service,
                due_date=due_date,
                url=url
                or reverse("beneficiary_detail", kwargs={"pk": enrollment.beneficiary_id})
                + f"?enrollment={enrollment.pk}",
            )
        )

    documented_beneficiary_ids = set()
    if include_restricted_operations:
        beneficiary_ids = {item.beneficiary_id for item in enrollment_rows}
        documented_beneficiary_ids = set(
            PrivateAttachment.objects.filter(
                parent_type=AttachmentParentType.BENEFICIARY,
                parent_id__in=beneficiary_ids,
                center=center,
            ).values_list("parent_id", flat=True)
        )
    checked_beneficiaries = set()
    for enrollment in enrollment_rows:
        detail_url = (
            reverse("beneficiary_detail", kwargs={"pk": enrollment.beneficiary_id})
            + f"?enrollment={enrollment.pk}"
        )
        if not enrollment.start_date or enrollment.legacy_dates_incomplete:
            add(
                "enrollment_dates",
                _("Enrollment dates need review"),
                "warning",
                _("Enrollment"),
                enrollment,
                url=detail_url,
            )
        if include_restricted_operations and not enrollment.application_contract_number:
            add(
                "enrollment_contract",
                _("Enrollment contract number is missing"),
                "warning",
                _("Enrollment"),
                enrollment,
                url=detail_url,
            )
        beneficiary = enrollment.beneficiary
        if not include_restricted_operations or beneficiary.pk in checked_beneficiaries:
            continue
        checked_beneficiaries.add(beneficiary.pk)
        if not beneficiary.birth_date:
            add(
                "birth_date",
                _("Birth date is missing"),
                "warning",
                _("Beneficiary"),
                enrollment,
                url=detail_url,
            )
        if not (beneficiary.region_ref_id or beneficiary.region):
            add(
                "region",
                _("Region is missing"),
                "warning",
                _("Beneficiary"),
                enrollment,
                url=detail_url,
            )
        if not (beneficiary.municipality_ref_id or beneficiary.municipality):
            add(
                "municipality",
                _("Municipality is missing"),
                "warning",
                _("Beneficiary"),
                enrollment,
                url=detail_url,
            )
        if beneficiary.pk not in documented_beneficiary_ids:
            add(
                "beneficiary_document",
                _("No beneficiary document is attached for this center"),
                "warning",
                _("Beneficiary"),
                enrollment,
                url=detail_url + "#documents",
            )

    enrollment_by_id = {item.pk: item for item in enrollment_rows}
    for assessment in assessments.filter(next_review_date__lt=as_of).select_related(
        "enrollment__beneficiary",
        "enrollment__service",
    ):
        enrollment = enrollment_by_id.get(assessment.enrollment_id)
        if enrollment is not None:
            add(
                "assessment_review",
                _("Assessment review is overdue"),
                "danger",
                _("Assessment"),
                enrollment,
                assessment.next_review_date,
                reverse("assessment_detail", kwargs={"pk": assessment.pk}),
            )
    for plan in (
        plans.filter(status="active")
        .select_related(
            "enrollment__beneficiary",
            "enrollment__service",
        )
        .prefetch_related("goals")
    ):
        enrollment = enrollment_by_id.get(plan.enrollment_id)
        if enrollment is None:
            continue
        plan_url = reverse("plan_detail", kwargs={"pk": plan.pk})
        if plan.review_due_date and plan.review_due_date < as_of:
            add(
                "plan_review",
                _("Plan review is overdue"),
                "danger",
                _("Individual plan"),
                enrollment,
                plan.review_due_date,
                plan_url,
            )
        elif not plan.review_due_date:
            add(
                "plan_review_date",
                _("Active plan has no review due date"),
                "warning",
                _("Individual plan"),
                enrollment,
                url=plan_url,
            )
        if any(goal.requires_review for goal in plan.goals.all()):
            add(
                "goal_review",
                _("Plan contains goals that require review"),
                "warning",
                _("Plan goal"),
                enrollment,
                url=plan_url,
            )
    return sorted(
        rows,
        key=lambda row: (
            0 if row.severity == "danger" else 1,
            row.due_date or date.max,
            row.beneficiary_code,
            row.issue_code,
        ),
    )


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
        "beneficiary_breakdown": [
            _("Center"),
            _("Service"),
            _("Enrollment status"),
            _("SSK age band"),
            _("Region"),
            _("Municipality"),
            _("Beneficiaries"),
            _("Enrollments"),
        ],
        "caseload": [
            _("Specialist"),
            _("Beneficiaries"),
            _("Enrollments"),
            _("Active assignments"),
            _("Pending enrollments"),
            _("Active enrollments"),
            _("Suspended enrollments"),
        ],
        "service_delivery": [
            _("Month"),
            _("Beneficiary code"),
            _("Beneficiary"),
            _("Enrollment code"),
            _("Service"),
            _("Activity"),
            _("Delivery location"),
            _("Format"),
            _("Planned visits"),
            _("Delivered visits"),
            _("Visit variance"),
            _("Planned units"),
            _("Delivered units"),
            _("Unit variance"),
            _("Delivered duration minutes"),
            _("No show"),
            _("Cancelled"),
        ],
        "visit_exceptions": [
            _("Beneficiary code"),
            _("Enrollment code"),
            _("Service"),
            _("Specialist"),
            _("Visit date"),
            _("Activity"),
            _("Delivery location"),
            _("Exception"),
            _("Days overdue"),
            _("Cancellation reason"),
        ],
        "assessment_progress": [
            _("Beneficiary code"),
            _("Enrollment code"),
            _("Service"),
            _("Assessment date"),
            _("Type"),
            _("Instrument"),
            _("Current total"),
            _("Previous total"),
            _("Total change"),
            _("Delayed domains"),
            _("Delayed-domain change"),
            _("Comparison status"),
        ],
        "plan_goals": [
            _("Category"),
            _("Goal status"),
            _("Goals"),
            _("Plans"),
            _("Beneficiaries"),
            _("Overdue goals"),
        ],
        "beneficiary_outcomes": [
            _("Beneficiary code"),
            _("Beneficiary"),
            _("Enrollment code"),
            _("Service"),
            _("Plan status"),
            _("Child condition outcome"),
            _("Total goals"),
            _("Achieved goals"),
            _("Active goals"),
            _("Deferred goals"),
            _("Achieved percent"),
        ],
        "enrollment_trends": [
            _("Month"),
            _("Lifecycle event"),
            _("Service"),
            _("Events"),
            _("Beneficiaries"),
        ],
        "data_quality": [
            _("Severity"),
            _("Issue"),
            _("Record type"),
            _("Beneficiary code"),
            _("Enrollment code"),
            _("Service"),
            _("Due date"),
        ],
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


def report_rows(report_type: str, source) -> Iterable[list[str]]:
    iterable = source.iterator(chunk_size=500) if isinstance(source, QuerySet) else source
    for row in iterable:
        if report_type == "beneficiary_breakdown":
            values = [
                row.center,
                row.service,
                row.enrollment_status,
                row.age_band,
                row.region,
                row.municipality,
                row.beneficiary_count,
                row.enrollment_count,
            ]
        elif report_type == "caseload":
            values = [
                row.specialist,
                row.beneficiary_count,
                row.enrollment_count,
                row.active_assignment_count,
                row.pending_count,
                row.active_count,
                row.suspended_count,
            ]
        elif report_type == "service_delivery":
            values = [
                row.schedule_month.strftime("%Y-%m"),
                row.beneficiary.beneficiary_code,
                row.beneficiary.full_name,
                row.enrollment.episode_code,
                row.enrollment.service,
                row.activity,
                row.delivery_location,
                row.participation_format,
                row.planned_visits,
                row.delivered_visits,
                row.visit_variance,
                row.planned_units,
                row.delivered_units,
                row.unit_variance,
                row.delivered_duration_minutes,
                row.no_show_count,
                row.cancelled_count,
            ]
        elif report_type == "visit_exceptions":
            visit = row.visit
            values = [
                visit.beneficiary.beneficiary_code,
                visit.enrollment.episode_code,
                visit.enrollment.service,
                visit.specialist,
                visit.visit_date,
                visit.activity,
                visit.delivery_location,
                row.exception_label,
                row.days_overdue,
                visit.cancellation_reason,
            ]
        elif report_type == "assessment_progress":
            assessment = row.assessment
            values = [
                assessment.beneficiary.beneficiary_code,
                assessment.enrollment.episode_code,
                assessment.enrollment.service,
                assessment.assessment_date,
                assessment.get_assessment_type_display(),
                assessment.template_version.instrument.name,
                assessment.total_score,
                row.previous.total_score if row.previous else None,
                row.total_change,
                assessment.delayed_domain_count,
                row.delayed_domain_change,
                row.comparison_status,
            ]
        elif report_type == "plan_goals":
            values = [
                row.category,
                row.status_label,
                row.goal_count,
                row.plan_count,
                row.beneficiary_count,
                row.overdue_count,
            ]
        elif report_type == "beneficiary_outcomes":
            values = [
                row.plan.beneficiary.beneficiary_code,
                row.plan.beneficiary.full_name,
                row.plan.enrollment.episode_code,
                row.plan.enrollment.service,
                row.plan.get_status_display(),
                row.condition_outcome,
                row.total_goals,
                row.achieved_goals,
                row.active_goals,
                row.deferred_goals,
                row.achieved_percent,
            ]
        elif report_type == "enrollment_trends":
            values = [
                row.month.strftime("%Y-%m") if row.month else _("Unknown"),
                row.event_label,
                row.service,
                row.event_count,
                row.beneficiary_count,
            ]
        elif report_type == "data_quality":
            values = [
                row.severity,
                row.issue,
                row.record_type,
                row.beneficiary_code,
                row.enrollment_code,
                row.service,
                row.due_date,
            ]
        elif report_type == "plan_outcomes":
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
        elif report_type == "beneficiaries":
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
