from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError

from apps.casework.assessment_engine import (
    comparison_for_assessment,
    complete_assessment,
    correct_assessment,
    replace_draft_responses,
)
from apps.casework.models import (
    Assessment,
    AssessmentInstrument,
    AssessmentResponse,
    AssessmentScoreBand,
    AssessmentTemplateField,
    AssessmentTemplateSection,
    AssessmentTemplateVersion,
    ServiceDefinition,
)
from apps.core.authorization import assessments_for_user, current_assessments_for_user
from apps.core.reporting import report_headers, report_rows

pytestmark = pytest.mark.django_db


def _template(
    *,
    instrument_code="OTHER",
    version="synthetic-engine-1",
    fields=None,
    bands=(),
    score_minimum=None,
    score_maximum=None,
    comparison_group="",
):
    instrument = AssessmentInstrument.objects.get(code=instrument_code)
    template = AssessmentTemplateVersion.objects.create(
        instrument=instrument,
        version=version,
        name=f"Synthetic {instrument_code} {version}",
        score_minimum=score_minimum,
        score_maximum=score_maximum,
        comparison_group=comparison_group,
        publication_notes="Synthetic structural test with no licensed questions.",
    )
    section = AssessmentTemplateSection.objects.create(
        template_version=template,
        code="SYNTHETIC",
        name="Synthetic structure",
    )
    created_fields = []
    for order, field_data in enumerate(
        fields
        or [
            {
                "code": "SCORE",
                "label": "Synthetic score",
                "response_type": AssessmentTemplateField.ResponseType.NUMERIC_SCORE,
                "minimum_value": 0,
                "maximum_value": 100,
                "include_in_total": True,
            }
        ],
        start=1,
    ):
        created_fields.append(
            AssessmentTemplateField.objects.create(
                section=section,
                display_order=order,
                **field_data,
            )
        )
    for order, (code, label, lower, upper) in enumerate(bands, start=1):
        AssessmentScoreBand.objects.create(
            template_version=template,
            code=code,
            label=label,
            lower_bound=lower,
            upper_bound=upper,
            display_order=order,
        )
    template.publish()
    return template, created_fields


def _assessment(
    beneficiary,
    specialist,
    template,
    payloads,
    *,
    assessment_date=date(2026, 1, 10),
    assessment_type=Assessment.AssessmentType.INITIAL,
    previous=None,
):
    enrollment = beneficiary.enrollments.get(service__code="LEGACY-OTHER")
    assessment = Assessment.objects.create(
        enrollment=enrollment,
        beneficiary=beneficiary,
        center=enrollment.placement_on(assessment_date).center,
        specialist=specialist,
        assessment_date=assessment_date,
        assessment_type=assessment_type,
        previous_assessment=previous,
        template_version=template,
        scoring_tool=template.instrument.identifier,
        total_score=Decimal("999"),
    )
    replace_draft_responses(assessment, payloads)
    return complete_assessment(assessment)


@pytest.mark.parametrize(
    ("score", "classification"),
    (
        (0, "Synthetic band 1"),
        (65, "Synthetic band 1"),
        (66, "Synthetic band 2"),
        (75, "Synthetic band 2"),
        (76, "Synthetic band 3"),
        (95, "Synthetic band 3"),
        (96, "Synthetic band 4"),
        (100, "Synthetic band 4"),
    ),
)
def test_barthel_boundaries_are_inclusive_and_total_is_derived(
    beneficiary_a,
    specialist_a,
    score,
    classification,
):
    template, fields = _template(
        instrument_code="BARTHEL",
        score_minimum=0,
        score_maximum=100,
        bands=(
            ("B1", "Synthetic band 1", 0, 65),
            ("B2", "Synthetic band 2", 66, 75),
            ("B3", "Synthetic band 3", 76, 95),
            ("B4", "Synthetic band 4", 96, 100),
        ),
    )
    assessment = _assessment(
        beneficiary_a,
        specialist_a,
        template,
        [{"template_field": fields[0], "numeric_value": score}],
    )

    assert assessment.total_score == Decimal(score).quantize(Decimal("0.01"))
    assert assessment.total_score != Decimal("999")
    assert assessment.derived_classification == classification
    assert assessment.scoring_rule_version == template.version


