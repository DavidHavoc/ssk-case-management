from __future__ import annotations

from urllib.parse import urlparse
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from apps.accounts.roles import is_system_manager
from apps.accounts.services import issue_temporary_access_code
from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.casework.models import AttachmentParentType, CenterServiceOffering
from apps.casework.private_attachments import (
    AttachmentParentCenterRequired,
    staff_attachments,
)
from apps.core.authorization import (
    ACTIVE_CENTER_SESSION_KEY,
    accessible_centers,
    can_change_staff_directory,
    can_manage_center,
    can_view_staff_directory,
    can_view_staff_hr_fields,
    casework_home_route,
    get_authorized_object,
    staff_directory_centers_for_user,
    staff_profiles_for_user,
)
from apps.core.decorators import active_center_required

from .forms import (
    CenterForm,
    CenterServiceOfferingForm,
    NewSpecialistForm,
    SpecialistAssignmentForm,
    SpecialistProfileForm,
    StaffProfileForm,
)
from .models import SpecialistCenterAssignment, SpecialistProfile, StaffProfile


def _safe_next(request) -> str:
    default_route = casework_home_route(request.user)
    value = request.POST.get("next") or request.GET.get("next") or reverse(default_route)
    parsed = urlparse(value)
    if parsed.netloc or parsed.scheme or not value.startswith("/"):
        return reverse(default_route)
    return value


@login_required
def center_select(request):
    centers = accessible_centers(request.user, active_only=True)
    if request.method == "POST":
        center = get_object_or_404(centers, pk=request.POST.get("center"))
        request.session[ACTIVE_CENTER_SESSION_KEY] = str(center.pk)
        messages.success(
            request, _("Active center changed to %(center)s.") % {"center": center.name}
        )
        return redirect(_safe_next(request))
    if not centers.exists():
        raise PermissionDenied
    return render(
        request,
        "centers/center_select.html",
        {"centers": centers, "next": _safe_next(request)},
    )


@login_required
def center_list(request):
    return render(
        request,
        "centers/center_list.html",
        {
            "centers": accessible_centers(request.user),
            "can_create": is_system_manager(request.user),
        },
    )


@login_required
def staff_list(request):
    if not can_view_staff_directory(request.user):
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.SENSITIVE_READ,
            target_type="StaffDirectory",
            outcome=AuditEvent.Outcome.DENIED,
        )
        raise PermissionDenied
    queryset = staff_profiles_for_user(request.user)
    show_hr_fields = can_view_staff_hr_fields(request.user)
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    center_id = request.GET.get("center", "").strip()
    if query:
        search = (
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(employee_number__icontains=query)
            | Q(project_program__icontains=query)
            | Q(job_title__icontains=query)
        )
        if show_hr_fields:
            search |= Q(user__email__icontains=query) | Q(contact_number__icontains=query)
        queryset = queryset.filter(search)
    if status in StaffProfile.Status.values:
        queryset = queryset.filter(status=status)
    if center_id:
        try:
            center_uuid = UUID(center_id)
        except ValueError:
            queryset = queryset.none()
        else:
            queryset = queryset.filter(centers__pk=center_uuid).distinct()
    page_obj = Paginator(queryset, 30).get_page(request.GET.get("page"))
    record_event(
        actor=request.user,
        event_type=AuditEvent.EventType.SENSITIVE_READ,
        target_type="StaffDirectory",
    )
    return render(
        request,
        "centers/staff_list.html",
        {
            "page_obj": page_obj,
            "query": query,
            "selected_status": status,
            "selected_center": center_id,
            "status_choices": StaffProfile.Status.choices,
            "centers": staff_directory_centers_for_user(request.user),
            "show_hr_fields": show_hr_fields,
        },
    )


@login_required
def staff_detail(request, pk):
    if not can_view_staff_directory(request.user):
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.SENSITIVE_READ,
            target_type="StaffProfile",
            target_id=pk,
            outcome=AuditEvent.Outcome.DENIED,
        )
        raise PermissionDenied
    try:
        staff = get_authorized_object(staff_profiles_for_user(request.user), pk)
    except Http404:
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.SENSITIVE_READ,
            target_type="StaffProfile",
            target_id=pk,
            outcome=AuditEvent.Outcome.DENIED,
        )
        raise
    record_event(
        actor=request.user,
        event_type=AuditEvent.EventType.SENSITIVE_READ,
        target_type="StaffProfile",
        target_id=staff.pk,
        center=staff.primary_center,
    )
    show_hr_fields = can_view_staff_hr_fields(request.user)
    attachments = (
        staff_attachments(request.user).list(AttachmentParentType.STAFF_PROFILE, staff.pk)
        if show_hr_fields
        else ()
    )
    return render(
        request,
        "centers/staff_detail.html",
        {
            "staff": staff,
            "attachments": attachments,
            "can_change_staff": staff_profiles_for_user(request.user, change=True)
            .filter(pk=staff.pk)
            .exists(),
            "show_hr_fields": show_hr_fields,
        },
    )


