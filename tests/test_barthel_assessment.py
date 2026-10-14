from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, transaction
from django.http import Http404
from django.urls import reverse
from django.utils import translation

from apps.casework.assessment_engine import (
    calculate_assessment,
    complete_assessment,
    correct_assessment,
    replace_draft_responses,
)
from apps.casework.assessment_signing import (
    assessment_review,
    finalize_assessment,
    issue_assessment_token,
)
from apps.casework.forms import AssessmentForm
from apps.casework.models import (
    Assessment,
    AssessmentTemplateVersion,
    PrivateAttachment,
    SignedAssessment,
)
from apps.casework.private_attachments import case_attachments

from .factories import set_active_center
from .test_consent_signing import png_value

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def private_root(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    return settings.PRIVATE_MEDIA_ROOT


def template():
    return AssessmentTemplateVersion.objects.get(
        instrument__code="BARTHEL", version="ssk-20261014-1"
    )


def draft(person, specialist, score=55):
    enrollment = person.enrollments.get(service__code="LEGACY-OTHER")
    assessment = Assessment.objects.create(
        enrollment=enrollment,
        beneficiary=person,
        center=person.center,
        specialist=specialist,
        assessment_date=date(2026, 1, 15),
        assessment_type="initial",
        template_version=template(),
        scoring_tool="barthel",
        signature_required=True,
        additional_care_needs="Synthetic medication and shopping support needs.",
    )
    remaining = score
    payloads = []
    for field in template().fields.order_by("display_order"):
        allowed = sorted((choice["score"] for choice in field.allowed_choices), reverse=True)
        value = next(value for value in allowed if value <= remaining)
        remaining -= value
        payloads.append({"template_field": field, "choice_value": str(value)})
    assert remaining == 0
    replace_draft_responses(assessment, payloads)
    return assessment


def values(assessment, actor, language="en"):
    return {
        "review_token": issue_assessment_token(
            assessment, actor, assessment.center, assessment_review(assessment, language)
        ),
        "signer_name": "Synthetic representative <script>alert(1)</script>",
        "signer_role": "representative",
        "relationship": "Synthetic guardian",
        "signature_data": png_value(),
        "reviewed": "on",
    }


@pytest.mark.parametrize("score", range(0, 101, 5))
def test_every_reachable_score_uses_confirmed_bands(beneficiary_a, specialist_a, score):
    assessment = draft(beneficiary_a, specialist_a, score)
    result = calculate_assessment(assessment)
    dependency, need = (
        ("total", "very_high")
        if score <= 20
        else ("severe", "high")
        if score <= 60
        else ("moderate", "moderate")
        if score <= 90
        else ("slight", "low")
        if score < 100
        else ("independent", "minimal")
    )
    assert result.total_score == Decimal(score)
    assert result.functional_dependency_level == dependency
    assert result.care_need_level == need
    assert len(result.trace["responses"]) == 10
    with pytest.raises(ValidationError, match="sign"):
        complete_assessment(assessment)


def test_question_structure_choices_and_no_version_picker(
    client, coordinator_a, center_a, beneficiary_a
):
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    response = client.get(reverse("assessment_create"))
    assert response.status_code == 200
    assert len(response.context["formset"].forms) == 10
    html = response.content.decode()
    assert 'type="radio"' in html
    assert "Template version" not in html
    assert "ssk-20261014-1" not in html
    assert "Barthel scale" in html
    form = response.context["form"]
    enrollment = beneficiary_a.enrollments.get(service__code="LEGACY-OTHER")
    label = form.fields["enrollment"].label_from_instance(enrollment)
    assert label.startswith(beneficiary_a.full_name)
    assert beneficiary_a.beneficiary_code in label
    assert "years" in label
    assert form.fields["template_version"].widget.is_hidden


def test_scores_and_choice_values_cannot_be_forged(beneficiary_a, specialist_a):
    assessment = draft(beneficiary_a, specialist_a)
    response = assessment.responses.first()
    response.numeric_value = 999
    with pytest.raises(ValidationError, match="score must match"):
        response.save()
    response.numeric_value = None
    response.choice_value = "forged"
    with pytest.raises(ValidationError, match="allowed choice"):
        response.save()
    response = assessment.responses.last()
    response.delete()
    with pytest.raises(ValidationError, match="required"):
        calculate_assessment(assessment)


@pytest.mark.parametrize("language", ["en", "ka"])
def test_signed_result_exact_snapshot_and_retry(
    client, coordinator_a, center_a, beneficiary_a, specialist_a, language
):
    assessment = draft(beneficiary_a, specialist_a)
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    client.cookies["django_language"] = language
    with translation.override(language):
        response = client.get(reverse("assessment_sign", args=[assessment.pk]))
        data = values(assessment, coordinator_a, language)
        data["review_token"] = response.context["form"].initial["review_token"]
        signed = client.post(reverse("assessment_sign", args=[assessment.pk]), data)
        assert signed.status_code == 302, signed.content.decode()[:2000]
        retry = client.post(reverse("assessment_sign", args=[assessment.pk]), data)
    assert retry.status_code == 302
    assessment.refresh_from_db()
    assert assessment.status == "completed"
    assert assessment.total_score == 55
    assert assessment.functional_dependency_level == "severe"
    assert assessment.care_need_level == "high"
    assert SignedAssessment.objects.count() == 1
    record = assessment.signed_document
    assert record.snapshot["review"]["result"]["score"] == "55.00"
    assert record.snapshot["execution"]["role"] == "representative"
    assert PrivateAttachment.objects.filter(parent_id=record.pk).count() == 2
    document = client.get(reverse("assessment_document", args=[record.pk]))
    html = b"".join(document.streaming_content).decode()
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "Synthetic medication" in html
    assert "data:image/png;base64," in html
    assert "private" in document["Cache-Control"] and "no-store" in document["Cache-Control"]
    assert "frame-ancestors 'none'" in document["Content-Security-Policy"]
    download = client.get(reverse("assessment_download", args=[record.pk]))
    assert download["Content-Disposition"] == 'attachment; filename="signed-assessment.html"'
    assert b"".join(download.streaming_content).decode() == html
    if language == "ka":
        assert "კვება" in html
        assert "მძიმე დამოკიდებულება" in html
        assert "მაღალი" in html
    attachment = PrivateAttachment.objects.get(
        parent_id=record.pk, original_filename="signature.png"
    )
    with pytest.raises(Http404):
        case_attachments(coordinator_a, center_a).download(attachment.pk)


@pytest.mark.parametrize(
    "mutation", ["answer", "notes", "actor", "center", "token", "confirmation", "blank_signature"]
)
def test_stale_or_invalid_review_cannot_complete(
    beneficiary_a, specialist_a, coordinator_a, center_b, private_root, mutation
):
    assessment = draft(beneficiary_a, specialist_a)
    data = values(assessment, coordinator_a)
    if mutation == "answer":
        response = assessment.responses.first()
        response.choice_value, response.numeric_value = "0", None
        response.save()
    elif mutation == "notes":
        assessment.notes = "Changed after review"
        assessment.save()
    elif mutation == "actor":
        coordinator_a.is_active = False
        coordinator_a.save(update_fields=["is_active"])
    elif mutation == "center":
        data["review_token"] = issue_assessment_token(
            assessment, coordinator_a, center_b, assessment_review(assessment, "en")
        )
    elif mutation == "token":
        data["review_token"] = "forged"
    elif mutation == "confirmation":
        data["reviewed"] = ""
    elif mutation == "blank_signature":
        data["signature_data"] = png_value(blank=True)
    with pytest.raises((ValidationError, Http404)):
        finalize_assessment(
            assessment=assessment,
            actor=coordinator_a,
            center=assessment.center,
            language="en",
            data=data,
        )
    assessment.refresh_from_db()
    assert assessment.status == "draft"
    assert not SignedAssessment.objects.exists()
    assert not PrivateAttachment.objects.exists()
    assert not list(private_root.rglob("*.*"))


def test_cross_center_and_anonymous_signing(
    client, coordinator_a, center_a, beneficiary_b, specialist_b
):
    assessment = draft(beneficiary_b, specialist_b)
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    for name in ("assessment_sign", "assessment_print"):
        assert client.get(reverse(name, args=[assessment.pk])).status_code == 404
    client.logout()
    assert client.get(reverse("assessment_sign", args=[assessment.pk])).status_code == 302


def test_storage_failure_rolls_back_record_and_files(
    beneficiary_a, specialist_a, coordinator_a, private_root
):
    assessment = draft(beneficiary_a, specialist_a)
    data = values(assessment, coordinator_a)
    with (
        patch(
            "apps.casework.assessment_signing.complete_assessment",
            side_effect=OSError("Synthetic failure"),
        ),
        pytest.raises(OSError),
    ):
        finalize_assessment(
            assessment=assessment,
            actor=coordinator_a,
            center=assessment.center,
            language="en",
            data=data,
        )
    assert not SignedAssessment.objects.exists()
    assert not PrivateAttachment.objects.exists()
    assert not list(private_root.rglob("*.*"))


def test_paper_signature_and_immutable_evidence(beneficiary_a, specialist_a, coordinator_a):
    assessment = draft(beneficiary_a, specialist_a)
    data = values(assessment, coordinator_a)
    data["signature_data"] = ""
    paper = SimpleUploadedFile(
        "synthetic-signed.pdf",
        b"%PDF-1.4\nSynthetic paper fixture\n%%EOF",
        content_type="application/pdf",
    )
    record = finalize_assessment(
        assessment=assessment,
        actor=coordinator_a,
        center=assessment.center,
        language="en",
        data=data,
        files={"paper_signature": paper},
    )
    assert record.snapshot["execution"]["method"] == "paper"
    assert "paper_sha256" in record.snapshot["execution"]
    with pytest.raises(ValidationError, match="cannot be changed"):
        record.save()
    with pytest.raises(TypeError), transaction.atomic():
        SignedAssessment.objects.filter(pk=record.pk).delete()
    with pytest.raises(DatabaseError), transaction.atomic():
        SignedAssessment.objects.filter(pk=record.pk).update(language="ka")
    attachment = PrivateAttachment.objects.get(
        parent_id=record.pk, original_filename="signed-paper.pdf"
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        PrivateAttachment.objects.filter(pk=attachment.pk).update(original_filename="forged.pdf")
    assessment.refresh_from_db()
    assessment.notes = "Changed after signing"
    with pytest.raises(ValidationError, match="fresh signed correction"):
        assessment.save()


def test_signed_correction_requires_new_signature(beneficiary_a, specialist_a, coordinator_a):
    assessment = draft(beneficiary_a, specialist_a)
    record = finalize_assessment(
        assessment=assessment,
        actor=coordinator_a,
        center=assessment.center,
        language="en",
        data=values(assessment, coordinator_a),
    )
    payloads = [
        {"template_field": response.template_field, "choice_value": "0"}
        for response in assessment.responses.all()
    ]
    corrected = correct_assessment(
        assessment, response_data=payloads, actor=coordinator_a, reason="Synthetic correction"
    )
    assert corrected.status == "draft"
    with pytest.raises(ValidationError, match="already awaiting"):
        correct_assessment(
            assessment,
            response_data=payloads,
            actor=coordinator_a,
            reason="Another pending correction",
        )
    assessment.refresh_from_db()
    assert assessment.status == "completed"
    finalize_assessment(
        assessment=corrected,
        actor=coordinator_a,
        center=assessment.center,
        language="en",
        data=values(corrected, coordinator_a),
    )
    assessment.refresh_from_db()
    assert assessment.status == "superseded"
    assert (
        SignedAssessment.objects.get(pk=record.pk).snapshot["review"]["result"]["score"] == "55.00"
    )
    assert SignedAssessment.objects.count() == 2


def test_expired_review_is_rejected(beneficiary_a, specialist_a, coordinator_a):
    from django.core.signing import SignatureExpired

    assessment = draft(beneficiary_a, specialist_a)
    data = values(assessment, coordinator_a)
    with (
        patch("apps.casework.assessment_signing.signing.loads", side_effect=SignatureExpired),
        pytest.raises(ValidationError, match="expired"),
    ):
        finalize_assessment(
            assessment=assessment,
            actor=coordinator_a,
            center=assessment.center,
            language="en",
            data=data,
        )
    assert not SignedAssessment.objects.exists()


def test_signed_documents_and_files_deny_cross_center(
    client, manager, center_a, beneficiary_b, specialist_b
):
    assessment = draft(beneficiary_b, specialist_b)
    record = finalize_assessment(
        assessment=assessment,
        actor=manager,
        center=assessment.center,
        language="en",
        data=values(assessment, manager),
    )
    client.force_login(manager)
    set_active_center(client, center_a)
    for name in ("assessment_document", "assessment_download", "assessment_signature_download"):
        assert client.get(reverse(name, args=[record.pk])).status_code == 404


def test_age_uses_assessment_date_and_unknown_age_is_explicit(
    beneficiary_a, specialist_a, coordinator_a, center_a
):
    beneficiary_a.birth_date = date(2020, 2, 20)
    beneficiary_a.save()
    enrollment = beneficiary_a.enrollments.get(service__code="LEGACY-OTHER")
    form = AssessmentForm(
        user=coordinator_a, center=center_a, initial={"assessment_date": date(2026, 1, 15)}
    )
    assert "5 years, 10 months" in form.fields["enrollment"].label_from_instance(enrollment)
    beneficiary_a.birth_date = None
    beneficiary_a.save()
    assert "Age unknown" in form.fields["enrollment"].label_from_instance(enrollment)


@pytest.mark.skipif(
    connection.vendor != "postgresql", reason="Raw delete guards require PostgreSQL."
)
def test_raw_database_deletion_is_blocked(beneficiary_a, specialist_a, coordinator_a):
    assessment = draft(beneficiary_a, specialist_a)
    record = finalize_assessment(
        assessment=assessment,
        actor=coordinator_a,
        center=assessment.center,
        language="en",
        data=values(assessment, coordinator_a),
    )
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("DELETE FROM casework_signedassessment WHERE id=%s", [record.pk])