def test_barthel_publication_rejects_gaps_overlaps_and_impossible_bands():
    instrument = AssessmentInstrument.objects.get(code="BARTHEL")

    def draft(version):
        template = AssessmentTemplateVersion.objects.create(
            instrument=instrument,
            version=version,
            name=version,
            score_minimum=0,
            score_maximum=100,
        )
        section = AssessmentTemplateSection.objects.create(
            template_version=template,
            code="TOTAL",
            name="Total",
        )
        AssessmentTemplateField.objects.create(
            section=section,
            code="SCORE",
            label="Synthetic score",
            response_type=AssessmentTemplateField.ResponseType.NUMERIC_SCORE,
            minimum_value=0,
            maximum_value=100,
            include_in_total=True,
        )
        return template

    gap = draft("gap")
    AssessmentScoreBand.objects.create(
        template_version=gap, code="LOW", label="Low", lower_bound=0, upper_bound=49
    )
    AssessmentScoreBand.objects.create(
        template_version=gap, code="HIGH", label="High", lower_bound=51, upper_bound=100
    )
    with pytest.raises(ValidationError, match="gap"):
        gap.publish()

    overlap = draft("overlap")
    AssessmentScoreBand.objects.create(
        template_version=overlap, code="LOW", label="Low", lower_bound=0, upper_bound=50
    )
    AssessmentScoreBand.objects.create(
        template_version=overlap, code="HIGH", label="High", lower_bound=50, upper_bound=100
    )
    with pytest.raises(ValidationError, match="overlap"):
        overlap.publish()

    impossible = draft("impossible")
    with pytest.raises(ValidationError, match="cannot be below"):
        AssessmentScoreBand.objects.create(
            template_version=impossible,
            code="BAD",
            label="Bad",
            lower_bound=20,
            upper_bound=10,
        )


def test_published_template_structure_and_service_scope_are_immutable(center_a):
    template, fields = _template()
    fields[0].label = "Changed label"
    with pytest.raises(ValidationError, match="immutable"):
        fields[0].save()
    with pytest.raises(ProtectedError):
        fields[0].delete()
    service = ServiceDefinition.objects.get(code="LEGACY-OTHER")
    with pytest.raises(ValidationError, match="immutable"):
        with transaction.atomic():
            template.applicable_services.add(service)
    template.name = "Changed template name"
    with pytest.raises(ValidationError, match="immutable"):
        template.save()


