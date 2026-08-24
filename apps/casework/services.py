from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import connection, transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import (
    Beneficiary,
    CenterServiceOffering,
    EnrollmentCenterPlacement,
    EnrollmentSpecialistAssignment,
    EnrollmentStateEvent,
    GoalStatusTransition,
    IndividualPlan,
    IndividualPlanGoal,
    ServiceEnrollment,
    ServiceVisit,
    ServiceVisitCorrection,
    SpecialistMonthlyServiceSummary,
)

PLAN_STATUS_TRANSITIONS = {
    IndividualPlan.Status.DRAFT: {
        IndividualPlan.Status.ACTIVE,
        IndividualPlan.Status.CANCELLED,
    },
    IndividualPlan.Status.ACTIVE: {
        IndividualPlan.Status.COMPLETED,
        IndividualPlan.Status.SUPERSEDED,
        IndividualPlan.Status.CANCELLED,
    },
    IndividualPlan.Status.COMPLETED: set(),
    IndividualPlan.Status.SUPERSEDED: set(),
    IndividualPlan.Status.CANCELLED: set(),
}


GOAL_STATUS_TRANSITIONS = {
    IndividualPlanGoal.Status.PLANNED: {
        IndividualPlanGoal.Status.IN_PROGRESS,
        IndividualPlanGoal.Status.DEFERRED,
        IndividualPlanGoal.Status.CANCELLED,
    },
    IndividualPlanGoal.Status.IN_PROGRESS: {
        IndividualPlanGoal.Status.ACHIEVED,
        IndividualPlanGoal.Status.DEFERRED,
        IndividualPlanGoal.Status.CANCELLED,
    },
    IndividualPlanGoal.Status.DEFERRED: {
        IndividualPlanGoal.Status.PLANNED,
        IndividualPlanGoal.Status.IN_PROGRESS,
        IndividualPlanGoal.Status.CANCELLED,
    },
    IndividualPlanGoal.Status.ACHIEVED: set(),
    IndividualPlanGoal.Status.CANCELLED: set(),
}


@transaction.atomic
def save_plan_period(
    plan: IndividualPlan,
    *,
    has_valid_goals: bool = False,
) -> IndividualPlan:
    ServiceEnrollment.objects.select_for_update().get(pk=plan.enrollment_id)
    if plan.status in {IndividualPlan.Status.ACTIVE, IndividualPlan.Status.COMPLETED}:
        stored_goals_exist = plan.pk and IndividualPlanGoal.objects.filter(plan=plan).exists()
        if not has_valid_goals and not stored_goals_exist:
            raise ValueError("An active or completed plan requires at least one valid goal.")
    prior_active = (
        IndividualPlan.objects.select_for_update()
        .filter(enrollment_id=plan.enrollment_id, status=IndividualPlan.Status.ACTIVE)
        .exclude(pk=plan.pk)
        .order_by("-version_number", "-created_at")
        .first()
    )
    if plan.status == IndividualPlan.Status.ACTIVE and prior_active:
        if not plan.previous_plan_id:
            plan.previous_plan = prior_active
        IndividualPlan.objects.filter(pk=prior_active.pk).update(
            status=IndividualPlan.Status.SUPERSEDED,
            updated_at=timezone.now(),
        )
    plan.save()
    return plan


def record_goal_status_transition(
    goal: IndividualPlanGoal,
    *,
    from_status: str,
    actor,
    transition_date: date,
    reason: str = "",
    evidence: str = "",
) -> GoalStatusTransition:
    if from_status == goal.status:
        raise ValueError("A goal status transition must change the status.")
    if from_status and goal.status not in GOAL_STATUS_TRANSITIONS.get(from_status, set()):
        raise ValueError(f"Invalid goal transition from {from_status} to {goal.status}.")
    return GoalStatusTransition.objects.create(
        goal=goal,
        from_status=from_status,
        to_status=goal.status,
        transition_date=transition_date,
        actor=actor,
        reason=reason,
        evidence=evidence,
    )


