from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db.models import F, Prefetch, Q, QuerySet
from django.http import Http404
from django.utils import timezone

from apps.accounts.roles import (
    is_central_hr,
    is_coordinator,
    is_specialist,
    is_system_manager,
)
from apps.casework.models import (
    Assessment,
    Beneficiary,
    BeneficiaryDiagnosis,
    BeneficiarySocialStatus,
    EnrollmentServiceSchedule,
    EnrollmentSpecialistAssignment,
    EnrollmentStateEvent,
    IndividualPlan,
    ServiceEnrollment,
    ServiceVisit,
    SpecialistMonthlyServiceSummary,
)
from apps.centers.models import Center, SpecialistProfile, StaffProfile

ACTIVE_CENTER_SESSION_KEY = "ssk_active_center"


class CenterSelectionRequired(PermissionDenied):
    pass


def casework_home_route(user) -> str:
    if is_specialist(user) and not (is_coordinator(user) or is_system_manager(user)):
        return "specialist_workspace"
    return "dashboard"


def accessible_centers(user, *, active_only: bool = False) -> QuerySet[Center]:
    centers = Center.objects.all()
    if active_only:
        centers = centers.filter(is_active=True)
    if is_system_manager(user):
        return centers.order_by("name")
    if not getattr(user, "is_authenticated", False):
        return centers.none()
    query = Q(pk__in=[])
    if is_coordinator(user):
        query |= Q(staff__user=user, staff__status=StaffProfile.Status.ACTIVE)
    if is_specialist(user):
        query |= Q(
            specialist_assignments__specialist__staff_profile__user=user,
            specialist_assignments__specialist__staff_profile__status=StaffProfile.Status.ACTIVE,
        )
    return centers.filter(query).distinct().order_by("name")


def active_center_for_request(request, *, required: bool = True) -> Center | None:
    centers = accessible_centers(request.user, active_only=True)
    selected = request.session.get(ACTIVE_CENTER_SESSION_KEY)
    if selected:
        center = centers.filter(pk=selected).first()
        if center:
            return center
        request.session.pop(ACTIVE_CENTER_SESSION_KEY, None)
    count = centers.count()
    if count == 1:
        center = centers.first()
        request.session[ACTIVE_CENTER_SESSION_KEY] = str(center.pk)
        return center
    if required and count > 1:
        raise CenterSelectionRequired
    if required:
        raise PermissionDenied
    return None


def can_manage_center(user, center: Center) -> bool:
    if is_system_manager(user):
        return True
    return is_coordinator(user) and accessible_centers(user).filter(pk=center.pk).exists()


def can_view_staff_directory(user) -> bool:
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return False
    if is_system_manager(user) or is_central_hr(user):
        return True
    if is_coordinator(user) and accessible_centers(user).exists():
        return True
    return _has_active_staff_profile(user) and (
        user.has_perm("centers.view_staffprofile") or user.has_perm("centers.change_staffprofile")
    )


def can_change_staff_directory(user) -> bool:
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return False
    if is_system_manager(user) or is_central_hr(user):
        return True
    return _has_active_staff_profile(user) and user.has_perm("centers.change_staffprofile")


def _has_active_staff_profile(user) -> bool:
    return StaffProfile.objects.filter(user=user, status=StaffProfile.Status.ACTIVE).exists()


def staff_profiles_for_user(user, *, change: bool = False) -> QuerySet[StaffProfile]:
    queryset = (
        StaffProfile.objects.select_related(
            "user",
            "primary_center",
            "specialist_profile",
        )
        .prefetch_related("centers", "user__groups")
        .order_by("user__last_name", "user__first_name", "employee_number")
    )
    allowed = can_change_staff_directory(user) if change else can_view_staff_directory(user)
    if not allowed:
        return queryset.none()
    if is_system_manager(user) or is_central_hr(user):
        return queryset
    if is_coordinator(user):
        return queryset.filter(centers__in=accessible_centers(user)).distinct()
    return queryset


def can_view_staff_hr_fields(user) -> bool:
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return False
    if is_system_manager(user) or is_central_hr(user):
        return True
    return _has_active_staff_profile(user) and (
        user.has_perm("centers.view_staffprofile") or user.has_perm("centers.change_staffprofile")
    )


