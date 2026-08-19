from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from django import forms
from django.apps import apps
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q, Subquery
from django.http import FileResponse, Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.core.forms import StyledForm, StyledModelForm

from .models import AttachmentParentType, PrivateAttachment
from .validators import validate_private_upload

__all__ = (
    "AttachmentParentCenterRequired",
    "case_attachments",
    "staff_attachments",
)


class AttachmentParentCenterRequired(Exception):
    pass


@dataclass(frozen=True)
class _AttachmentParentPolicy:
    parent_type: str
    model_label: str
    detail_route: str
    authorization_adapter: Callable
    center_adapter: Callable
    requires_active_center: bool = True
    requires_document_type: bool = False
    uses_supporting_file_copy: bool = False


def _beneficiary_parent_adapter(parent_type: str, parent_id, user, center, action: str):
    from apps.core.authorization import (
        beneficiaries_for_user,
        can_view_restricted_beneficiary_fields,
        get_authorized_object,
    )

    if center is None:
        raise Http404
    parent = get_authorized_object(beneficiaries_for_user(user, center), parent_id)
    if not can_view_restricted_beneficiary_fields(user, parent):
        raise Http404
    return parent


def _visit_parent_adapter(parent_type: str, parent_id, user, center, action: str):
    from apps.core.authorization import get_authorized_object, visits_for_user

    if center is None:
        raise Http404
    return get_authorized_object(visits_for_user(user, center), parent_id)


def _assessment_parent_adapter(parent_type: str, parent_id, user, center, action: str):
    from apps.core.authorization import assessments_for_user, get_authorized_object

    if center is None:
        raise Http404
    return get_authorized_object(assessments_for_user(user, center), parent_id)


def _plan_parent_adapter(parent_type: str, parent_id, user, center, action: str):
    from apps.core.authorization import get_authorized_object, plans_for_user

    if center is None:
        raise Http404
    return get_authorized_object(plans_for_user(user, center), parent_id)


def _staff_parent_adapter(parent_type: str, parent_id, user, center, action: str):
    from apps.core.authorization import (
        can_change_staff_directory,
        can_view_staff_directory,
        get_authorized_object,
        staff_profiles_for_user,
    )

    allowed = (
        can_change_staff_directory(user) if action == "change" else can_view_staff_directory(user)
    )
    if not allowed:
        raise PermissionDenied
    return get_authorized_object(staff_profiles_for_user(user), parent_id)


def _case_center(parent):
    return parent.center


def _staff_center(parent):
    return parent.primary_center or parent.centers.first()


_ATTACHMENT_PARENT_POLICIES = {
    AttachmentParentType.BENEFICIARY: _AttachmentParentPolicy(
        parent_type=AttachmentParentType.BENEFICIARY,
        model_label="casework.Beneficiary",
        detail_route="beneficiary_detail",
        authorization_adapter=_beneficiary_parent_adapter,
        center_adapter=_case_center,
        uses_supporting_file_copy=True,
    ),
    AttachmentParentType.SERVICE_VISIT: _AttachmentParentPolicy(
        parent_type=AttachmentParentType.SERVICE_VISIT,
        model_label="casework.ServiceVisit",
        detail_route="visit_detail",
        authorization_adapter=_visit_parent_adapter,
        center_adapter=_case_center,
        uses_supporting_file_copy=True,
    ),
    AttachmentParentType.ASSESSMENT: _AttachmentParentPolicy(
        parent_type=AttachmentParentType.ASSESSMENT,
        model_label="casework.Assessment",
        detail_route="assessment_detail",
        authorization_adapter=_assessment_parent_adapter,
        center_adapter=_case_center,
    ),
    AttachmentParentType.INDIVIDUAL_PLAN: _AttachmentParentPolicy(
        parent_type=AttachmentParentType.INDIVIDUAL_PLAN,
        model_label="casework.IndividualPlan",
        detail_route="plan_detail",
        authorization_adapter=_plan_parent_adapter,
        center_adapter=_case_center,
    ),
    AttachmentParentType.STAFF_PROFILE: _AttachmentParentPolicy(
        parent_type=AttachmentParentType.STAFF_PROFILE,
        model_label="centers.StaffProfile",
        detail_route="staff_detail",
        authorization_adapter=_staff_parent_adapter,
        center_adapter=_staff_center,
        requires_active_center=False,
        requires_document_type=True,
    ),
}