def _validate_offering(
    offering: CenterServiceOffering,
    *,
    service_id,
    center_id,
    effective_date: date,
) -> None:
    if offering.service_id != service_id:
        raise ValueError("Center offering does not match the enrollment service.")
    if offering.center_id != center_id:
        raise ValueError("Center offering does not match the selected center.")
    if not offering.is_effective(effective_date):
        raise ValueError("Center offering is not effective on the selected date.")


@transaction.atomic
def create_enrollment(
    *,
    beneficiary: Beneficiary,
    offering: CenterServiceOffering,
    episode_code: str,
    start_date: date,
    actor,
    status: str = ServiceEnrollment.Status.PENDING,
    first_service_date: date | None = None,
    application_contract_number: str = "",
    notes: str = "",
    prior_enrollment: ServiceEnrollment | None = None,
) -> ServiceEnrollment:
    Beneficiary.objects.select_for_update().get(pk=beneficiary.pk)
    _validate_offering(
        offering,
        service_id=offering.service_id,
        center_id=offering.center_id,
        effective_date=start_date,
    )
    if status not in {ServiceEnrollment.Status.PENDING, ServiceEnrollment.Status.ACTIVE}:
        raise ValueError("A new enrollment must start as pending or active.")
    enrollment = ServiceEnrollment.objects.create(
        beneficiary=beneficiary,
        service=offering.service,
        episode_code=episode_code,
        status=status,
        start_date=start_date,
        first_service_date=first_service_date,
        application_contract_number=application_contract_number,
        notes=notes,
        prior_enrollment=prior_enrollment,
    )
    EnrollmentCenterPlacement.objects.create(
        enrollment=enrollment,
        center=offering.center,
        offering=offering,
        valid_from=start_date,
    )
    if prior_enrollment:
        kind = EnrollmentStateEvent.Kind.RE_ENROLLMENT
    elif status == ServiceEnrollment.Status.ACTIVE:
        kind = EnrollmentStateEvent.Kind.ADMISSION
    else:
        kind = EnrollmentStateEvent.Kind.CREATED
    EnrollmentStateEvent.objects.create(
        enrollment=enrollment,
        kind=kind,
        previous_state="",
        new_state=status,
        effective_date=start_date,
        actor=actor,
    )
    return enrollment


def _validate_transition_date(enrollment: ServiceEnrollment, effective_date: date) -> None:
    if enrollment.start_date and effective_date <= enrollment.start_date:
        raise ValueError("Transition date must be later than the enrollment start date.")
    latest = (
        enrollment.state_events.filter(effective_date__isnull=False)
        .order_by("-effective_date", "-created_at")
        .first()
    )
    if latest and latest.effective_date and effective_date < latest.effective_date:
        raise ValueError("Transition date cannot be earlier than existing enrollment history.")