def staff_directory_centers_for_user(user) -> QuerySet[Center]:
    centers = Center.objects.order_by("name")
    if is_system_manager(user) or is_central_hr(user):
        return centers
    if is_coordinator(user):
        return accessible_centers(user)
    return centers.filter(staff__in=staff_profiles_for_user(user)).distinct()


def specialist_profile_for_user(user) -> SpecialistProfile | None:
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return None
    return (
        SpecialistProfile.objects.select_related("staff_profile", "staff_profile__user")
        .filter(
            staff_profile__user=user,
            staff_profile__status=StaffProfile.Status.ACTIVE,
        )
        .first()
    )


def specialists_for_center(center: Center) -> QuerySet[SpecialistProfile]:
    return (
        SpecialistProfile.objects.filter(
            center_assignments__center=center,
            staff_profile__status=StaffProfile.Status.ACTIVE,
        )
        .select_related("staff_profile", "staff_profile__user")
        .distinct()
    )


def staff_contracts_for_user(user, center: Center | None = None) -> QuerySet[StaffProfile]:
    """Return staff contract dates that the user may receive in-app reminders about."""
    queryset = StaffProfile.objects.select_related("user", "primary_center").prefetch_related(
        "centers"
    )
    if center is None:
        return queryset.none()
    at_center = Q(primary_center=center) | Q(centers=center)
    if is_system_manager(user):
        return queryset.filter(at_center).distinct()
    if is_coordinator(user) and accessible_centers(user).filter(pk=center.pk).exists():
        return queryset.filter(at_center).distinct()
    if is_specialist(user):
        return queryset.filter(user=user).filter(at_center).distinct()
    return queryset.none()


def _effective_interval(prefix: str, on_date) -> Q:
    return Q(**{f"{prefix}valid_from__lte": on_date}) & (
        Q(**{f"{prefix}valid_to__isnull": True}) | Q(**{f"{prefix}valid_to__gt": on_date})
    )


def enrollments_for_user(
    user,
    center: Center | None = None,
    *,
    as_of=None,
) -> QuerySet[ServiceEnrollment]:
    on_date = as_of or timezone.localdate()
    queryset = ServiceEnrollment.objects.select_related(
        "beneficiary",
        "service",
        "prior_enrollment",
    ).prefetch_related(
        "center_placements__center",
        "specialist_assignments__specialist__staff_profile__user",
        "state_events",
    )
    if is_system_manager(user):
        if center is None:
            return queryset
        return queryset.filter(center_placements__center=center).distinct()
    if center is None or not accessible_centers(user).filter(pk=center.pk).exists():
        return queryset.none()

    current_placement = Q(center_placements__center=center) & _effective_interval(
        "center_placements__", on_date
    )
    if is_coordinator(user):
        terminal_at_center = Q(
            status__in=ServiceEnrollment.TERMINAL_STATUSES,
            center_placements__center=center,
            center_placements__valid_to=F("end_date"),
        )
        return queryset.filter(current_placement | terminal_at_center).distinct()
    if is_specialist(user):
        profile = specialist_profile_for_user(user)
        if profile:
            assignment = Q(specialist_assignments__specialist=profile) & _effective_interval(
                "specialist_assignments__", on_date
            )
            return (
                queryset.exclude(status__in=ServiceEnrollment.TERMINAL_STATUSES)
                .filter(current_placement & assignment)
                .distinct()
            )
    return queryset.none()


