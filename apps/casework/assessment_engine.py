from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import (
    Assessment,
    AssessmentResponse,
    AssessmentResponsibleSpecialist,
    AssessmentTemplateField,
    AssessmentTemplateVersion,
)


@dataclass(frozen=True)
class CalculatedAssessmentResult:
    total_score: Decimal
    classification: str
    delayed_domain_count: int
    trace: dict[str, Any]


def _response_is_delayed(response: AssessmentResponse) -> bool:
    field = response.template_field
    if (
        response.state != AssessmentResponse.State.ASSESSED
        or response.numeric_value is None
        or not field.is_delayed_domain
        or field.delayed_threshold is None
    ):
        return False
    value = response.numeric_value
    threshold = field.delayed_threshold
    return {
        AssessmentTemplateField.DelayedOperator.LESS_THAN: value < threshold,
        AssessmentTemplateField.DelayedOperator.LESS_THAN_OR_EQUAL: value <= threshold,
        AssessmentTemplateField.DelayedOperator.GREATER_THAN: value > threshold,
        AssessmentTemplateField.DelayedOperator.GREATER_THAN_OR_EQUAL: value >= threshold,
    }[field.delayed_operator]


def calculate_assessment(
    assessment: Assessment,
    *,
    responses: list[AssessmentResponse] | None = None,
) -> CalculatedAssessmentResult:
    template = assessment.template_version
    template_fields = list(
        template.fields.select_related("section").order_by(
            "section__display_order", "display_order", "created_at"
        )
    )
    if responses is None:
        responses = list(
            assessment.responses.select_related("template_field__section__template_version").all()
        )
    response_by_field = {response.template_field_id: response for response in responses}
    if len(response_by_field) != len(responses):
        raise ValidationError(_("Each template field may have only one response."))
    allowed_field_ids = {field.pk for field in template_fields}
    unknown = set(response_by_field) - allowed_field_ids
    if unknown:
        raise ValidationError(_("Assessment contains responses from another template."))

    errors = {}
    numeric_values: list[Decimal] = []
    delayed_count = 0
    response_trace = []
    for field in template_fields:
        response = response_by_field.get(field.pk)
        if response is None:
            if field.is_required:
                errors[field.code] = _("A response is required.")
            continue
        response.full_clean()
        if (
            field.is_required
            and response.state == AssessmentResponse.State.NOT_ASSESSED
            and not field.allow_not_assessed
            and field.response_type != AssessmentTemplateField.ResponseType.ASSESSED_NOT_ASSESSED
        ):
            errors[field.code] = _("This required field must be assessed.")
        if field.include_in_total and response.state == AssessmentResponse.State.ASSESSED:
            if response.numeric_value is None:
                errors[field.code] = _("A scored response requires a numeric value.")
            else:
                numeric_values.append(response.numeric_value)
        delayed = _response_is_delayed(response)
        delayed_count += int(delayed)
        response_trace.append(
            {
                "field": field.code,
                "state": response.state,
                "numeric_value": (
                    str(response.numeric_value) if response.numeric_value is not None else None
                ),
                "choice_value": response.choice_value or None,
                "delayed": delayed,
            }
        )
    if errors:
        raise ValidationError(errors)

    if template.scoring_method == AssessmentTemplateVersion.ScoringMethod.SUM:
        total = sum(numeric_values, Decimal("0"))
    elif template.scoring_method == AssessmentTemplateVersion.ScoringMethod.AVERAGE:
        total = (
            sum(numeric_values, Decimal("0")) / Decimal(len(numeric_values))
            if numeric_values
            else Decimal("0")
        )
    else:
        total = Decimal("0")
    total = total.quantize(Decimal("0.01"))
    if template.score_minimum is not None and total < template.score_minimum:
        raise ValidationError({"total_score": _("Calculated total is below the template minimum.")})
    if template.score_maximum is not None and total > template.score_maximum:
        raise ValidationError({"total_score": _("Calculated total is above the template maximum.")})

    matching_bands = [
        band for band in template.score_bands.all() if band.lower_bound <= total <= band.upper_bound
    ]
    if len(matching_bands) > 1:
        raise ValidationError(_("Calculated total matches overlapping classification bands."))
    if (
        template.instrument.identifier == template.instrument.Identifier.BARTHEL
        and len(matching_bands) != 1
    ):
        raise ValidationError(_("Calculated Barthel score does not match a classification band."))
    classification = matching_bands[0].label if matching_bands else ""
    trace = {
        "instrument_code": template.instrument.code,
        "template_version": template.version,
        "scoring_method": template.scoring_method,
        "included_values": [str(value) for value in numeric_values],
        "total_score": str(total),
        "classification": classification or None,
        "delayed_domain_count": delayed_count,
        "responses": response_trace,
    }
    return CalculatedAssessmentResult(total, classification, delayed_count, trace)


@transaction.atomic
def replace_draft_responses(
    assessment: Assessment,
    response_data: list[dict[str, Any]],
) -> list[AssessmentResponse]:
    assessment = Assessment.objects.select_for_update().get(pk=assessment.pk)
    if assessment.status != Assessment.Status.DRAFT:
        raise ValidationError(_("Completed assessment responses are immutable."))
    for response in list(assessment.responses.all()):
        response.delete()
    responses = []
    for payload in response_data:
        template_field = payload.get("template_field")
        if not isinstance(template_field, AssessmentTemplateField):
            template_field = AssessmentTemplateField.objects.get(pk=template_field)
        response = AssessmentResponse(
            assessment=assessment,
            template_field=template_field,
            state=payload.get("state", AssessmentResponse.State.ASSESSED),
            numeric_value=payload.get("numeric_value"),
            text_value=payload.get("text_value", ""),
            choice_value=payload.get("choice_value", ""),
            notes=payload.get("notes", ""),
        )
        response.save()
        responses.append(response)
    return responses