@transaction.atomic
def transition_enrollment(
    enrollment: ServiceEnrollment,
    *,
    new_state: str,
    effective_date: date,
    reason: str,
    actor,
    notes: str = "",
) -> ServiceEnrollment:
    enrollment = ServiceEnrollment.objects.select_for_update().get(pk=enrollment.pk)
    allowed = {
        ServiceEnrollment.Status.PENDING: {
            ServiceEnrollment.Status.ACTIVE,
            ServiceEnrollment.Status.CANCELLED,
        },
        ServiceEnrollment.Status.ACTIVE: {
            ServiceEnrollment.Status.SUSPENDED,
            ServiceEnrollment.Status.COMPLETED,
            ServiceEnrollment.Status.EXITED,
        },
        ServiceEnrollment.Status.SUSPENDED: {
            ServiceEnrollment.Status.ACTIVE,
            ServiceEnrollment.Status.COMPLETED,
            ServiceEnrollment.Status.EXITED,
        },
    }
    if new_state not in allowed.get(enrollment.status, set()):
        raise ValueError(f"Invalid transition from {enrollment.status} to {new_state}.")
    _validate_transition_date(enrollment, effective_date)
    kind = {
        ServiceEnrollment.Status.ACTIVE: (
            EnrollmentStateEvent.Kind.ADMISSION
            if enrollment.status == ServiceEnrollment.Status.PENDING
            else EnrollmentStateEvent.Kind.RESUMPTION
        ),
        ServiceEnrollment.Status.SUSPENDED: EnrollmentStateEvent.Kind.SUSPENSION,
        ServiceEnrollment.Status.COMPLETED: EnrollmentStateEvent.Kind.COMPLETION,
        ServiceEnrollment.Status.EXITED: EnrollmentStateEvent.Kind.EXIT,
        ServiceEnrollment.Status.CANCELLED: EnrollmentStateEvent.Kind.CANCELLATION,
    }[new_state]
    previous_state = enrollment.status
    enrollment.status = new_state
    if new_state in ServiceEnrollment.TERMINAL_STATUSES:
        enrollment.end_date = effective_date
        enrollment.exit_reason = reason
        EnrollmentCenterPlacement.objects.filter(
            enrollment=enrollment,
            valid_to__isnull=True,
        ).update(valid_to=effective_date, updated_at=timezone.now())
        EnrollmentSpecialistAssignment.objects.filter(
            enrollment=enrollment,
            valid_to__isnull=True,
        ).update(valid_to=effective_date, updated_at=timezone.now())
    enrollment.save()
    EnrollmentStateEvent.objects.create(
        enrollment=enrollment,
        kind=kind,
        previous_state=previous_state,
        new_state=new_state,
        effective_date=effective_date,
        reason=reason,
        notes=notes,
        actor=actor,
    )
    return enrollment


def admit_enrollment(enrollment, *, effective_date, reason, actor, notes=""):
    return transition_enrollment(
        enrollment,
        new_state=ServiceEnrollment.Status.ACTIVE,
        effective_date=effective_date,
        reason=reason,
        actor=actor,
        notes=notes,
    )


def suspend_enrollment(enrollment, *, effective_date, reason, actor, notes=""):
    return transition_enrollment(
        enrollment,
        new_state=ServiceEnrollment.Status.SUSPENDED,
        effective_date=effective_date,
        reason=reason,
        actor=actor,
        notes=notes,
    )


def resume_enrollment(enrollment, *, effective_date, reason, actor, notes=""):
    return transition_enrollment(
        enrollment,
        new_state=ServiceEnrollment.Status.ACTIVE,
        effective_date=effective_date,
        reason=reason,
        actor=actor,
        notes=notes,
    )


def complete_enrollment(enrollment, *, effective_date, reason, actor, notes=""):
    return transition_enrollment(
        enrollment,
        new_state=ServiceEnrollment.Status.COMPLETED,
        effective_date=effective_date,
        reason=reason,
        actor=actor,
        notes=notes,
    )


def exit_enrollment(enrollment, *, effective_date, reason, actor, notes=""):
    return transition_enrollment(
        enrollment,
        new_state=ServiceEnrollment.Status.EXITED,
        effective_date=effective_date,
        reason=reason,
        actor=actor,
        notes=notes,
    )


@transaction.atomic
def transfer_enrollment(
    enrollment: ServiceEnrollment,
    *,
    destination_offering: CenterServiceOffering,
    effective_date: date,
    reason: str,
    actor,
    notes: str = "",
) -> ServiceEnrollment:
    enrollment = ServiceEnrollment.objects.select_for_update().get(pk=enrollment.pk)
    if enrollment.is_terminal:
        raise ValueError("A terminal enrollment cannot be transferred.")
    _validate_transition_date(enrollment, effective_date)
    current = (
        EnrollmentCenterPlacement.objects.select_for_update()
        .filter(
            enrollment=enrollment,
        )
        .filter(Q(valid_from__isnull=True) | Q(valid_from__lte=effective_date))
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=effective_date))
        .first()
    )
    if not current:
        raise ValueError("Enrollment has no placement on the transfer date.")
    if current.center_id == destination_offering.center_id:
        raise ValueError("Destination center must differ from the current center.")
    _validate_offering(
        destination_offering,
        service_id=enrollment.service_id,
        center_id=destination_offering.center_id,
        effective_date=effective_date,
    )
    current.valid_to = effective_date
    current.transfer_reason = reason
    current.notes = notes
    current.save()
    EnrollmentCenterPlacement.objects.create(
        enrollment=enrollment,
        center=destination_offering.center,
        offering=destination_offering,
        valid_from=effective_date,
        transfer_reason=reason,
        notes=notes,
    )
    compatible_specialists = destination_offering.center.specialist_assignments.values_list(
        "specialist_id", flat=True
    )
    EnrollmentSpecialistAssignment.objects.filter(
        enrollment=enrollment,
        valid_to__isnull=True,
    ).exclude(specialist_id__in=compatible_specialists).update(
        valid_to=effective_date,
        updated_at=timezone.now(),
    )
    EnrollmentStateEvent.objects.create(
        enrollment=enrollment,
        kind=EnrollmentStateEvent.Kind.TRANSFER,
        previous_state=enrollment.status,
        new_state=enrollment.status,
        effective_date=effective_date,
        reason=reason,
        notes=notes,
        actor=actor,
    )
    return enrollment