def assigned_enrollments_for_specialist(
    user,
    center: Center | None = None,
    *,
    as_of=None,
) -> QuerySet[ServiceEnrollment]:
    """Return the current enrollment assignments for the user's specialist profile.

    This selector intentionally ignores any additional coordinator role so a mixed-role
    user's specialist workspace remains a clearly bounded operational view.
    """
    on_date = as_of or timezone.localdate()
    queryset = ServiceEnrollment.objects.select_related(
        "beneficiary",
        "service",
        "prior_enrollment",
    ).prefetch_related(
        "center_placements__center",
        "specialist_assignments__specialist__staff_profile__user",
        "state_events",
    )
    if (
        center is None
        or not is_specialist(user)
        or not accessible_centers(user).filter(pk=center.pk).exists()
    ):
        return queryset.none()
    profile = specialist_profile_for_user(user)
    if profile is None:
        return queryset.none()
    current_placement = Q(center_placements__center=center) & _effective_interval(
        "center_placements__", on_date
    )
    assignment = Q(specialist_assignments__specialist=profile) & _effective_interval(
        "specialist_assignments__", on_date
    )
    return (
        queryset.exclude(status__in=ServiceEnrollment.TERMINAL_STATUSES)
        .filter(current_placement & assignment)
        .distinct()
    )


def assigned_beneficiaries_for_specialist(
    user,
    center: Center | None = None,
    *,
    as_of=None,
) -> QuerySet[Beneficiary]:
    authorized_enrollments = assigned_enrollments_for_specialist(
        user,
        center,
        as_of=as_of,
    )
    return (
        Beneficiary.objects.select_related("center", "region_ref", "municipality_ref")
        .filter(enrollments__in=authorized_enrollments)
        .distinct()
        .prefetch_related(
            Prefetch(
                "enrollments",
                queryset=authorized_enrollments,
                to_attr="authorized_enrollments",
            )
        )
    )


def active_enrollment_assignments_for_user(
    user,
    center: Center | None = None,
    *,
    as_of=None,
) -> QuerySet[EnrollmentSpecialistAssignment]:
    """Return active assignments whose enrollments are already authorized for the user."""
    on_date = as_of or timezone.localdate()
    authorized_enrollments = enrollments_for_user(user, center, as_of=on_date)
    queryset = (
        EnrollmentSpecialistAssignment.objects.select_related(
            "enrollment__beneficiary",
            "enrollment__service",
            "specialist__staff_profile__user",
        )
        .filter(
            enrollment__in=authorized_enrollments,
            valid_from__lte=on_date,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=on_date))
    )
    if is_specialist(user) and not (is_coordinator(user) or is_system_manager(user)):
        profile = specialist_profile_for_user(user)
        if profile is None:
            return queryset.none()
        queryset = queryset.filter(specialist=profile)
    return queryset.distinct()


def enrollment_events_for_user(
    user,
    center: Center | None = None,
) -> QuerySet[EnrollmentStateEvent]:
    """Return lifecycle events only through an authorized enrollment queryset."""
    authorized_enrollments = enrollments_for_user(user, center)
    return EnrollmentStateEvent.objects.select_related(
        "enrollment__beneficiary",
        "enrollment__service",
    ).filter(enrollment__in=authorized_enrollments)


def beneficiaries_for_user(user, center: Center | None = None) -> QuerySet[Beneficiary]:
    queryset = Beneficiary.objects.select_related("center", "region_ref", "municipality_ref")
    if is_system_manager(user):
        if center is None:
            authorized_enrollments = ServiceEnrollment.objects.select_related("service")
            return queryset.prefetch_related(
                Prefetch(
                    "enrollments",
                    queryset=authorized_enrollments,
                    to_attr="authorized_enrollments",
                )
            )
    authorized_enrollments = enrollments_for_user(user, center)
    return (
        queryset.filter(enrollments__in=authorized_enrollments)
        .distinct()
        .prefetch_related(
            Prefetch(
                "enrollments",
                queryset=authorized_enrollments,
                to_attr="authorized_enrollments",
            )
        )
    )


def case_records_for_user(model, user, center: Center | None = None):
    queryset = model.objects.select_related(
        "center",
        "beneficiary",
        "enrollment__service",
        "specialist__staff_profile__user",
    )
    if model is ServiceVisit:
        queryset = queryset.select_related("activity", "delivery_location")
    if model is Assessment:
        queryset = queryset.select_related(
            "template_version__instrument",
            "previous_assessment__template_version__instrument",
        ).prefetch_related(
            "responsible_specialists__staff_profile__user",
            "responses__template_field__section",
        )
    if is_system_manager(user):
        return queryset.filter(center=center) if center else queryset
    if center is None or not accessible_centers(user).filter(pk=center.pk).exists():
        return queryset.none()
    if is_coordinator(user):
        return queryset.filter(center=center)
    if is_specialist(user):
        authorized_enrollments = enrollments_for_user(user, center)
        return queryset.filter(enrollment__in=authorized_enrollments).distinct()
    return queryset.none()