@login_required
def staff_update(request, pk):
    if not can_change_staff_directory(request.user):
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.UPDATE,
            target_type="StaffProfile",
            target_id=pk,
            outcome=AuditEvent.Outcome.DENIED,
        )
        raise PermissionDenied
    try:
        staff = get_authorized_object(staff_profiles_for_user(request.user, change=True), pk)
    except Http404:
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.UPDATE,
            target_type="StaffProfile",
            target_id=pk,
            outcome=AuditEvent.Outcome.DENIED,
        )
        raise
    form = StaffProfileForm(request.POST or None, instance=staff)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
            record_event(
                actor=request.user,
                event_type=AuditEvent.EventType.UPDATE,
                target_type="StaffProfile",
                target_id=staff.pk,
                center=staff.primary_center,
            )
        messages.success(request, _("Employee profile updated."))
        return redirect("staff_detail", pk=staff.pk)
    return render(
        request,
        "centers/staff_form.html",
        {"form": form, "staff": staff, "title": _("Update employee")},
    )


@never_cache
@login_required
def staff_reset_access(request, pk):
    if request.method != "POST":
        raise Http404
    if not can_change_staff_directory(request.user):
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.UPDATE,
            target_type="StaffProfile",
            target_id=pk,
            outcome=AuditEvent.Outcome.DENIED,
        )
        raise PermissionDenied
    try:
        staff = get_authorized_object(staff_profiles_for_user(request.user, change=True), pk)
    except Http404:
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.UPDATE,
            target_type="StaffProfile",
            target_id=pk,
            outcome=AuditEvent.Outcome.DENIED,
        )
        raise
    if staff.user_id == request.user.pk:
        messages.error(request, _("You cannot reset your own access code here."))
        return redirect("staff_detail", pk=staff.pk)
    with transaction.atomic():
        temporary_code = issue_temporary_access_code(staff.user)
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.UPDATE,
            target_type="StaffProfile",
            target_id=staff.pk,
            center=staff.primary_center,
            metadata={"result": "temporary_access_code_issued"},
        )
    return render(
        request,
        "centers/access_code_issued.html",
        {
            "staff": staff,
            "temporary_code": temporary_code,
            "access_code_action": _("New access code generated"),
            "can_view_staff": True,
        },
    )


@login_required
def staff_attachment_upload(request, pk):
    try:
        result = staff_attachments(request.user).upload(
            AttachmentParentType.STAFF_PROFILE,
            pk,
            data=request.POST if request.method == "POST" else None,
            files=request.FILES if request.method == "POST" else None,
        )
    except AttachmentParentCenterRequired:
        messages.error(request, _("Assign the employee to a center before uploading documents."))
        return redirect("staff_detail", pk=pk)
    if result.saved:
        messages.success(request, _("Staff document uploaded securely."))
        return redirect(result.redirect_url)
    return render(
        request,
        "casework/attachment_form.html",
        {
            "form": result.form,
            "parent": result.parent,
            "cancel_url": result.redirect_url,
        },
    )


@login_required
def staff_attachment_download(request, pk):
    return staff_attachments(request.user).download(pk)


@login_required
def staff_attachment_delete(request, pk):
    if request.method != "POST":
        raise Http404
    redirect_url = staff_attachments(request.user).delete(pk)
    messages.success(request, _("Staff document deleted."))
    return redirect(redirect_url)


@active_center_required
def center_detail(request):
    center = request.ssk_center
    assignments = SpecialistCenterAssignment.objects.filter(center=center).select_related(
        "specialist__staff_profile__user"
    )
    record_event(
        actor=request.user,
        event_type=AuditEvent.EventType.SENSITIVE_READ,
        target_type="CenterRoster",
        target_id=center.pk,
        center=center,
    )
    return render(
        request,
        "centers/center_detail.html",
        {
            "center": center,
            "assignments": assignments,
            "service_offerings": center.service_offerings.select_related("service"),
            "can_manage": can_manage_center(request.user, center),
            "can_manage_offerings": is_system_manager(request.user),
        },
    )


@login_required
def center_create(request):
    if not is_system_manager(request.user):
        raise PermissionDenied
    form = CenterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        center = form.save()
        request.session[ACTIVE_CENTER_SESSION_KEY] = str(center.pk)
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.CREATE,
            target_type="Center",
            target_id=center.pk,
            center=center,
        )
        messages.success(request, _("Center created."))
        return redirect("center_detail")
    return render(request, "centers/center_form.html", {"form": form, "title": _("New center")})


@active_center_required
def center_update(request):
    center = request.ssk_center
    if not can_manage_center(request.user, center):
        raise PermissionDenied
    form = CenterForm(request.POST or None, instance=center)
    if request.method == "POST" and form.is_valid():
        form.save()
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.UPDATE,
            target_type="Center",
            target_id=center.pk,
            center=center,
        )
        messages.success(request, _("Center updated."))
        return redirect("center_detail")
    return render(request, "centers/center_form.html", {"form": form, "title": _("Update center")})


