from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.accounts.roles import is_system_manager
from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.casework.forms import PrivateAttachmentForm
from apps.casework.models import AttachmentParentType, PrivateAttachment
from apps.core.authorization import (
    ACTIVE_CENTER_SESSION_KEY,
    accessible_centers,
    can_change_staff_directory,
    can_manage_center,
    can_view_staff_directory,
    get_authorized_object,
    staff_profiles_for_user,
)
from apps.core.decorators import active_center_required

from .forms import (
    CenterForm,
    NewSpecialistForm,
    SpecialistAssignmentForm,
    SpecialistProfileForm,
    StaffProfileForm,
)
from .models import Center, SpecialistCenterAssignment, SpecialistProfile, StaffProfile


def _safe_next(request) -> str:
    value = request.POST.get("next") or request.GET.get("next") or reverse("dashboard")
    parsed = urlparse(value)
    if parsed.netloc or parsed.scheme or not value.startswith("/"):
        return reverse("dashboard")
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
        raise PermissionDenied
    queryset = staff_profiles_for_user(request.user)
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    center_id = request.GET.get("center", "").strip()
    if query:
        queryset = queryset.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__email__icontains=query)
            | Q(employee_number__icontains=query)
            | Q(project_program__icontains=query)
            | Q(job_title__icontains=query)
            | Q(contact_number__icontains=query)
        )
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
            "centers": Center.objects.order_by("name"),
        },
    )


@login_required
def staff_detail(request, pk):
    if not can_view_staff_directory(request.user):
        raise PermissionDenied
    staff = get_authorized_object(staff_profiles_for_user(request.user), pk)
    record_event(
        actor=request.user,
        event_type=AuditEvent.EventType.SENSITIVE_READ,
        target_type="StaffProfile",
        target_id=staff.pk,
        center=staff.primary_center,
    )
    attachments = PrivateAttachment.objects.filter(
        parent_type=AttachmentParentType.STAFF_PROFILE,
        parent_id=staff.pk,
    ).select_related("uploaded_by", "center")
    return render(
        request,
        "centers/staff_detail.html",
        {
            "staff": staff,
            "attachments": attachments,
            "can_change_staff": can_change_staff_directory(request.user),
        },
    )


@login_required
def staff_update(request, pk):
    if not can_change_staff_directory(request.user):
        raise PermissionDenied
    staff = get_authorized_object(staff_profiles_for_user(request.user), pk)
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


@login_required
def staff_attachment_upload(request, pk):
    if not can_change_staff_directory(request.user):
        raise PermissionDenied
    staff = get_authorized_object(staff_profiles_for_user(request.user), pk)
    document_center = staff.primary_center or staff.centers.first()
    if document_center is None:
        messages.error(request, _("Assign the employee to a center before uploading documents."))
        return redirect("staff_detail", pk=staff.pk)
    attachment = PrivateAttachment(
        parent_type=AttachmentParentType.STAFF_PROFILE,
        parent_id=staff.pk,
        center=document_center,
        uploaded_by=request.user,
    )
    if request.method == "POST":
        upload = request.FILES.get("file")
        if upload:
            attachment.original_filename = Path(upload.name.replace("\\", "/")).name
        form = PrivateAttachmentForm(request.POST, request.FILES, instance=attachment)
        if form.is_valid():
            try:
                with transaction.atomic():
                    attachment = form.save(commit=False)
                    attachment.save()
                    record_event(
                        actor=request.user,
                        event_type=AuditEvent.EventType.CREATE,
                        target_type="PrivateAttachment",
                        target_id=attachment.pk,
                        center=attachment.center,
                        metadata={
                            "parent_type": AttachmentParentType.STAFF_PROFILE,
                            "file_extension": Path(upload.name).suffix.lower(),
                        },
                    )
            except Exception:
                if attachment.file.name:
                    attachment.file.storage.delete(attachment.file.name)
                raise
            messages.success(request, _("Staff document uploaded securely."))
            return redirect("staff_detail", pk=staff.pk)
    else:
        form = PrivateAttachmentForm(instance=attachment)
    return render(
        request,
        "casework/attachment_form.html",
        {
            "form": form,
            "parent": staff,
            "cancel_url": reverse("staff_detail", kwargs={"pk": staff.pk}),
        },
    )


@login_required
def staff_attachment_download(request, pk):
    if not can_view_staff_directory(request.user):
        raise PermissionDenied
    attachment = get_object_or_404(
        PrivateAttachment.objects.select_related("center"),
        pk=pk,
        parent_type=AttachmentParentType.STAFF_PROFILE,
    )
    get_authorized_object(staff_profiles_for_user(request.user), attachment.parent_id)
    record_event(
        actor=request.user,
        event_type=AuditEvent.EventType.DOWNLOAD,
        target_type="PrivateAttachment",
        target_id=attachment.pk,
        center=attachment.center,
        metadata={"file_extension": Path(attachment.original_filename).suffix.lower()},
    )
    return FileResponse(
        attachment.file.open("rb"),
        as_attachment=True,
        filename=Path(attachment.original_filename).name,
        content_type=attachment.content_type or "application/octet-stream",
    )


@login_required
def staff_attachment_delete(request, pk):
    if request.method != "POST":
        raise Http404
    if not can_change_staff_directory(request.user):
        raise PermissionDenied
    attachment = get_object_or_404(
        PrivateAttachment.objects.select_related("center"),
        pk=pk,
        parent_type=AttachmentParentType.STAFF_PROFILE,
    )
    staff = get_authorized_object(staff_profiles_for_user(request.user), attachment.parent_id)
    attachment_id = attachment.pk
    center = attachment.center
    with transaction.atomic():
        attachment.delete()
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.DELETE,
            target_type="PrivateAttachment",
            target_id=attachment_id,
            center=center,
        )
    messages.success(request, _("Staff document deleted."))
    return redirect("staff_detail", pk=staff.pk)


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
            "can_manage": can_manage_center(request.user, center),
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


@active_center_required
def specialist_create(request):
    center = request.ssk_center
    if not can_manage_center(request.user, center):
        raise PermissionDenied
    form = NewSpecialistForm(request.POST or None, center=center)
    if request.method == "POST" and form.is_valid():
        profile = form.save()
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.CREATE,
            target_type="SpecialistProfile",
            target_id=profile.pk,
            center=center,
        )
        messages.success(
            request,
            _("Specialist created. Use password reset to establish the first password."),
        )
        return redirect("center_detail")
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