_CASE_RECORD_DATE_FIELDS = {
    ServiceVisit: "visit_date",
    Assessment: "assessment_date",
    IndividualPlan: "plan_start_date",
}


def case_records_changeable_by_user(model, user, center: Center | None = None):
    queryset = case_records_for_user(model, user, center)
    if is_system_manager(user) or is_coordinator(user):
        return queryset
    if not is_specialist(user):
        return queryset.none()
    profile = specialist_profile_for_user(user)
    date_field = _CASE_RECORD_DATE_FIELDS.get(model)
    if profile is None or date_field is None:
        return queryset.none()
    prefix = "enrollment__specialist_assignments__"
    assignment_at_record_date = (
        Q(**{f"{prefix}specialist": profile})
        & Q(**{f"{prefix}valid_from__lte": F(date_field)})
        & (Q(**{f"{prefix}valid_to__isnull": True}) | Q(**{f"{prefix}valid_to__gt": F(date_field)}))
    )
    return queryset.filter(assignment_at_record_date).distinct()


def can_create_case_record(
    user,
    center: Center,
    enrollment: ServiceEnrollment,
    on_date,
    *,
    allowed_statuses=None,
) -> bool:
    allowed_statuses = allowed_statuses or {ServiceEnrollment.Status.ACTIVE}
    if (
        enrollment is None
        or on_date is None
        or enrollment.status_on(on_date) not in allowed_statuses
    ):
        return False
    placement = enrollment.placement_on(on_date) if enrollment and on_date else None
    if placement is None or placement.center_id != center.pk:
        return False
    if is_system_manager(user):
        return True
    if not accessible_centers(user).filter(pk=center.pk).exists():
        return False
    if is_coordinator(user):
        return True
    if not is_specialist(user):
        return False
    profile = specialist_profile_for_user(user)
    if profile is None:
        return False
    if not enrollments_for_user(user, center).filter(pk=enrollment.pk).exists():
        return False
    return (
        enrollment.specialist_assignments.filter(specialist=profile)
        .filter(
            Q(valid_to__isnull=True) | Q(valid_to__gt=on_date),
            valid_from__lte=on_date,
        )
        .exists()
    )


def can_change_case_record(user, center: Center, record) -> bool:
    return case_records_changeable_by_user(type(record), user, center).filter(pk=record.pk).exists()


def visits_for_user(user, center: Center | None = None, *, for_change: bool = False):
    selector = case_records_changeable_by_user if for_change else case_records_for_user
    return selector(ServiceVisit, user, center)


def schedules_for_user(user, center: Center | None = None, *, for_change: bool = False):
    queryset = EnrollmentServiceSchedule.objects.select_related(
        "enrollment__beneficiary",
        "enrollment__service",
        "activity",
        "delivery_location",
    )
    if is_system_manager(user):
        if center is None:
            return queryset
        return (
            queryset.filter(
                enrollment__center_placements__center=center,
            )
            .filter(
                Q(enrollment__center_placements__valid_to__isnull=True)
                | Q(enrollment__center_placements__valid_to__gt=F("schedule_month")),
                enrollment__center_placements__valid_from__lte=F("schedule_month"),
            )
            .distinct()
        )
    if center is None or not accessible_centers(user).filter(pk=center.pk).exists():
        return queryset.none()
    if is_coordinator(user):
        return (
            queryset.filter(
                enrollment__center_placements__center=center,
            )
            .filter(
                Q(enrollment__center_placements__valid_to__isnull=True)
                | Q(enrollment__center_placements__valid_to__gt=F("schedule_month")),
                enrollment__center_placements__valid_from__lte=F("schedule_month"),
            )
            .distinct()
        )
    if not is_specialist(user):
        return queryset.none()
    profile = specialist_profile_for_user(user)
    if profile is None:
        return queryset.none()
    result = queryset.filter(enrollment__in=enrollments_for_user(user, center))
    if for_change:
        prefix = "enrollment__specialist_assignments__"
        assignment_at_schedule_month = (
            Q(**{f"{prefix}specialist": profile})
            & Q(**{f"{prefix}valid_from__lte": F("schedule_month")})
            & (
                Q(**{f"{prefix}valid_to__isnull": True})
                | Q(**{f"{prefix}valid_to__gt": F("schedule_month")})
            )
        )
        result = result.filter(assignment_at_schedule_month)
    return result.distinct()