def test_response_types_ranges_states_and_delayed_domain_count(
    beneficiary_a,
    specialist_a,
):
    template, fields = _template(
        fields=[
            {
                "code": "TOTAL",
                "label": "Synthetic numeric",
                "response_type": "numeric",
                "minimum_value": 0,
                "maximum_value": 10,
                "include_in_total": True,
            },
            {
                "code": "DELAYED",
                "label": "Synthetic delayed percentage",
                "response_type": "percentage",
                "value_increment": Decimal("0.01"),
                "allow_not_assessed": True,
                "allow_not_applicable": True,
                "is_delayed_domain": True,
                "delayed_threshold": 50,
                "delayed_operator": "lt",
            },
            {
                "code": "STATE",
                "label": "Synthetic assessment state",
                "response_type": "assessed_state",
            },
            {
                "code": "CHOICE",
                "label": "Synthetic choice",
                "response_type": "choice",
                "allowed_choices": ["synthetic-a", "synthetic-b"],
            },
            {
                "code": "TEXT",
                "label": "Synthetic text",
                "response_type": "text",
            },
            {
                "code": "NA",
                "label": "Synthetic not applicable",
                "response_type": "not_applicable",
            },
        ]
    )
    payloads = [
        {"template_field": fields[0], "numeric_value": 7},
        {"template_field": fields[1], "numeric_value": 40},
        {"template_field": fields[2], "state": "not_assessed"},
        {"template_field": fields[3], "choice_value": "synthetic-a"},
        {"template_field": fields[4], "text_value": "Synthetic note"},
        {"template_field": fields[5], "state": "not_applicable"},
    ]
    assessment = _assessment(beneficiary_a, specialist_a, template, payloads)
    assert assessment.total_score == Decimal("7.00")
    assert assessment.delayed_domain_count == 1

    invalid = AssessmentResponse(
        assessment=Assessment(
            enrollment=assessment.enrollment,
            beneficiary=beneficiary_a,
            center=assessment.center,
            specialist=specialist_a,
            assessment_date=date(2026, 2, 1),
            assessment_type="initial",
            template_version=template,
            scoring_tool="other",
        ),
        template_field=fields[1],
        numeric_value=101,
    )
    with pytest.raises(ValidationError, match="above the allowed maximum"):
        invalid.clean()
    invalid.numeric_value = 40
    invalid.state = AssessmentResponse.State.NOT_ASSESSED
    with pytest.raises(ValidationError, match="cannot contain a value"):
        invalid.clean()
    invalid_choice = AssessmentResponse(
        assessment=invalid.assessment,
        template_field=fields[3],
        choice_value="crafted-invalid-choice",
    )
    with pytest.raises(ValidationError, match="allowed choice"):
        invalid_choice.clean()


def test_chains_are_per_instrument_close_on_final_and_reject_backdating(
    beneficiary_a,
    specialist_a,
):
    other, other_fields = _template(instrument_code="OTHER", version="chain-other")
    icf, icf_fields = _template(instrument_code="ICF", version="chain-icf")
    initial = _assessment(
        beneficiary_a,
        specialist_a,
        other,
        [{"template_field": other_fields[0], "numeric_value": 1}],
        assessment_date=date(2026, 1, 10),
    )
    separate_initial = _assessment(
        beneficiary_a,
        specialist_a,
        icf,
        [{"template_field": icf_fields[0], "numeric_value": 2}],
        assessment_date=date(2026, 1, 5),
    )
    assert separate_initial.chain_id != initial.chain_id
    repeated = _assessment(
        beneficiary_a,
        specialist_a,
        other,
        [{"template_field": other_fields[0], "numeric_value": 3}],
        assessment_date=date(2026, 2, 10),
        assessment_type="repeated",
        previous=initial,
    )
    final = _assessment(
        beneficiary_a,
        specialist_a,
        other,
        [{"template_field": other_fields[0], "numeric_value": 4}],
        assessment_date=date(2026, 3, 10),
        assessment_type="final",
        previous=repeated,
    )
    assert repeated.chain_id == initial.chain_id == final.chain_id
    assert [
        initial.assessment_cycle_number,
        repeated.assessment_cycle_number,
        final.assessment_cycle_number,
    ] == [1, 2, 3]

    with pytest.raises(ValidationError, match="closes"):
        Assessment.objects.create(
            enrollment=initial.enrollment,
            beneficiary=beneficiary_a,
            center=initial.center,
            specialist=specialist_a,
            assessment_date=date(2026, 4, 1),
            assessment_type="repeated",
            previous_assessment=final,
            template_version=other,
            scoring_tool="other",
        )
    with pytest.raises(ValidationError, match="cannot be later"):
        Assessment.objects.create(
            enrollment=initial.enrollment,
            beneficiary=beneficiary_a,
            center=initial.center,
            specialist=specialist_a,
            assessment_date=date(2026, 1, 1),
            assessment_type="repeated",
            previous_assessment=initial,
            template_version=other,
            scoring_tool="other",
        )
    next_initial = Assessment.objects.create(
        enrollment=initial.enrollment,
        beneficiary=beneficiary_a,
        center=initial.center,
        specialist=specialist_a,
        assessment_date=date(2026, 4, 10),
        assessment_type="initial",
        template_version=other,
        scoring_tool="other",
    )
    assert next_initial.chain_number == 2
    assert next_initial.assessment_cycle_number == 1