_CASE_ATTACHMENT_PARENT_TYPES = frozenset(
    {
        AttachmentParentType.BENEFICIARY,
        AttachmentParentType.SERVICE_VISIT,
        AttachmentParentType.ASSESSMENT,
        AttachmentParentType.INDIVIDUAL_PLAN,
    }
)
_STAFF_ATTACHMENT_PARENT_TYPES = frozenset({AttachmentParentType.STAFF_PROFILE})


def _parent_policy(parent_type: str) -> _AttachmentParentPolicy:
    policy = _ATTACHMENT_PARENT_POLICIES.get(parent_type)
    if policy is None:
        raise Http404
    return policy


def _parent_model(parent_type: str):
    policy = _ATTACHMENT_PARENT_POLICIES.get(parent_type)
    if policy is None:
        return None
    return apps.get_model(policy.model_label)


def _center_for_parent(parent_type: str, parent):
    policy = _parent_policy(parent_type)
    return policy.center_adapter(parent)


def _authorize_parent(
    parent_type: str,
    parent_id,
    user,
    *,
    center=None,
    action: str = "view",
    allowed_parent_types=None,
):
    if action not in {"view", "change"}:
        raise ValueError("Unsupported attachment authorization action.")
    policy = _parent_policy(parent_type)
    if allowed_parent_types is not None and parent_type not in allowed_parent_types:
        raise Http404
    if policy.requires_active_center and center is None:
        raise Http404
    return policy.authorization_adapter(parent_type, parent_id, user, center, action)


def _attachments_for_parent(
    parent_type: str,
    parent_id,
    user,
    *,
    center=None,
    allowed_parent_types=None,
):
    parent = _authorize_parent(
        parent_type,
        parent_id,
        user,
        center=center,
        allowed_parent_types=allowed_parent_types,
    )
    filters = {"parent_type": parent_type, "parent_id": parent.pk}
    if _parent_policy(parent_type).requires_active_center:
        filters["center"] = _center_for_parent(parent_type, parent)
    return PrivateAttachment.objects.filter(**filters).select_related("uploaded_by", "center")


def _timeline_attachments_for_beneficiary(beneficiary, user, *, center):
    from apps.core.authorization import (
        assessments_for_user,
        beneficiaries_for_user,
        can_view_restricted_beneficiary_fields,
        get_authorized_object,
        plans_for_user,
        visits_for_user,
    )

    if center is None:
        raise Http404
    beneficiary = get_authorized_object(beneficiaries_for_user(user, center), beneficiary.pk)
    visits = visits_for_user(user, center).filter(beneficiary=beneficiary).order_by()
    assessments = assessments_for_user(user, center).filter(beneficiary=beneficiary).order_by()
    plans = plans_for_user(user, center).filter(beneficiary=beneficiary).order_by()

    parent_scope = (
        Q(
            parent_type=AttachmentParentType.SERVICE_VISIT,
            parent_id__in=Subquery(visits.values("pk")),
        )
        | Q(
            parent_type=AttachmentParentType.ASSESSMENT,
            parent_id__in=Subquery(assessments.values("pk")),
        )
        | Q(
            parent_type=AttachmentParentType.INDIVIDUAL_PLAN,
            parent_id__in=Subquery(plans.values("pk")),
        )
    )
    if can_view_restricted_beneficiary_fields(user, beneficiary):
        parent_scope |= Q(
            parent_type=AttachmentParentType.BENEFICIARY,
            parent_id=beneficiary.pk,
        )

    return PrivateAttachment.objects.filter(center=center).filter(parent_scope)


def _parent_detail_url(parent_type: str, parent_id) -> str:
    return reverse(_parent_policy(parent_type).detail_route, kwargs={"pk": parent_id})