@transaction.atomic
def complete_assessment(assessment: Assessment) -> Assessment:
    locked = (
        Assessment.objects.select_for_update()
        .select_related("template_version__instrument")
        .get(pk=assessment.pk)
    )
    if locked.status != Assessment.Status.DRAFT:
        raise ValidationError(_("Only a draft assessment can be completed."))
    if (
        not locked.revision_of_id
        and not locked.template_version.is_legacy
        and not locked.template_version.is_available_for(
            locked.enrollment.service_id, locked.assessment_date
        )
    ):
        raise ValidationError(
            _("The template is not published and effective for this service and date.")
        )
    if not locked.responsible_specialists.filter(pk=locked.specialist_id).exists():
        AssessmentResponsibleSpecialist.objects.create(
            assessment=locked,
            specialist=locked.specialist,
        )
    result = calculate_assessment(locked)
    now = timezone.now()
    Assessment.objects.filter(pk=locked.pk).update(
        total_score=result.total_score,
        derived_classification=result.classification,
        delayed_domain_count=result.delayed_domain_count,
        scoring_rule_version=locked.template_version.version,
        calculation_trace=result.trace,
        calculated_at=now,
        status=Assessment.Status.COMPLETED,
        updated_at=now,
    )
    locked.refresh_from_db()
    return locked


@transaction.atomic
def correct_assessment(
    assessment: Assessment,
    *,
    response_data: list[dict[str, Any]],
    actor,
    reason: str,
) -> Assessment:
    reason = reason.strip()
    if not reason:
        raise ValidationError({"reason": _("A correction reason is required.")})
    current = Assessment.objects.select_for_update().get(pk=assessment.pk)
    from apps.core.authorization import assessments_for_user

    if (
        not assessments_for_user(actor, current.center, for_change=True)
        .filter(pk=current.pk)
        .exists()
    ):
        raise PermissionDenied
    if current.status != Assessment.Status.COMPLETED:
        raise ValidationError(_("Only the current completed assessment can be corrected."))
    original = current.revision_of or current
    latest_revision = (
        Assessment.objects.filter(revision_of=original).aggregate(value=Max("revision_number"))[
            "value"
        ]
        or original.revision_number
    )
    corrected = Assessment(
        enrollment=current.enrollment,
        beneficiary=current.beneficiary,
        center=current.center,
        specialist=current.specialist,
        assessment_date=current.assessment_date,
        assessment_type=current.assessment_type,
        previous_assessment=current.previous_assessment,
        assessment_cycle_number=current.assessment_cycle_number,
        chain_id=current.chain_id,
        chain_number=current.chain_number,
        template_version=current.template_version,
        scoring_tool=current.scoring_tool,
        service_schedule_count=current.service_schedule_count,
        progress_summary=current.progress_summary,
        recommendations=current.recommendations,
        next_review_date=current.next_review_date,
        notes=current.notes,
        revision_of=original,
        revision_number=latest_revision + 1,
        correction_reason=reason,
        corrected_by=actor,
    )
    corrected.save()
    for specialist in current.responsible_specialists.all():
        AssessmentResponsibleSpecialist.objects.create(
            assessment=corrected,
            specialist=specialist,
        )
    replace_draft_responses(corrected, response_data)
    corrected = complete_assessment(corrected)
    Assessment.objects.filter(pk=current.pk).update(
        status=Assessment.Status.SUPERSEDED,
        updated_at=timezone.now(),
    )
    return corrected


def templates_are_comparable(
    first: AssessmentTemplateVersion,
    second: AssessmentTemplateVersion,
) -> bool:
    if first.instrument.lineage_code != second.instrument.lineage_code:
        return False
    if first.pk == second.pk:
        return True
    return bool(first.comparison_group and first.comparison_group == second.comparison_group)


def comparison_for_assessment(assessment: Assessment) -> dict[str, Any] | None:
    previous = assessment.previous_assessment
    if previous is None:
        return None
    corrected_previous = (
        previous.corrections.filter(status=Assessment.Status.COMPLETED)
        .order_by("-revision_number")
        .first()
    )
    previous = corrected_previous or previous
    if not templates_are_comparable(assessment.template_version, previous.template_version):
        return {
            "comparable": False,
            "previous": previous,
            "reason": _("Template versions do not have an approved comparison rule."),
            "responses": [],
        }
    current_responses = {
        response.template_field.code: response
        for response in assessment.responses.select_related("template_field").all()
    }
    previous_responses = {
        response.template_field.code: response
        for response in previous.responses.select_related("template_field").all()
    }
    changes = []
    for code in sorted(set(current_responses) & set(previous_responses)):
        current_response = current_responses[code]
        previous_response = previous_responses[code]
        if (
            current_response.state == AssessmentResponse.State.ASSESSED
            and previous_response.state == AssessmentResponse.State.ASSESSED
            and current_response.numeric_value is not None
            and previous_response.numeric_value is not None
        ):
            changes.append(
                {
                    "code": code,
                    "label": current_response.template_field.label,
                    "previous": previous_response.numeric_value,
                    "current": current_response.numeric_value,
                    "change": current_response.numeric_value - previous_response.numeric_value,
                }
            )
    return {
        "comparable": True,
        "previous": previous,
        "total_change": assessment.total_score - previous.total_score,
        "delayed_domain_change": (assessment.delayed_domain_count - previous.delayed_domain_count),
        "responses": changes,
    }