def test_completed_assessment_requires_authorized_revision_and_cannot_be_deleted(
    beneficiary_a,
    specialist_a,
    specialist_b,
    coordinator_a,
    center_a,
):
    template, fields = _template()
    original = _assessment(
        beneficiary_a,
        specialist_a,
        template,
        [{"template_field": fields[0], "numeric_value": 10}],
    )
    with pytest.raises(ProtectedError):
        original.delete()
    with pytest.raises(PermissionDenied):
        correct_assessment(
            original,
            response_data=[{"template_field": fields[0], "numeric_value": 20}],
            actor=specialist_b.staff_profile.user,
            reason="Synthetic correction",
        )

    corrected = correct_assessment(
        original,
        response_data=[{"template_field": fields[0], "numeric_value": 20}],
        actor=coordinator_a,
        reason="Synthetic correction",
    )
    original.refresh_from_db()
    assert original.status == Assessment.Status.SUPERSEDED
    assert original.total_score == Decimal("10.00")
    assert corrected.status == Assessment.Status.COMPLETED
    assert corrected.revision_of == original
    assert corrected.revision_number == 2
    assert corrected.total_score == Decimal("20.00")
    assert list(current_assessments_for_user(coordinator_a, center_a)) == [corrected]
    response = corrected.responses.get()
    response.numeric_value = 30
    with pytest.raises(ValidationError, match="immutable"):
        response.save()


def test_comparisons_require_approved_version_compatibility(beneficiary_a, specialist_a):
    template, fields = _template(comparison_group="SYNTHETIC-COMPARE")
    initial = _assessment(
        beneficiary_a,
        specialist_a,
        template,
        [{"template_field": fields[0], "numeric_value": 10}],
    )
    repeated = _assessment(
        beneficiary_a,
        specialist_a,
        template,
        [{"template_field": fields[0], "numeric_value": 15}],
        assessment_date=date(2026, 2, 10),
        assessment_type="repeated",
        previous=initial,
    )
    comparison = comparison_for_assessment(repeated)
    assert comparison["comparable"] is True
    assert comparison["total_change"] == Decimal("5.00")

    incompatible, incompatible_fields = _template(
        version="synthetic-engine-2",
        comparison_group="",
    )
    incompatible_repeated = Assessment(
        enrollment=initial.enrollment,
        beneficiary=beneficiary_a,
        center=initial.center,
        specialist=specialist_a,
        assessment_date=date(2026, 3, 10),
        assessment_type="repeated",
        previous_assessment=repeated,
        template_version=incompatible,
        scoring_tool="other",
    )
    incompatible_repeated.save()
    replace_draft_responses(
        incompatible_repeated,
        [{"template_field": incompatible_fields[0], "numeric_value": 20}],
    )
    incompatible_repeated = complete_assessment(incompatible_repeated)
    comparison = comparison_for_assessment(incompatible_repeated)
    assert comparison["comparable"] is False


def test_authorized_selector_and_report_use_derived_results(
    beneficiary_a,
    specialist_a,
    specialist_b,
    center_a,
):
    template, fields = _template()
    assessment = _assessment(
        beneficiary_a,
        specialist_a,
        template,
        [{"template_field": fields[0], "numeric_value": 12}],
    )
    assert (
        assessments_for_user(specialist_a.staff_profile.user, center_a)
        .filter(pk=assessment.pk)
        .exists()
    )
    assert (
        not assessments_for_user(specialist_b.staff_profile.user, center_a)
        .filter(pk=assessment.pk)
        .exists()
    )

    headers = report_headers("assessments")
    rows = list(report_rows("assessments", Assessment.objects.filter(pk=assessment.pk)))
    assert "Template version" in headers
    assert "Delayed domains" in headers
    assert rows[0][headers.index("Total score")] == "12.00"
    assert rows[0][headers.index("Template version")] == template.version
