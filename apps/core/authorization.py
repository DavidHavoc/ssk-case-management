from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.http import Http404

from apps.accounts.roles import is_coordinator, is_specialist, is_system_manager
from apps.casework.models import (
    Assessment,
    AttachmentParentType,
    Beneficiary,
    IndividualPlan,
    PrivateAttachment,
    ServiceVisit,
    SpecialistMonthlyServiceSummary,
)
from apps.centers.models import Center, SpecialistProfile, StaffProfile

ACTIVE_CENTER_SESSION_KEY = "ssk_active_center"


class CenterSelectionRequired(PermissionDenied):
    pass


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
    if not getattr(user, "is_authenticated", False):
        return False
    return (
        is_system_manager(user)
        or user.has_perm("centers.view_staffprofile")
        or user.has_perm("centers.change_staffprofile")
    )


def can_change_staff_directory(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return is_system_manager(user) or user.has_perm("centers.change_staffprofile")


def staff_profiles_for_user(user) -> QuerySet[StaffProfile]:
    queryset = (
        StaffProfile.objects.select_related(
            "user",
            "primary_center",
            "specialist_profile",
        )
        .prefetch_related("centers", "user__groups")
        .order_by("user__last_name", "user__first_name", "employee_number")
    )
    if can_view_staff_directory(user):
        return queryset
    return queryset.none()


def specialist_profile_for_user(user) -> SpecialistProfile | None:
    if not getattr(user, "is_authenticated", False):
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


def beneficiaries_for_user(user, center: Center | None = None) -> QuerySet[Beneficiary]:
    queryset = Beneficiary.objects.select_related("center").prefetch_related(
        "specialist_assignments__specialist__staff_profile__user"
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
            return queryset.filter(
                center=center, specialist_assignments__specialist=profile
            ).distinct()
    return queryset.none()


def case_records_for_user(model, user, center: Center | None = None):
    queryset = model.objects.select_related(
        "center", "beneficiary", "specialist__staff_profile__user"
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
            return (
                queryset.filter(center=center)
                .filter(
                    Q(specialist=profile)
                    | Q(beneficiary__specialist_assignments__specialist=profile)
                )
                .distinct()
            )
    return queryset.none()


def visits_for_user(user, center: Center | None = None):
    return case_records_for_user(ServiceVisit, user, center)


def assessments_for_user(user, center: Center | None = None):
    return case_records_for_user(Assessment, user, center)


def plans_for_user(user, center: Center | None = None):
    return case_records_for_user(IndividualPlan, user, center)


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


def can_view_restricted_beneficiary_fields(user, beneficiary: Beneficiary) -> bool:
    return is_system_manager(user) or (
        is_coordinator(user) and accessible_centers(user).filter(pk=beneficiary.center_id).exists()
    )


def get_authorized_object(queryset, pk):
    try:
        return queryset.get(pk=pk)
    except queryset.model.DoesNotExist as exc:
        raise Http404 from exc


def parent_for_attachment(parent_type: str, parent_id, user, center: Center):
    mapping = {
        AttachmentParentType.BENEFICIARY: beneficiaries_for_user(user, center),
        AttachmentParentType.SERVICE_VISIT: visits_for_user(user, center),
        AttachmentParentType.ASSESSMENT: assessments_for_user(user, center),
        AttachmentParentType.INDIVIDUAL_PLAN: plans_for_user(user, center),
    }
    queryset = mapping.get(parent_type)
    if queryset is None:
        raise Http404
    parent = get_authorized_object(queryset, parent_id)
    if parent_type == AttachmentParentType.BENEFICIARY:
        if not can_view_restricted_beneficiary_fields(user, parent):
            raise Http404
    return parent


def attachments_for_parent(parent_type: str, parent_id, user, center: Center):
    parent_for_attachment(parent_type, parent_id, user, center)
    return PrivateAttachment.objects.filter(
        parent_type=parent_type, parent_id=parent_id, center=center
    ).select_related("uploaded_by", "center")


def attachment_for_download(pk, user, center: Center) -> PrivateAttachment:
    attachment = get_authorized_object(PrivateAttachment.objects.select_related("center"), pk)
    if attachment.center_id != center.id and not is_system_manager(user):
        raise Http404
    parent_for_attachment(attachment.parent_type, attachment.parent_id, user, attachment.center)
    return attachment
