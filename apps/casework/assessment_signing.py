"""Review-bound, append-only assessment signing using the consent signature controls."""

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
from apps.core.authorization import assessments_for_user, get_authorized_object

from .assessment_engine import calculate_assessment, complete_assessment
from .consent_signing import (
    DOCUMENT_CSP,
    ROLE_CHOICES,
    TOKEN_MAX_AGE,
    ConsentSigningForm,
    embedded_font,
)
from .models import (
    Assessment,
    AttachmentParentType,
    Beneficiary,
    CareNeedLevel,
    FunctionalDependencyLevel,
    SignedAssessment,
)
from .private_attachments import signed_assessment_attachments
from .validators import validate_private_upload

TOKEN_SALT = "casework.assisted-assessment.v1"
CARE_NOTICE = gettext_lazy(
    "Barthel measures basic activities of daily living. The score alone must not determine "
    "home-care visit frequency or service intensity. Even a score of 100 may coexist with "
    "needs for medication support, meal preparation, shopping, housework, or social support. "
    "Use the additional care needs assessment when planning services."
)


class AssessmentSigningForm(ConsentSigningForm):
    reviewed = forms.BooleanField(
        label=gettext_lazy(
            "The beneficiary or representative has reviewed this assessment and requests that "
            "their signature be saved."
        )
    )
    paper_signature = forms.FileField(
        required=False,
        label=gettext_lazy("Signed paper assessment (PDF)"),
        validators=[validate_private_upload],
        help_text=gettext_lazy(
            "Alternatively, print this assessment, sign it on paper, and upload the signed PDF."
        ),
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,application/pdf"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["signature_data"].required = False
        self.fields["review_token"].label = _("Assessment review")

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
                raise ValidationError(_("Upload the signed paper assessment as a PDF."))
        return upload

    def clean(self):
        cleaned = super().clean()
        drawing, paper = cleaned.get("signature_data"), cleaned.get("paper_signature")
        if bool(drawing) == bool(paper):
            self.add_error(None, _("Draw a signature or upload a signed paper assessment."))
        return cleaned


def authorized_assessment(pk, actor, center, *, for_change=False):
    if not actor.is_active or not center.is_active:
        raise Http404
    return get_authorized_object(assessments_for_user(actor, center, for_change=for_change), pk)


def authorized_signed_assessment(pk, actor, center, *, for_change=False):
    record = get_authorized_object(SignedAssessment.objects.filter(center=center), pk)
    authorized_assessment(record.assessment_id, actor, center, for_change=for_change)
    return record


def assessment_review(assessment, language):
    language = language if language in {"en", "ka"} else "en"
    result = calculate_assessment(assessment)
    person = assessment.beneficiary
    age = person.age_on(assessment.assessment_date)
    with translation.override(language):
        responses = [
            {
                "field_id": str(response.template_field_id),
                "field": response.template_field.code,
                "label": _(response.template_field.label),
                "state": response.state,
                "state_label": str(response.get_state_display()),
                "score": str(response.numeric_value) if response.numeric_value is not None else "",
                "answer": response.choice_display or response.text_value,
                "notes": response.notes,
            }
            for response in assessment.responses.select_related("template_field__section").order_by(
                "template_field__section__display_order", "template_field__display_order"
            )
        ]
        specialists = {str(item.pk): str(item) for item in assessment.responsible_specialists.all()}
        specialists[str(assessment.specialist_id)] = str(assessment.specialist)
        return {
            "assessment_id": str(assessment.pk),
            "language": language,
            "beneficiary": {"name": person.full_name, "code": person.beneficiary_code},
            "age": (
                _("%(years)s years, %(months)s months") % {"years": age.years, "months": age.months}
                if age
                else _("Age unknown")
            ),
            "date": assessment.assessment_date.isoformat(),
            "type": str(assessment.get_assessment_type_display()),
            "enrollment_id": str(assessment.enrollment_id),
            "service": str(assessment.enrollment.service),
            "center": str(assessment.center),
            "template_id": str(assessment.template_version_id),
            "template": _(assessment.template_version.name),
            "template_version": assessment.template_version.version,
            "barthel": assessment.scoring_tool == Assessment.ScoringTool.BARTHEL,
            "result": {
                "score": str(result.total_score),
                "classification": result.classification,
                "dependency": result.functional_dependency_level,
                "dependency_label": str(
                    dict(FunctionalDependencyLevel.choices).get(
                        result.functional_dependency_level, ""
                    )
                ),
                "care_need": result.care_need_level,
                "care_need_label": str(dict(CareNeedLevel.choices).get(result.care_need_level, "")),
                "trace": result.trace,
            },
            "responses": responses,
            "responsible_specialists": specialists,
            "progress_summary": assessment.progress_summary,
            "recommendations": assessment.recommendations,
            "notes": assessment.notes,
            "additional_care_needs": assessment.additional_care_needs,
            "service_schedule_count": assessment.service_schedule_count,
            "next_review_date": assessment.next_review_date.isoformat()
            if assessment.next_review_date
            else "",
            "care_notice": str(CARE_NOTICE),
        }


def review_fingerprint(assessment, review):
    # Include the revision timestamp to catch edits that were changed and then restored.
    state = {"review": review, "updated_at": assessment.updated_at.isoformat()}
    return hashlib.sha256(
        json.dumps(state, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def issue_assessment_token(assessment, actor, center, review):
    return signing.dumps(
        {
            "assessment": str(assessment.pk),
            "actor": str(actor.pk),
            "center": str(center.pk),
            "language": review["language"],
            "fingerprint": review_fingerprint(assessment, review),
            "submission": str(uuid.uuid4()),
        },
        salt=TOKEN_SALT,
    )


def stale_review():
    return ValidationError(
        _(
            "The assessment review has changed or expired. Review it again and provide "
            "a fresh signature."
        )
    )


def assessment_document_html(review, *, execution=None, signature=None):
    with translation.override(review["language"]):
        return render_to_string(
            "casework/assessment_artifact.html",
            {
                "document": review,
                "execution": execution,
                "signature": base64.b64encode(signature).decode("ascii") if signature else "",
                "font_data": embedded_font(),
                "csp": DOCUMENT_CSP,
            },
        )


def finalize_assessment(*, assessment, actor, center, language, data, files=None):
    workflow = signed_assessment_attachments(actor, center)
    with workflow.atomic_uploads() as uploader:
        Beneficiary.objects.select_for_update().get(pk=assessment.beneficiary_id)
        assessment = Assessment.objects.select_for_update().get(pk=assessment.pk)
        actor = get_user_model().objects.get(pk=actor.pk)
        center = Center.objects.get(pk=center.pk)
        assessment = authorized_assessment(assessment.pk, actor, center, for_change=True)
        form = AssessmentSigningForm(data, files)
        if not form.is_valid():
            raise ValidationError(form.errors)
        try:
            token = signing.loads(
                form.cleaned_data["review_token"], salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE
            )
            if (token["assessment"], token["actor"], token["center"], token["language"]) != (
                str(assessment.pk),
                str(actor.pk),
                str(center.pk),
                language,
            ):
                raise stale_review()
            uuid.UUID(token["submission"])
        except (signing.BadSignature, KeyError, ValueError, TypeError) as exc:
            raise stale_review() from exc
        existing = SignedAssessment.objects.filter(submission_id=token["submission"]).first()
        if existing:
            return authorized_signed_assessment(existing.pk, actor, center)
        if assessment.status != Assessment.Status.DRAFT:
            raise stale_review()
        review = assessment_review(assessment, language)
        if review_fingerprint(assessment, review) != token["fingerprint"]:
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
        record = SignedAssessment.objects.create(
            assessment=assessment,
            center=center,
            recorded_by=actor,
            signed_at=signed_at,
            language=language,
            submission_id=token["submission"],
            snapshot={"review": review, "execution": execution},
        )
        uploader.create(
            parent_type=AttachmentParentType.SIGNED_ASSESSMENT,
            parent=record,
            upload=ContentFile(
                paper_bytes if paper else signature,
                name="signed-paper.pdf" if paper else "signature.png",
            ),
        )
        uploader.create(
            parent_type=AttachmentParentType.SIGNED_ASSESSMENT,
            parent=record,
            upload=ContentFile(
                assessment_document_html(review, execution=execution, signature=signature).encode(
                    "utf-8"
                ),
                name="signed-assessment.txt",
            ),
        )
        complete_assessment(assessment)
        record_event(
            actor=actor,
            center=center,
            event_type=AuditEvent.EventType.CREATE,
            target_type="SignedAssessment",
            target_id=record.pk,
        )
        return record
