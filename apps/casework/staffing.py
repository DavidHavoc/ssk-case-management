"""One dated person-level pair, with a frozen and bounded legacy bridge."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db.models import Exists, F, OuterRef, Q, Value
from django.db.models.lookups import LessThan
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.centers.models import SpecialistCenterAssignment, SpecialistProfile, StaffProfile

from .models import (
    BeneficiaryStaffingPeriod,
    EnrollmentCenterPlacement,
    EnrollmentSpecialistAssignment,
    LegacyStaffingGrant,
)


def eligible_specialists(center):
    return (
        SpecialistProfile.objects.filter(
            staff_profile__user__is_active=True,
            staff_profile__status=StaffProfile.Status.ACTIVE,
            center_assignments__center=center,
            center_assignments__center__is_active=True,
        )
        .select_related("staff_profile__user")
        .distinct()
    )


def responsibility_expression(
    specialist_id, *, person_ref, enrollment_ref, on_date, historical=False
):
    """Correlated EXISTS keeps the person and date boundaries on the same row."""
    periods = BeneficiaryStaffingPeriod.objects.filter(beneficiary_id=person_ref)
    started = periods.filter(valid_from__lte=on_date)
    pair = started.filter(Q(lead_id=specialist_id) | Q(helper_id=specialist_id)).filter(
        Q(valid_to__isnull=True) | Q(valid_to__gt=on_date)
    )
    # Historical authorship uses untouched evidence before the first confirmed period.
    later_confirmation = periods.filter(valid_from__gt=on_date)
    evidence = EnrollmentSpecialistAssignment.objects.filter(
        enrollment_id=enrollment_ref,
        specialist_id=specialist_id,
        valid_from__lte=on_date,
    ).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=on_date))
    grants = (
        LegacyStaffingGrant.objects.filter(
            enrollment_id=enrollment_ref,
            specialist_id=specialist_id,
            captured_on__lte=timezone.localdate(),
            expires_on__gt=timezone.localdate(),
            valid_from__lte=on_date,
            assignment__valid_from__lte=on_date,
            assignment__specialist_id=specialist_id,
            assignment__enrollment_id=F("enrollment_id"),
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=on_date))
        .filter(Q(assignment__valid_to__isnull=True) | Q(assignment__valid_to__gt=on_date))
    )
    # As-of previews cannot extend the bridge beyond its hard deadline either.
    grants = grants.filter(
        Q(placement__valid_to__isnull=True) | Q(placement__valid_to__gt=on_date),
        expires_on__gt=on_date,
        placement__center_id=F("center_id"),
        placement__enrollment_id=F("enrollment_id"),
        placement__valid_from__lte=on_date,
    )
    legacy = Exists(grants)
    if historical:
        date_expression = on_date if hasattr(on_date, "resolve_expression") else Value(on_date)
        historical_evidence = evidence.filter(
            LessThan(date_expression, Value(timezone.localdate()))
        )
        legacy = legacy | (Exists(later_confirmation) & Exists(historical_evidence))
    return Exists(pair) | (~Exists(started) & legacy)


def responsible_specialists(enrollment, on_date):
    if enrollment is None or on_date is None:
        return SpecialistProfile.objects.none()
    placement = enrollment.placement_on(on_date)
    if placement is None:
        return SpecialistProfile.objects.none()
    return eligible_specialists(placement.center).filter(
        responsibility_expression(
            OuterRef("pk"),
            person_ref=enrollment.beneficiary_id,
            enrollment_ref=enrollment.pk,
            on_date=on_date,
            historical=True,
        )
    )


def specialist_responsible(enrollment, specialist_id, on_date):
    return responsible_specialists(enrollment, on_date).filter(pk=specialist_id).exists()


def validate_casework_actor(record, enrollment, *, using):
    """Recheck the actor after acquiring the same person lock used by staffing writers."""
    context = getattr(record, "_casework_actor_context", None)
    if context is None:
        return
    from django.contrib.auth import get_user_model
    from django.core.exceptions import PermissionDenied

    from apps.core.authorization import (
        can_create_case_record,
        case_records_changeable_by_user,
        plans_for_user,
        schedules_for_user,
    )

    from .models import Assessment, EnrollmentServiceSchedule, IndividualPlan, ServiceVisit

    actor_id, center_id = context
    # Fetch a fresh user so cached role names or pre-validation activation cannot authorize a write.
    actor = get_user_model().objects.using(using).get(pk=actor_id)
    from apps.centers.models import Center

    center = Center.objects.using(using).get(pk=center_id)
    parent = record
    if hasattr(record, "plan_id"):
        parent = record.plan
    elif hasattr(record, "goal_id"):
        parent = record.goal.plan
    elif hasattr(record, "assessment_id"):
        parent = record.assessment
    business_date = getattr(record, record.authorization_date_field, None) or getattr(
        parent, record.authorization_date_field, None
    )
    allowed_statuses = {enrollment.Status.ACTIVE}
    if isinstance(record, EnrollmentServiceSchedule) or (
        isinstance(record, ServiceVisit) and record.status == ServiceVisit.Status.PLANNED
    ):
        allowed_statuses.add(enrollment.Status.PENDING)
    if not center.is_active or not can_create_case_record(
        actor, center, enrollment, business_date, allowed_statuses=allowed_statuses
    ):
        raise PermissionDenied
    if not record._state.adding:
        if isinstance(record, (ServiceVisit, Assessment, IndividualPlan)):
            authorized = case_records_changeable_by_user(type(record), actor, center)
        elif isinstance(record, EnrollmentServiceSchedule):
            authorized = schedules_for_user(actor, center, for_change=True)
        else:
            authorized = None
        if authorized is not None and not authorized.filter(pk=record.pk).exists():
            raise PermissionDenied
    if parent is not record and isinstance(parent, IndividualPlan):
        # Goals modify the parent plan; append-only progress uses its own business date.
        selector = plans_for_user(
            actor, center, for_change=record.authorization_date_field == "plan_start_date"
        )
        if not selector.filter(pk=parent.pk).exists():
            raise PermissionDenied


def current_staffing(beneficiary, on_date=None):
    on_date = on_date or timezone.localdate()
    return (
        beneficiary.staffing_periods.filter(valid_from__lte=on_date)
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=on_date))
        .select_related("lead__staff_profile__user", "helper__staff_profile__user")
        .first()
    )


def staffing_needs_review(beneficiary, center, on_date=None):
    on_date = on_date or timezone.localdate()
    pair = current_staffing(beneficiary, on_date)
    return (
        pair is None
        or not eligible_specialists(center).filter(pk=pair.lead_id).exists()
        or (
            pair.helper_id is not None
            and not eligible_specialists(center).filter(pk=pair.helper_id).exists()
        )
    )


def validate_staffing_period(period):
    errors = {}
    if period.helper_id and period.lead_id == period.helper_id:
        errors["helper"] = _("Lead and helper must be different specialists.")
    if period.valid_from and period.valid_to and period.valid_to <= period.valid_from:
        errors["valid_to"] = _("Effective until must be later than effective from.")
    stored = None
    if not period._state.adding:
        stored = BeneficiaryStaffingPeriod.objects.get(pk=period.pk)
        immutable = (
            "beneficiary_id",
            "lead_id",
            "helper_id",
            "valid_from",
            "confirmed_by_id",
            "migration_backfill",
        )
        if any(getattr(stored, field) != getattr(period, field) for field in immutable):
            errors["__all__"] = _("Staffing history is preserved. Create a replacement pair.")
        if period.valid_to != stored.valid_to and (
            period.valid_to is None
            or period.valid_to < timezone.localdate()
            or (stored.valid_to is not None and period.valid_to > stored.valid_to)
        ):
            errors["valid_to"] = _("A staffing period may only be closed today or in the future.")
    if period._state.adding:
        from apps.core.authorization import can_manage_center

        if not period.confirmed_by_id:
            errors["__all__"] = _("Only a manager or coordinator may confirm staffing.")
        if period.valid_from and period.valid_from < timezone.localdate():
            errors["valid_from"] = _("New staffing cannot rewrite past responsibility.")
        if period.migration_backfill:
            errors["__all__"] = _("Only the migration may mark a staffing backfill.")
        # Appointment needs at least one ongoing placement where both people are eligible.
        placements = period.beneficiary.enrollments.exclude(
            Q(status__in=period.beneficiary.enrollments.model.TERMINAL_STATUSES)
            & (
                Q(end_date__isnull=True)
                | Q(end_date__lte=period.valid_from or timezone.localdate())
            )
        )
        compatible = False
        for enrollment in placements:
            placement = enrollment.placement_on(period.valid_from) if period.valid_from else None
            if (
                placement
                and period.confirmed_by_id
                and can_manage_center(period.confirmed_by, placement.center)
                and all(
                    eligible_specialists(placement.center).filter(pk=pk).exists()
                    for pk in (period.lead_id, period.helper_id)
                    if pk
                )
            ):
                compatible = True
                break
        if not compatible:
            errors["lead"] = _("Select active specialists belonging to an ongoing service center.")
    if period.beneficiary_id and period.valid_from:
        overlap = (
            BeneficiaryStaffingPeriod.objects.filter(
                beneficiary_id=period.beneficiary_id,
            )
            .exclude(pk=period.pk)
            .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=period.valid_from))
        )
        if period.valid_to:
            overlap = overlap.filter(valid_from__lt=period.valid_to)
        if overlap.exists():
            errors["__all__"] = _("Staffing periods cannot overlap, including future appointments.")
    if period.beneficiary_id and period.valid_from == timezone.localdate() and period._state.adding:
        from .models import (
            Assessment,
            AssessmentResponsibleSpecialist,
            IndividualPlan,
            ServiceVisit,
        )

        team = {pk for pk in (period.lead_id, period.helper_id) if pk}
        dated_models = (
            (ServiceVisit, "visit_date"),
            (Assessment, "assessment_date"),
            (IndividualPlan, "plan_start_date"),
        )
        displaced = any(
            model.objects.filter(beneficiary_id=period.beneficiary_id, **{field: period.valid_from})
            .exclude(specialist_id__in=team)
            .exists()
            for model, field in dated_models
        )
        displaced = (
            displaced
            or AssessmentResponsibleSpecialist.objects.filter(
                assessment__beneficiary_id=period.beneficiary_id,
                assessment__assessment_date=period.valid_from,
            )
            .exclude(specialist_id__in=team)
            .exists()
        )
        if displaced:
            errors["valid_from"] = _(
                "Recorded casework already uses this date. Choose a later replacement date."
            )
    if stored and stored.valid_to != period.valid_to and period.valid_to == timezone.localdate():
        from .models import Assessment, IndividualPlan, ServiceVisit

        if any(
            model.objects.filter(
                beneficiary_id=period.beneficiary_id, **{field: period.valid_to}
            ).exists()
            for model, field in (
                (ServiceVisit, "visit_date"),
                (Assessment, "assessment_date"),
                (IndividualPlan, "plan_start_date"),
            )
        ):
            errors["valid_to"] = _(
                "Recorded casework already uses this date. Choose a later replacement date."
            )
    if errors:
        raise ValidationError(errors)


@dataclass(frozen=True)
class Responsibility:
    enrollment: object
    specialist: object
    assignment_role: str
    confirmed: bool = True

    @property
    def pk(self):
        return (self.enrollment.pk, self.specialist.pk)

    @property
    def enrollment_id(self):
        return self.enrollment.pk

    @property
    def specialist_id(self):
        return self.specialist.pk

    def get_assignment_role_display(self):
        if not self.confirmed:
            return _("Primary") if self.assignment_role == "primary" else _("Secondary")
        return _("Lead specialist") if self.assignment_role == "primary" else _("Helper specialist")


def responsibility_rows(enrollments, on_date):
    """Batch dated responsibility for scoped QuerySets or lists, without caching access."""
    enrollments = list(enrollments)
    if not enrollments:
        return []
    enrollment_ids = {row.pk for row in enrollments}
    person_ids = {row.beneficiary_id for row in enrollments}
    pairs = {}
    for pair in (
        BeneficiaryStaffingPeriod.objects.filter(
            beneficiary_id__in=person_ids, valid_from__lte=on_date
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=on_date))
        .select_related("lead__staff_profile__user", "helper__staff_profile__user")
    ):
        pairs.setdefault(pair.beneficiary_id, pair)

    # Match placement_on's inclusive start, exclusive end and first-row ordering.
    # Read fresh rows even if a caller reuses prefetched enrollment instances.
    centers = {}
    for enrollment_id, center_id in (
        EnrollmentCenterPlacement.objects.filter(
            enrollment_id__in=enrollment_ids, valid_from__lte=on_date
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=on_date))
        .values_list("enrollment_id", "center_id")
    ):
        centers.setdefault(enrollment_id, center_id)

    legacy = {}
    unresolved_ids = {row.pk for row in enrollments if row.beneficiary_id not in pairs}
    if unresolved_ids:
        # Reuse the authorization predicate for frozen grants, original placements,
        # historical continuity and the ban on reviving access after confirmation.
        assignments = (
            EnrollmentSpecialistAssignment.objects.filter(
                enrollment_id__in=unresolved_ids, valid_from__lte=on_date
            )
            .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=on_date))
            .filter(
                responsibility_expression(
                    OuterRef("specialist_id"),
                    person_ref=OuterRef("enrollment__beneficiary_id"),
                    enrollment_ref=OuterRef("enrollment_id"),
                    on_date=on_date,
                    historical=True,
                )
            )
            .select_related("specialist__staff_profile__user")
        )
        for assignment in assignments:
            legacy.setdefault(assignment.enrollment_id, []).append(assignment)

    specialist_ids = {pk for pair in pairs.values() for pk in (pair.lead_id, pair.helper_id) if pk}
    specialist_ids.update(row.specialist_id for team in legacy.values() for row in team)
    # All eligibility predicates apply to the same membership row and its center.
    eligible = set(
        SpecialistCenterAssignment.objects.filter(
            center_id__in=centers.values(),
            center__is_active=True,
            specialist_id__in=specialist_ids,
            specialist__staff_profile__user__is_active=True,
            specialist__staff_profile__status=StaffProfile.Status.ACTIVE,
        ).values_list("center_id", "specialist_id")
    )

    rows = []
    for enrollment in enrollments:
        center_id = centers.get(enrollment.pk)
        pair = pairs.get(enrollment.beneficiary_id)
        if pair:
            for specialist, role in ((pair.lead, "primary"), (pair.helper, "secondary")):
                if specialist and (center_id, specialist.pk) in eligible:
                    rows.append(Responsibility(enrollment, specialist, role))
        else:
            # Preserve the roles as recorded, without choosing among joint leads.
            for assignment in legacy.get(enrollment.pk, ()):
                if (center_id, assignment.specialist_id) in eligible:
                    rows.append(
                        Responsibility(
                            enrollment,
                            assignment.specialist,
                            assignment.assignment_role,
                            confirmed=False,
                        )
                    )
    return rows