def reenroll_beneficiary(
    prior_enrollment: ServiceEnrollment,
    *,
    offering: CenterServiceOffering,
    episode_code: str,
    start_date: date,
    actor,
    status: str = ServiceEnrollment.Status.PENDING,
    application_contract_number: str = "",
    notes: str = "",
) -> ServiceEnrollment:
    if not prior_enrollment.is_terminal:
        raise ValueError("Only a terminal enrollment can be followed by re-enrollment.")
    if offering.service_id != prior_enrollment.service_id:
        raise ValueError("Re-enrollment must use the prior service.")
    return create_enrollment(
        beneficiary=prior_enrollment.beneficiary,
        offering=offering,
        episode_code=episode_code,
        start_date=start_date,
        actor=actor,
        status=status,
        application_contract_number=application_contract_number,
        notes=notes,
        prior_enrollment=prior_enrollment,
    )


def _lock_summary_scope(specialist_id, center_id, summary_month: date) -> None:
    if connection.vendor != "postgresql":
        return
    value = f"{specialist_id}:{center_id}:{summary_month:%Y-%m}".encode()
    lock_key = int.from_bytes(hashlib.sha256(value).digest()[:8], "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])


@transaction.atomic
def rebuild_monthly_summary(
    specialist_id, center_id, summary_month: date
) -> SpecialistMonthlyServiceSummary | None:
    month = summary_month.replace(day=1)
    _lock_summary_scope(specialist_id, center_id, month)
    visits = ServiceVisit.objects.filter(
        specialist_id=specialist_id,
        center_id=center_id,
        visit_month=month,
    )
    if not visits.exists():
        SpecialistMonthlyServiceSummary.objects.filter(
            specialist_id=specialist_id,
            center_id=center_id,
            summary_month=month,
        ).delete()
        return None
    totals = visits.aggregate(
        completed_visits=Count("id", filter=Q(status=ServiceVisit.Status.COMPLETED)),
        total_service_units=Coalesce(
            Sum("service_units", filter=Q(status=ServiceVisit.Status.COMPLETED)),
            Decimal("0"),
        ),
        total_duration_minutes=Coalesce(
            Sum("duration_minutes", filter=Q(status=ServiceVisit.Status.COMPLETED)), 0
        ),
        unique_beneficiaries=Count(
            "beneficiary_id", distinct=True, filter=Q(status=ServiceVisit.Status.COMPLETED)
        ),
        planned_count=Count("id", filter=Q(status=ServiceVisit.Status.PLANNED)),
        no_show_count=Count("id", filter=Q(status=ServiceVisit.Status.NO_SHOW)),
        cancelled_count=Count("id", filter=Q(status=ServiceVisit.Status.CANCELLED)),
    )
    summary, _ = SpecialistMonthlyServiceSummary.objects.update_or_create(
        specialist_id=specialist_id,
        center_id=center_id,
        summary_month=month,
        defaults={**totals, "last_rebuilt_at": timezone.now()},
    )
    return summary


VISIT_CORRECTION_FIELDS = (
    "enrollment_id",
    "beneficiary_id",
    "center_id",
    "specialist_id",
    "visit_date",
    "visit_month",
    "activity_id",
    "delivery_location_id",
    "participation_format",
    "status",
    "service_units",
    "duration_minutes",
    "participants",
    "cancellation_reason",
    "notes",
)


def service_visit_snapshot(visit: ServiceVisit) -> dict[str, str | int]:
    snapshot = {}
    for field_name in VISIT_CORRECTION_FIELDS:
        value = getattr(visit, field_name)
        if isinstance(value, (date, Decimal)):
            value = str(value)
        elif value is not None and field_name.endswith("_id"):
            value = str(value)
        snapshot[field_name] = value
    return snapshot


def record_service_visit_correction(
    *,
    visit: ServiceVisit,
    corrected_by,
    reason: str,
    before_values: dict,
) -> ServiceVisitCorrection:
    return ServiceVisitCorrection.objects.create(
        visit=visit,
        corrected_by=corrected_by,
        reason=reason,
        before_values=before_values,
        after_values=service_visit_snapshot(visit),
    )


@dataclass
class MonthlyServiceDeliveryRow:
    enrollment: ServiceEnrollment
    schedule_month: date
    activity: object
    delivery_location: object
    participation_format: str
    planned_visits: int = 0
    planned_units: Decimal = Decimal("0")
    delivered_visits: int = 0
    delivered_units: Decimal = Decimal("0")
    delivered_duration_minutes: int = 0
    no_show_count: int = 0
    cancelled_count: int = 0

    @property
    def beneficiary(self):
        return self.enrollment.beneficiary

    @property
    def visit_variance(self) -> int:
        return self.delivered_visits - self.planned_visits

    @property
    def unit_variance(self) -> Decimal:
        return self.delivered_units - self.planned_units


def monthly_service_delivery_rows(schedule_queryset, visit_queryset):
    rows = {}

    def row_key(enrollment_id, month, activity_id, location_id, participation_format):
        return enrollment_id, month, activity_id, location_id, participation_format

    schedules = schedule_queryset.select_related(
        "enrollment__beneficiary",
        "enrollment__service",
        "activity",
        "delivery_location",
    )
    for schedule in schedules:
        key = row_key(
            schedule.enrollment_id,
            schedule.schedule_month,
            schedule.activity_id,
            schedule.delivery_location_id,
            schedule.participation_format,
        )
        row = rows.setdefault(
            key,
            MonthlyServiceDeliveryRow(
                enrollment=schedule.enrollment,
                schedule_month=schedule.schedule_month,
                activity=schedule.activity,
                delivery_location=schedule.delivery_location,
                participation_format=schedule.participation_format,
            ),
        )
        row.planned_visits += schedule.planned_visits
        row.planned_units += schedule.planned_units

    visits = visit_queryset.select_related(
        "enrollment__beneficiary",
        "enrollment__service",
        "activity",
        "delivery_location",
    )
    for visit in visits:
        key = row_key(
            visit.enrollment_id,
            visit.visit_month,
            visit.activity_id,
            visit.delivery_location_id,
            visit.participation_format,
        )
        row = rows.setdefault(
            key,
            MonthlyServiceDeliveryRow(
                enrollment=visit.enrollment,
                schedule_month=visit.visit_month,
                activity=visit.activity,
                delivery_location=visit.delivery_location,
                participation_format=visit.participation_format,
            ),
        )
        if visit.status == ServiceVisit.Status.COMPLETED:
            row.delivered_visits += 1
            row.delivered_units += visit.service_units
            row.delivered_duration_minutes += visit.duration_minutes
        elif visit.status == ServiceVisit.Status.NO_SHOW:
            row.no_show_count += 1
        elif visit.status == ServiceVisit.Status.CANCELLED:
            row.cancelled_count += 1

    return sorted(
        rows.values(),
        key=lambda row: (
            -row.schedule_month.toordinal(),
            row.beneficiary.full_name,
            row.enrollment.episode_code,
            row.activity.reporting_order,
            row.delivery_location.reporting_order,
            row.participation_format,
        ),
    )
