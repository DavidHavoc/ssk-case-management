from __future__ import annotations

from urllib.parse import urlparse

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.accounts.roles import is_system_manager
from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.core.authorization import (
    ACTIVE_CENTER_SESSION_KEY,
    accessible_centers,
    can_manage_center,
)
from apps.core.decorators import active_center_required

from .forms import (
    CenterForm,
    NewSpecialistForm,
    SpecialistAssignmentForm,
    SpecialistProfileForm,
)
from .models import SpecialistCenterAssignment, SpecialistProfile


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