class _PrivateAttachmentForm(StyledModelForm):
    class Meta:
        model = PrivateAttachment
        fields = ("document_type", "file")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        policy = _parent_policy(self.instance.parent_type)
        if policy.requires_document_type:
            self.fields["document_type"].required = True
        else:
            self.fields.pop("document_type", None)

        if policy.uses_supporting_file_copy:
            file_field = self.fields["file"]
            file_field.label = _("PDF or supporting file")
            file_field.help_text = _(
                "PDF files are supported. You can add more than one document by uploading "
                "them separately. Maximum file size: %(size)s MB."
            ) % {"size": settings.MAX_UPLOAD_SIZE // (1024 * 1024)}
            file_field.widget.attrs["accept"] = ",".join(sorted(settings.ALLOWED_UPLOAD_EXTENSIONS))


class _OptionalPrivateAttachmentForm(StyledForm):
    file = forms.FileField(required=False, validators=[validate_private_upload])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        file_field = self.fields["file"]
        file_field.label = _("PDF or supporting file")
        file_field.help_text = _(
            "Optional. You can upload additional documents after saving. Maximum file size: "
            "%(size)s MB."
        ) % {"size": settings.MAX_UPLOAD_SIZE // (1024 * 1024)}
        file_field.widget.attrs["accept"] = ",".join(sorted(settings.ALLOWED_UPLOAD_EXTENSIONS))
        self.apply_styles()


def _attachment_draft(*, parent_type: str, parent, actor) -> PrivateAttachment:
    center = _center_for_parent(parent_type, parent)
    if center is None:
        raise AttachmentParentCenterRequired
    return PrivateAttachment(
        parent_type=parent_type,
        parent_id=parent.pk,
        center=center,
        uploaded_by=actor,
    )


def _upload_form(*, parent_type: str, parent, actor, data=None, files=None):
    attachment = _attachment_draft(parent_type=parent_type, parent=parent, actor=actor)
    upload = files.get("file") if files else None
    if upload:
        attachment.original_filename = Path(upload.name.replace("\\", "/")).name
    return _PrivateAttachmentForm(data, files, instance=attachment)


def _cleanup_attachment_file(attachment: PrivateAttachment | None) -> None:
    if (
        attachment
        and attachment.file
        and attachment.file.name
        and getattr(attachment.file, "_committed", False)
    ):
        attachment.file.storage.delete(attachment.file.name)


class _AttachmentUploader:
    def __init__(self):
        self._stored: list[PrivateAttachment] = []

    def save(self, attachment: PrivateAttachment, *, actor) -> PrivateAttachment:
        attachment.uploaded_by = actor
        try:
            attachment.save()
        except Exception:
            _cleanup_attachment_file(attachment)
            raise
        self._stored.append(attachment)
        record_event(
            actor=actor,
            event_type=AuditEvent.EventType.CREATE,
            target_type="PrivateAttachment",
            target_id=attachment.pk,
            center=attachment.center,
            metadata={
                "parent_type": attachment.parent_type,
                "file_extension": Path(attachment.original_filename).suffix.lower(),
            },
        )
        return attachment

    def create(
        self,
        *,
        parent_type: str,
        parent,
        upload,
        actor,
        document_type: str = "",
    ) -> PrivateAttachment | None:
        if not upload:
            return None
        attachment = _attachment_draft(parent_type=parent_type, parent=parent, actor=actor)
        attachment.file = upload
        attachment.original_filename = Path(upload.name.replace("\\", "/")).name
        attachment.document_type = document_type
        return self.save(attachment, actor=actor)

    def cleanup(self) -> None:
        for attachment in self._stored:
            _cleanup_attachment_file(attachment)


@contextmanager
def _attachment_transaction() -> Iterator[_AttachmentUploader]:
    uploader = _AttachmentUploader()
    try:
        with transaction.atomic():
            yield uploader
    except Exception:
        uploader.cleanup()
        raise


def _authorized_attachment(
    pk,
    user,
    *,
    center=None,
    action: str = "view",
    allowed_parent_types=None,
) -> PrivateAttachment:
    try:
        attachment = PrivateAttachment.objects.select_related("center").get(pk=pk)
    except PrivateAttachment.DoesNotExist as exc:
        raise Http404 from exc
    if allowed_parent_types is not None and attachment.parent_type not in allowed_parent_types:
        raise Http404
    policy = _parent_policy(attachment.parent_type)
    if policy.requires_active_center:
        if center is None or attachment.center_id != center.id:
            raise Http404
        authorization_center = center
    else:
        authorization_center = None
    _authorize_parent(
        attachment.parent_type,
        attachment.parent_id,
        user,
        center=authorization_center,
        action=action,
        allowed_parent_types=allowed_parent_types,
    )
    return attachment


def _download_response(
    pk,
    user,
    *,
    center=None,
    allowed_parent_types=None,
) -> FileResponse:
    try:
        attachment = _authorized_attachment(
            pk,
            user,
            center=center,
            allowed_parent_types=allowed_parent_types,
        )
    except (Http404, PermissionDenied):
        record_event(
            actor=user,
            event_type=AuditEvent.EventType.DOWNLOAD,
            target_type="PrivateAttachment",
            target_id=pk,
            outcome=AuditEvent.Outcome.DENIED,
        )
        raise
    record_event(
        actor=user,
        event_type=AuditEvent.EventType.DOWNLOAD,
        target_type="PrivateAttachment",
        target_id=attachment.pk,
        center=attachment.center,
        metadata={"file_extension": Path(attachment.original_filename).suffix.lower()},
    )
    response = FileResponse(
        attachment.file.open("rb"),
        as_attachment=True,
        filename=Path(attachment.original_filename).name,
        content_type=attachment.content_type or "application/octet-stream",
    )
    response["Cache-Control"] = "private, no-store"
    response["Pragma"] = "no-cache"
    return response


def _delete_attachment(
    pk,
    user,
    *,
    center=None,
    allowed_parent_types=None,
) -> str:
    attachment = _authorized_attachment(
        pk,
        user,
        center=center,
        action="change",
        allowed_parent_types=allowed_parent_types,
    )
    redirect_url = _parent_detail_url(attachment.parent_type, attachment.parent_id)
    attachment_id = attachment.pk
    attachment_center = attachment.center
    with transaction.atomic():
        attachment.delete()
        record_event(
            actor=user,
            event_type=AuditEvent.EventType.DELETE,
            target_type="PrivateAttachment",
            target_id=attachment_id,
            center=attachment_center,
        )
    return redirect_url


@dataclass(frozen=True)
class _AttachmentUploadResult:
    parent: object
    form: _PrivateAttachmentForm
    redirect_url: str
    saved: bool


class _BoundAttachmentUploader:
    def __init__(self, workflow, uploader: _AttachmentUploader):
        self._workflow = workflow
        self._uploader = uploader

    def create(
        self,
        *,
        parent_type: str,
        parent,
        upload,
        document_type: str = "",
    ) -> PrivateAttachment | None:
        if not upload:
            return None
        authorized_parent = _authorize_parent(
            parent_type,
            parent.pk,
            self._workflow._actor,
            center=self._workflow._center,
            action="change",
            allowed_parent_types=self._workflow._allowed_parent_types,
        )
        return self._uploader.create(
            parent_type=parent_type,
            parent=authorized_parent,
            upload=upload,
            actor=self._workflow._actor,
            document_type=document_type,
        )


class _AttachmentWorkflow:
    def __init__(self, *, actor, center, allowed_parent_types):
        self._actor = actor
        self._center = center
        self._allowed_parent_types = allowed_parent_types

    def list(self, parent_type: str, parent_id):
        return _attachments_for_parent(
            parent_type,
            parent_id,
            self._actor,
            center=self._center,
            allowed_parent_types=self._allowed_parent_types,
        )

    def timeline_for_beneficiary(self, beneficiary):
        return _timeline_attachments_for_beneficiary(
            beneficiary,
            self._actor,
            center=self._center,
        )

    def optional_form(self, data=None, files=None, *, prefix=None):
        return _OptionalPrivateAttachmentForm(data, files, prefix=prefix)

    @contextmanager
    def atomic_uploads(self) -> Iterator[_BoundAttachmentUploader]:
        with _attachment_transaction() as uploader:
            yield _BoundAttachmentUploader(self, uploader)

    def upload(self, parent_type: str, parent_id, *, data=None, files=None):
        parent = _authorize_parent(
            parent_type,
            parent_id,
            self._actor,
            center=self._center,
            action="change",
            allowed_parent_types=self._allowed_parent_types,
        )
        form = _upload_form(
            parent_type=parent_type,
            parent=parent,
            actor=self._actor,
            data=data,
            files=files,
        )
        saved = False
        if form.is_bound and form.is_valid():
            with _attachment_transaction() as uploader:
                uploader.save(form.save(commit=False), actor=self._actor)
            saved = True
        return _AttachmentUploadResult(
            parent=parent,
            form=form,
            redirect_url=_parent_detail_url(parent_type, parent.pk),
            saved=saved,
        )

    def download(self, pk):
        return _download_response(
            pk,
            self._actor,
            center=self._center,
            allowed_parent_types=self._allowed_parent_types,
        )

    def delete(self, pk) -> str:
        return _delete_attachment(
            pk,
            self._actor,
            center=self._center,
            allowed_parent_types=self._allowed_parent_types,
        )


def case_attachments(actor, center) -> _AttachmentWorkflow:
    return _AttachmentWorkflow(
        actor=actor,
        center=center,
        allowed_parent_types=_CASE_ATTACHMENT_PARENT_TYPES,
    )


def staff_attachments(actor) -> _AttachmentWorkflow:
    return _AttachmentWorkflow(
        actor=actor,
        center=None,
        allowed_parent_types=_STAFF_ATTACHMENT_PARENT_TYPES,
    )


def _schedule_file_cleanup(attachment: PrivateAttachment) -> None:
    if attachment.file:
        storage = attachment.file.storage
        name = attachment.file.name
        transaction.on_commit(lambda: storage.delete(name))