def assessments_for_user(user, center: Center | None = None, *, for_change: bool = False):
    selector = case_records_changeable_by_user if for_change else case_records_for_user
    queryset = selector(Assessment, user, center)
    return queryset.exclude(status=Assessment.Status.SUPERSEDED) if for_change else queryset


def current_assessments_for_user(user, center: Center | None = None):
    return assessments_for_user(user, center).exclude(status=Assessment.Status.SUPERSEDED)


def plans_for_user(user, center: Center | None = None, *, for_change: bool = False):
    selector = case_records_changeable_by_user if for_change else case_records_for_user
    return selector(IndividualPlan, user, center)


def summaries_for_user(user, center: Center | None = None):
    queryset = SpecialistMonthlyServiceSummary.objects.select_related(
        "center", "specialist__staff_profile__user"
    )
    if is_system_manager(user):
        return queryset.filter(center=center) if center else queryset
    if center is None or not accessible_centers(user).filter(pk=center.pk).exists():
        return queryset.none()
    if is_coordinator(user):
        return queryset.filter(center=center)
    if is_specialist(user):
        profile = specialist_profile_for_user(user)
        if profile:
            return queryset.filter(center=center, specialist=profile)
    return queryset.none()


def diagnoses_for_user(
    user,
    center: Center | None = None,
    *,
    enrollment: ServiceEnrollment | None = None,
):
    queryset = BeneficiaryDiagnosis.objects.select_related(
        "beneficiary", "definition", "enrollment__service"
    )
    if is_system_manager(user):
        result = queryset
    elif center is None or not accessible_centers(user).filter(pk=center.pk).exists():
        return queryset.none()
    elif is_coordinator(user):
        result = queryset.filter(enrollment__in=enrollments_for_user(user, center))
    elif is_specialist(user):
        authorized = enrollments_for_user(user, center)
        result = queryset.filter(
            visible_to_specialists=True,
            enrollment__in=authorized,
        )
    else:
        return queryset.none()
    if enrollment is not None:
        result = result.filter(enrollment=enrollment)
    return result.distinct()


def social_statuses_for_user(
    user,
    center: Center | None = None,
    *,
    enrollment: ServiceEnrollment | None = None,
):
    queryset = BeneficiarySocialStatus.objects.select_related(
        "beneficiary", "definition", "enrollment__service"
    )
    if is_system_manager(user):
        result = queryset
    elif center is None or not accessible_centers(user).filter(pk=center.pk).exists():
        return queryset.none()
    elif is_coordinator(user):
        result = queryset.filter(enrollment__in=enrollments_for_user(user, center))
    elif is_specialist(user):
        authorized = enrollments_for_user(user, center)
        result = queryset.filter(
            visible_to_specialists=True,
            enrollment__in=authorized,
        )
    else:
        return queryset.none()
    if enrollment is not None:
        result = result.filter(enrollment=enrollment)
    return result.distinct()


def can_view_restricted_beneficiary_fields(
    user,
    beneficiary: Beneficiary,
    center: Center | None = None,
) -> bool:
    if is_system_manager(user):
        return True
    if not is_coordinator(user):
        return False
    candidate_centers = accessible_centers(user)
    if center is None:
        return any(
            enrollments_for_user(user, candidate).filter(beneficiary=beneficiary).exists()
            for candidate in candidate_centers
        )
    return (
        candidate_centers.filter(pk=center.pk).exists()
        and enrollments_for_user(user, center).filter(beneficiary=beneficiary).exists()
    )


def get_authorized_object(queryset, pk):
    try:
        return queryset.get(pk=pk)
    except queryset.model.DoesNotExist as exc:
        raise Http404 from exc