@active_center_required
def service_offering_create(request):
    center = request.ssk_center
    if not is_system_manager(request.user):
        raise PermissionDenied
    form = CenterServiceOfferingForm(request.POST or None, center=center)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            offering = form.save()
            record_event(
                actor=request.user,
                event_type=AuditEvent.EventType.CREATE,
                target_type="CenterServiceOffering",
                target_id=offering.pk,
                center=center,
            )
        messages.success(request, _("Service offering added."))
        return redirect("center_detail")
    return render(
        request,
        "centers/service_offering_form.html",
        {"form": form, "center": center, "title": _("Add service offering")},
    )


@active_center_required
def service_offering_update(request, pk):
    center = request.ssk_center
    if not is_system_manager(request.user):
        raise PermissionDenied
    offering = get_object_or_404(
        CenterServiceOffering.objects.select_related("service").filter(center=center),
        pk=pk,
    )
    form = CenterServiceOfferingForm(request.POST or None, instance=offering, center=center)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
            record_event(
                actor=request.user,
                event_type=AuditEvent.EventType.UPDATE,
                target_type="CenterServiceOffering",
                target_id=offering.pk,
                center=center,
            )
        messages.success(request, _("Service offering updated."))
        return redirect("center_detail")
    return render(
        request,
        "centers/service_offering_form.html",
        {
            "form": form,
            "center": center,
            "offering": offering,
            "title": _("Update service offering"),
        },
    )


@active_center_required
def center_delete(request):
    if not is_system_manager(request.user):
        raise PermissionDenied
    center = request.ssk_center
    if request.method == "POST":
        center_id = center.pk
        try:
            with transaction.atomic():
                center.delete()
                record_event(
                    actor=request.user,
                    event_type=AuditEvent.EventType.DELETE,
                    target_type="Center",
                    target_id=center_id,
                )
        except ProtectedError:
            messages.error(
                request, _("This center is referenced by other records and cannot be deleted.")
            )
            return render(
                request,
                "casework/delete_confirm.html",
                {"object": center, "cancel_url": reverse("center_detail")},
                status=409,
            )
        request.session.pop(ACTIVE_CENTER_SESSION_KEY, None)
        messages.success(request, _("Center deleted."))
        return redirect("center_list")
    return render(
        request,
        "casework/delete_confirm.html",
        {"object": center, "cancel_url": reverse("center_detail")},
    )


@active_center_required
def specialist_assign(request):
    center = request.ssk_center
    if not can_manage_center(request.user, center):
        raise PermissionDenied
    form = SpecialistAssignmentForm(request.POST or None, center=center)
    if request.method == "POST" and form.is_valid():
        assignment = form.save()
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.CREATE,
            target_type="SpecialistCenterAssignment",
            target_id=assignment.pk,
            center=center,
        )
        messages.success(request, _("Specialist added to the center roster."))
        return redirect("center_detail")
    return render(
        request,
        "centers/specialist_form.html",
        {"form": form, "title": _("Link existing specialist")},
    )


@never_cache
@active_center_required
def specialist_create(request):
    center = request.ssk_center
    if not can_manage_center(request.user, center):
        raise PermissionDenied
    form = NewSpecialistForm(request.POST or None, center=center)
    if request.method == "POST" and form.is_valid():
        profile, temporary_code = form.save()
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.CREATE,
            target_type="SpecialistProfile",
            target_id=profile.pk,
            center=center,
        )
        return render(
            request,
            "centers/access_code_issued.html",
            {
                "staff": profile.staff_profile,
                "temporary_code": temporary_code,
                "access_code_action": _("Employee account created"),
                "can_view_staff": can_view_staff_directory(request.user),
            },
        )
    return render(
        request,
        "centers/specialist_form.html",
        {"form": form, "title": _("Create specialist")},
    )


@active_center_required
def specialist_update(request, pk):
    center = request.ssk_center
    if not can_manage_center(request.user, center):
        raise PermissionDenied
    profile = get_object_or_404(
        SpecialistProfile.objects.filter(center_assignments__center=center).distinct(), pk=pk
    )
    form = SpecialistProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.UPDATE,
            target_type="SpecialistProfile",
            target_id=profile.pk,
            center=center,
        )
        messages.success(request, _("Specialist profile updated."))
        return redirect("center_detail")
    return render(
        request,
        "centers/specialist_form.html",
        {"form": form, "title": _("Update specialist")},
    )


@active_center_required
def specialist_remove(request, pk):
    if request.method != "POST":
        raise Http404
    center = request.ssk_center
    if not can_manage_center(request.user, center):
        raise PermissionDenied
    assignment = get_object_or_404(SpecialistCenterAssignment.objects.filter(center=center), pk=pk)
    assignment_id = assignment.pk
    assignment.delete()
    record_event(
        actor=request.user,
        event_type=AuditEvent.EventType.DELETE,
        target_type="SpecialistCenterAssignment",
        target_id=assignment_id,
        center=center,
    )
    messages.success(request, _("Specialist removed from this center roster."))
    return redirect("center_detail")
