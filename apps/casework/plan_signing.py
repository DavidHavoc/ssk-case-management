"""Review-bound, append-only plan signing using the consent signature controls."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid

from django import forms
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.http import Http404
from django.template.loader import render_to_string
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.centers.models import Center
from apps.core.authorization import get_authorized_object, plans_for_user

from .assessment_signing import CARE_NOTICE
from .consent_signing import (
    DOCUMENT_CSP,
    ROLE_CHOICES,
    TOKEN_MAX_AGE,
    ConsentSigningForm,
    embedded_font,
)
from .models import (
    AttachmentParentType,
    Beneficiary,
    IndividualPlan,
    SignedPlan,
)
from .plan_schema import intervention_table
from .plan_workflow import barthel_bands, barthel_summary
from .private_attachments import signed_plan_attachments
from .services import save_plan_period
from .validators import validate_private_upload

TOKEN_SALT = "casework.assisted-plan.v1"


class PlanSigningForm(ConsentSigningForm):
    reviewed = forms.BooleanField(
        label=gettext_lazy(
            "The beneficiary or representative has reviewed this plan and requests that "
            "their signature be saved."
        )
    )
    paper_signature = forms.FileField(
        required=False,
        label=gettext_lazy("Signed paper plan (PDF)"),
        validators=[validate_private_upload],
        help_text=gettext_lazy(
            "Alternatively, print this plan, sign it on paper, and upload the signed PDF."
        ),
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,application/pdf"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["signature_data"].required = False
        self.fields["review_token"].label = _("Plan review")

    def clean_signature_data(self):
        if not self.cleaned_data.get("signature_data"):
            return None
        return super().clean_signature_data()

    def clean_paper_signature(self):
        upload = self.cleaned_data.get("paper_signature")
        if upload:
            header = upload.read(5)
            upload.seek(0)
            if not upload.name.lower().endswith(".pdf") or header != b"%PDF-":
                raise ValidationError(_("Upload the signed paper plan as a PDF."))
        return upload

    def clean(self):
        cleaned = super().clean()
        drawing, paper = cleaned.get("signature_data"), cleaned.get("paper_signature")
        if bool(drawing) == bool(paper):
            self.add_error(None, _("Draw a signature or upload a signed paper plan."))
        return cleaned


def authorized_plan(pk, actor, center, *, for_change=False):
    if not actor.is_active or not center.is_active:
        raise Http404
    return get_authorized_object(plans_for_user(actor, center, for_change=for_change), pk)


def authorized_signed_plan(pk, actor, center, *, for_change=False):
    record = get_authorized_object(SignedPlan.objects.filter(center=center), pk)
    authorized_plan(record.plan_id, actor, center, for_change=for_change)
    return record


def plan_review(plan, language, actor, center):
    language = language if language in {"en", "ka"} else "en"
    with translation.override(language):
        return {
            "plan_id": str(plan.pk),
            "language": language,
            "beneficiary": {
                "name": plan.beneficiary.full_name,
                "code": plan.beneficiary.beneficiary_code,
            },
            "enrollment_id": str(plan.enrollment_id),
            "center": str(plan.center),
            "service": str(plan.enrollment.service),
            "kind": str(plan.get_plan_kind_display()),
            "date": plan.plan_start_date.isoformat(),
            "version": plan.version_number,
            "end_date": plan.plan_end_date.isoformat() if plan.plan_end_date else "",
            "review_due_date": plan.review_due_date.isoformat() if plan.review_due_date else "",
            "specialist": str(plan.specialist),
            "review_frequency": str(plan.get_review_frequency_display()),
            "previous_plan_id": str(plan.previous_plan_id or ""),
            "activities": intervention_table(plan.interventions),
            "notes": plan.notes,
            "barthel": barthel_summary(actor, center, plan.beneficiary, plan.plan_start_date),
            "barthel_bands": barthel_bands(),
            "care_notice": str(CARE_NOTICE),
        }


def review_fingerprint(plan, review):
    # Include the revision timestamp to catch edits that were changed and then restored.
    state = {"review": review, "updated_at": plan.updated_at.isoformat()}
    return hashlib.sha256(
        json.dumps(state, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def issue_plan_token(plan, actor, center, review):
    return signing.dumps(
        {
            "plan": str(plan.pk),
            "actor": str(actor.pk),
            "center": str(center.pk),
            "language": review["language"],
            "fingerprint": review_fingerprint(plan, review),
            "submission": str(uuid.uuid4()),
        },
        salt=TOKEN_SALT,
    )


def stale_review():
    return ValidationError(
        _("The plan review has changed or expired. Review it again and provide a fresh signature.")
    )


def plan_document_html(review, *, execution=None, signature=None):
    with translation.override(review["language"]):
        return render_to_string(
            "casework/plan_artifact.html",
            {
                "document": review,
                "execution": execution,
                "signature": base64.b64encode(signature).decode("ascii") if signature else "",
                "font_data": embedded_font(),
                "csp": DOCUMENT_CSP,
            },
        )


def finalize_plan(*, plan, actor, center, language, data, files=None):
    workflow = signed_plan_attachments(actor, center)
    with workflow.atomic_uploads() as uploader:
        Beneficiary.objects.select_for_update().get(pk=plan.beneficiary_id)
        plan = IndividualPlan.objects.select_for_update().get(pk=plan.pk)
        actor = get_user_model().objects.get(pk=actor.pk)
        center = Center.objects.get(pk=center.pk)
        plan = authorized_plan(plan.pk, actor, center, for_change=True)
        form = PlanSigningForm(data, files)
        if not form.is_valid():
            raise ValidationError(form.errors)
        try:
            token = signing.loads(
                form.cleaned_data["review_token"], salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE
            )
            if (token["plan"], token["actor"], token["center"], token["language"]) != (
                str(plan.pk),
                str(actor.pk),
                str(center.pk),
                language,
            ):
                raise stale_review()
            uuid.UUID(token["submission"])
        except (signing.BadSignature, KeyError, ValueError, TypeError) as exc:
            raise stale_review() from exc
        existing = SignedPlan.objects.filter(submission_id=token["submission"]).first()
        if existing:
            return authorized_signed_plan(existing.pk, actor, center)
        if plan.workflow_version != 2 or plan.status != IndividualPlan.Status.DRAFT:
            raise stale_review()
        plan.full_clean()
        review = plan_review(plan, language, actor, center)
        if review_fingerprint(plan, review) != token.get("fingerprint"):
            raise stale_review()
        signed_at = timezone.now()
        values = form.cleaned_data
        signature, paper = values["signature_data"], values.get("paper_signature")
        with translation.override(language):
            role_label = str(dict(ROLE_CHOICES)[values["signer_role"]])
        execution = {
            "signer_name": values["signer_name"],
            "role": values["signer_role"],
            "role_label": role_label,
            "relationship": values["relationship"],
            "timestamp": signed_at.isoformat(),
            "recorder": actor.get_full_name() or actor.username,
            "recorder_id": str(actor.pk),
            "method": "paper" if paper else "drawn",
        }
        if paper:
            paper.seek(0)
            paper_bytes = paper.read()
            execution["paper_sha256"] = hashlib.sha256(paper_bytes).hexdigest()
        else:
            execution["signature_sha256"] = hashlib.sha256(signature).hexdigest()
        record = SignedPlan.objects.create(
            plan=plan,
            center=center,
            recorded_by=actor,
            signed_at=signed_at,
            language=language,
            submission_id=token["submission"],
            snapshot={"review": review, "execution": execution},
        )
        uploader.create(
            parent_type=AttachmentParentType.SIGNED_PLAN,
            parent=record,
            upload=ContentFile(
                paper_bytes if paper else signature,
                name="signed-paper.pdf" if paper else "signature.png",
            ),
        )
        uploader.create(
            parent_type=AttachmentParentType.SIGNED_PLAN,
            parent=record,
            upload=ContentFile(
                plan_document_html(review, execution=execution, signature=signature).encode(
                    "utf-8"
                ),
                name="signed-plan.txt",
            ),
        )
        plan.status = IndividualPlan.Status.ACTIVE
        save_plan_period(plan)
        record_event(
            actor=actor,
            center=center,
            event_type=AuditEvent.EventType.CREATE,
            target_type="SignedPlan",
            target_id=record.pk,
        )
        return record
