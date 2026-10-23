from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, transaction
from django.http import Http404
from django.urls import reverse
from django.utils import translation

from apps.casework.assessment_signing import finalize_assessment
from apps.casework.forms import InterventionPlanForm
from apps.casework.models import IndividualPlan, PrivateAttachment, SignedPlan
from apps.casework.plan_schema import activity_catalog, validate_interventions
from apps.casework.plan_signing import finalize_plan, issue_plan_token, plan_review
from apps.casework.private_attachments import case_attachments
from apps.casework.services import save_plan_period

from .factories import make_plan, set_active_center
from .test_barthel_assessment import draft as barthel_draft
from .test_barthel_assessment import values as assessment_values
from .test_consent_signing import png_value

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def private_root(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    return settings.PRIVATE_MEDIA_ROOT


def draft(person, specialist, **overrides):
    values = dict(
        beneficiary=person,
        enrollment=person.enrollments.get(service__code="LEGACY-OTHER"),
        center=person.center,
        specialist=specialist,
        workflow_version=2,
        plan_start_date=date(2026, 2, 1),
        status="draft",
        interventions=[{"code": "nursing.vital_signs", "notes": "Synthetic monitoring"}],
        review_frequency="six_monthly",
    )
    values.update(overrides)
    return IndividualPlan.objects.create(**values)


def signature_values(plan, actor, language="en"):
    return dict(
        review_token=issue_plan_token(
            plan, actor, plan.center, plan_review(plan, language, actor, plan.center)
        ),
        signer_name="Synthetic beneficiary",
        signer_role="beneficiary",
        relationship="",
        signature_data=png_value(),
        reviewed="on",
    )


def sign(plan, actor, **kwargs):
    return finalize_plan(
        plan=plan,
        actor=actor,
        center=plan.center,
        language="en",
        data=signature_values(plan, actor),
        **kwargs,
    )


def payload(person, specialist, **overrides):
    data = dict(
        enrollment=str(person.enrollments.get(service__code="LEGACY-OTHER").pk),
        plan_kind="individual",
        specialist=str(specialist.pk),
        status="draft",
        plan_start_date="2026-02-01",
        plan_end_date="2026-12-31",
        review_due_date="2026-08-01",
        review_frequency="six_monthly",
        select_nursing_vital_signs="on",
        notes_nursing_vital_signs="Synthetic notes",
    )
    data.update(overrides)
    return data


def login(client, user, center):
    client.force_login(user)
    set_active_center(client, center)


@pytest.mark.parametrize("kind", ["individual", "early_intervention"])
def test_new_plan_saves_selected_table_without_old_goals(
    client, coordinator_a, center_a, beneficiary_a, specialist_a, kind
):
    login(client, coordinator_a, center_a)
    response = client.post(
        reverse("plan_create"), payload(beneficiary_a, specialist_a, plan_kind=kind)
    )
    assert response.status_code == 302, response.context["form"].errors
    plan = IndividualPlan.objects.get()
    assert plan.workflow_version == 2
    assert plan.plan_kind == kind
    assert plan.interventions == [{"code": "nursing.vital_signs", "notes": "Synthetic notes"}]
    assert plan.status == "draft"
    assert plan.plan_end_date == date(2026, 12, 31)
    assert plan.review_due_date == date(2026, 8, 1)
    assert not plan.goals.exists()
    detail = client.get(response.url)
    assert detail.status_code == 200
    assert "Selected care activities" in detail.content.decode()
    assert "Measurable goals" not in detail.content.decode()
    assert "Synthetic notes" in detail.content.decode()
    assert client.get(reverse("plan_goal_create", args=[plan.pk])).status_code == 404


def test_plan_form_name_first_and_only_requested_review_choices(
    client, coordinator_a, center_a, beneficiary_a
):
    login(client, coordinator_a, center_a)
    response = client.get(reverse("plan_create"))
    form = response.context["form"]
    label = form.fields["enrollment"].label_from_instance(beneficiary_a.enrollments.get())
    assert label.startswith(beneficiary_a.full_name)
    assert beneficiary_a.beneficiary_code in label
    assert {value for value, _ in form.fields["review_frequency"].choices} == {
        "",
        "monthly",
        "quarterly",
        "six_monthly",
    }
    assert {"status", "plan_start_date", "plan_end_date", "review_due_date"} <= form.fields.keys()
    assert not form.fields["plan_start_date"].disabled
    assert "plan_type" not in form.fields


@pytest.mark.parametrize("score", [0, 55])
def test_plan_picker_prefers_completed_barthel_and_includes_zero(
    coordinator_a, center_a, beneficiary_a, specialist_a, django_assert_num_queries, score
):
    beneficiary_a.barthel_index = Decimal("40")
    beneficiary_a.save(update_fields=["barthel_index"])
    assessment = barthel_draft(beneficiary_a, specialist_a, score)
    finalize_assessment(
        assessment=assessment,
        actor=coordinator_a,
        center=center_a,
        language="en",
        data=assessment_values(assessment, coordinator_a),
    )
    form = InterventionPlanForm(user=coordinator_a, center=center_a)
    field = form.fields["enrollment"]
    enrollment = field.queryset.get(beneficiary=beneficiary_a)
    with django_assert_num_queries(0):
        label = field.label_from_instance(enrollment)
    assert label.endswith(f" | Barthel index: {score}/100")
    assert "Recorded intake" not in label


def test_plan_picker_marks_intake_value_and_omits_unavailable_scores(
    coordinator_a, center_a, beneficiary_a, specialist_a
):
    assessment = barthel_draft(beneficiary_a, specialist_a, 55)

    def label():
        field = InterventionPlanForm(user=coordinator_a, center=center_a).fields["enrollment"]
        return field.label_from_instance(field.queryset.get(beneficiary=beneficiary_a))

    assert "Barthel" not in label()  # A draft assessment is not an available result.
    beneficiary_a.barthel_index = Decimal("0")
    beneficiary_a.save(update_fields=["barthel_index"])
    assert label().endswith(" | Recorded intake Barthel index: 0/100")
    finalize_assessment(
        assessment=assessment,
        actor=coordinator_a,
        center=center_a,
        language="en",
        data=assessment_values(assessment, coordinator_a),
    )
    with patch("apps.casework.forms.timezone.localdate", return_value=date(2026, 1, 14)):
        assert label().endswith(" | Recorded intake Barthel index: 0/100")


def test_plan_picker_does_not_include_other_centers_barthel(
    coordinator_a, center_a, beneficiary_a, beneficiary_b
):
    beneficiary_b.barthel_index = Decimal("95")
    beneficiary_b.save(update_fields=["barthel_index"])
    field = InterventionPlanForm(user=coordinator_a, center=center_a).fields["enrollment"]
    choices = list(field.choices)
    assert any(beneficiary_a.full_name in label for _, label in choices)
    assert all(
        beneficiary_b.full_name not in label and "95/100" not in label for _, label in choices
    )


@pytest.mark.parametrize(
    "change",
    [
        {"select_nursing_vital_signs": ""},
        {"select_nursing_vital_signs": "", "select_nursing_other": "on"},
        {"status": "active"},
        {"status": "completed"},
        {"enrollment": "invalid"},
        {"review_frequency": "weekly"},
    ],
)
def test_invalid_plan_cannot_be_saved(
    client, coordinator_a, center_a, beneficiary_a, specialist_a, change
):
    login(client, coordinator_a, center_a)
    response = client.post(reverse("plan_create"), payload(beneficiary_a, specialist_a, **change))
    assert response.status_code == 200
    assert not IndividualPlan.objects.exists()


def test_preview_button_never_creates_plan(
    client, coordinator_a, center_a, beneficiary_a, specialist_a
):
    login(client, coordinator_a, center_a)
    response = client.post(
        reverse("plan_create"), payload(beneficiary_a, specialist_a, preview="1")
    )
    assert response.status_code == 200
    assert not IndividualPlan.objects.exists()
    assert response.context["form"]["notes_nursing_vital_signs"].value() == "Synthetic notes"


def test_catalog_contains_owner_technical_activities():
    with translation.override("ka"):
        rows = [r for r in activity_catalog() if r["code"].startswith("technical.")]
        assert [r["activity"] for r in rows] == [
            "დამხმარე ტექნიკური საშუალებების გამართულობის შემოწმება და გამოყენებაში დახმარება",
            "საცხოვრებელ გარემოში მცირე ტექნიკური დახმარება",
            "უსაფრთხო გარემოს მოწყობაში დახმარება",
            "სხვა",
        ]
    for value in [
        [],
        [{"code": "forged", "notes": ""}],
        [{"code": "technical.other", "notes": ""}],
        [{"code": "nursing.teaching", "notes": ""}] * 2,
    ]:
        with pytest.raises(ValidationError):
            validate_interventions(value)


def test_signing_activates_plan_and_preserves_exact_document(
    beneficiary_a, specialist_a, coordinator_a
):
    plan = draft(beneficiary_a, specialist_a)
    values = signature_values(plan, coordinator_a)
    record = finalize_plan(
        plan=plan, actor=coordinator_a, center=plan.center, language="en", data=values
    )
    plan.refresh_from_db()
    assert plan.status == "active"
    assert record.snapshot["review"]["activities"][0]["notes"] == "Synthetic monitoring"
    assert (
        PrivateAttachment.objects.filter(parent_type="signed_plan", parent_id=record.pk).count()
        == 2
    )
    assert (
        finalize_plan(
            plan=plan, actor=coordinator_a, center=plan.center, language="en", data=values
        )
        == record
    )
    plan.notes = "Attempted overwrite"
    with pytest.raises(ValidationError, match="cannot be edited"):
        plan.save()
    with transaction.atomic(), pytest.raises(DatabaseError, match="immutable"):
        IndividualPlan.objects.filter(pk=plan.pk).update(interventions=[])
    with transaction.atomic(), pytest.raises(DatabaseError, match="immutable"):
        SignedPlan.objects.filter(pk=record.pk).update(snapshot={})
    with pytest.raises(TypeError):
        record.delete()


def test_changed_review_rejects_signature(beneficiary_a, specialist_a, coordinator_a):
    plan = draft(beneficiary_a, specialist_a)
    values = signature_values(plan, coordinator_a)
    plan.notes = "Changed plan"
    plan.save()
    with pytest.raises(ValidationError, match="changed or expired"):
        finalize_plan(
            plan=plan, actor=coordinator_a, center=plan.center, language="en", data=values
        )
    assert not SignedPlan.objects.exists()
    assert not PrivateAttachment.objects.exists()


def test_storage_error_cleans_up_files_and_record(
    beneficiary_a, specialist_a, coordinator_a, private_root
):
    plan = draft(beneficiary_a, specialist_a)
    with patch(
        "apps.casework.plan_signing.plan_document_html",
        side_effect=OSError("Synthetic storage error"),
    ):
        with pytest.raises(OSError):
            sign(plan, coordinator_a)
    assert not SignedPlan.objects.exists()
    assert not PrivateAttachment.objects.exists()
    assert not [p for p in private_root.rglob("*") if p.is_file()]
    plan.refresh_from_db()
    assert plan.status == "draft"


def test_barthel_preview_and_signed_snapshot(
    client, coordinator_a, center_a, beneficiary_a, specialist_a
):
    from apps.casework.assessment_signing import finalize_assessment

    assessment = barthel_draft(beneficiary_a, specialist_a, 55)
    plan = draft(beneficiary_a, specialist_a)
    login(client, coordinator_a, center_a)
    url = reverse("plan_beneficiary_preview")
    params = {"enrollment": plan.enrollment_id, "date": "2026-02-01"}
    assert client.get(url, params).json()["barthel"] is None
    finalize_assessment(
        assessment=assessment,
        actor=coordinator_a,
        center=center_a,
        language="en",
        data=assessment_values(assessment, coordinator_a),
    )
    result = client.get(url, params).json()["barthel"]
    assert result["score"] == "55.00"
    assert result["dependency"] == "Severe dependency"
    assert client.get(url, {**params, "date": "01/01/2026"}).json()["barthel"] is None
    assert client.get(url, {**params, "date": "2026-01-01"}).json()["barthel"] is None
    record = sign(plan, coordinator_a)
    assert record.snapshot["review"]["barthel"] == result
    for route in ["plan_list", "beneficiary_detail", "plan_detail"]:
        response = client.get(
            reverse(
                route,
                args=[]
                if route == "plan_list"
                else [beneficiary_a.pk if route == "beneficiary_detail" else plan.pk],
            )
        )
        assert response.status_code == 200
        assert "55.00" in response.content.decode()


def test_signed_plan_routes_and_private_evidence(
    client, coordinator_a, center_a, center_b, manager, beneficiary_a, specialist_a
):
    plan = draft(beneficiary_a, specialist_a)
    login(client, coordinator_a, center_a)
    review_page = client.get(reverse("plan_sign", args=[plan.pk]))
    assert review_page.status_code == 200
    assert "signature-pad" in review_page.content.decode()
    record = sign(plan, coordinator_a)
    assert client.get(reverse("plan_update", args=[plan.pk])).status_code == 200
    for route in ["plan_document", "plan_download", "plan_signature_download"]:
        url = reverse(route, args=[record.pk])
        response = client.get(url)
        assert response.status_code == 200
        assert "no-store" in response["Cache-Control"]
        login(client, manager, center_b)
        assert client.get(url).status_code == 404
        login(client, coordinator_a, center_a)
    for action in ["upload", "delete"]:
        with pytest.raises(Http404):
            if action == "upload":
                case_attachments(coordinator_a, center_a).upload("signed_plan", record.pk)
            else:
                case_attachments(coordinator_a, center_a).delete(
                    PrivateAttachment.objects.filter(parent_id=record.pk).first().pk
                )


def test_unsigned_cannot_activate_via_service(beneficiary_a, specialist_a):
    plan = draft(beneficiary_a, specialist_a)
    plan.status = "active"
    with pytest.raises(ValidationError, match="must sign"):
        save_plan_period(plan)


def test_plan_kinds_have_independent_active_periods(beneficiary_a, specialist_a, coordinator_a):
    individual = draft(beneficiary_a, specialist_a)
    early = draft(beneficiary_a, specialist_a, plan_kind="early_intervention")
    sign(individual, coordinator_a)
    sign(early, coordinator_a)
    next_individual = draft(
        beneficiary_a, specialist_a, plan_start_date=date(2026, 3, 1), previous_plan=individual
    )
    sign(next_individual, coordinator_a)
    individual.refresh_from_db()
    early.refresh_from_db()
    assert individual.status == "superseded"
    assert early.status == "active"
    assert early.version_number == 1
    assert next_individual.version_number == 2


def test_paper_signature_alternative(beneficiary_a, specialist_a, coordinator_a):
    plan = draft(beneficiary_a, specialist_a)
    data = signature_values(plan, coordinator_a)
    data["signature_data"] = ""
    record = finalize_plan(
        plan=plan,
        actor=coordinator_a,
        center=plan.center,
        language="en",
        data=data,
        files={
            "paper_signature": SimpleUploadedFile(
                "signed.pdf", b"%PDF-1.7\nSynthetic paper signature"
            )
        },
    )
    assert record.snapshot["execution"]["method"] == "paper"
    assert PrivateAttachment.objects.filter(
        parent_id=record.pk, original_filename="signed-paper.pdf"
    ).exists()


def test_existing_plan_history_is_preserved(
    beneficiary_a, specialist_a, client, coordinator_a, center_a
):
    plan = make_plan(beneficiary_a, specialist_a)
    login(client, coordinator_a, center_a)
    response = client.get(reverse("plan_detail", args=[plan.pk]))
    assert response.status_code == 200
    assert plan.goals.count() == 1
    assert plan.workflow_version == 1


@pytest.mark.parametrize("language", ["en", "ka"])
def test_signed_plan_status_change_preserves_content(
    client, coordinator_a, center_a, beneficiary_a, specialist_a, language
):
    plan = draft(beneficiary_a, specialist_a)
    signed = sign(plan, coordinator_a)
    original = signed.snapshot
    login(client, coordinator_a, center_a)
    with translation.override(language):
        url = reverse("plan_update", args=[plan.pk])
        response = client.get(url)
        assert response.status_code == 200
        assert list(response.context["form"].fields) == ["status"]
        response = client.post(url, {"status": "completed", "notes": "Attempted overwrite"})
    assert response.status_code == 302
    plan.refresh_from_db()
    signed.refresh_from_db()
    assert plan.status == "completed"
    assert plan.notes == ""
    assert signed.snapshot == original
    assert client.get(reverse("plan_print", args=[plan.pk])).status_code == 302


def test_barthel_snapshot_rejects_stale_score_and_preserves_signed_score(
    beneficiary_a, specialist_a, coordinator_a
):
    from apps.casework.assessment_signing import finalize_assessment

    plan = draft(beneficiary_a, specialist_a)
    values = signature_values(plan, coordinator_a)
    assessment = barthel_draft(beneficiary_a, specialist_a, 55)
    finalize_assessment(
        assessment=assessment,
        actor=coordinator_a,
        center=plan.center,
        language="en",
        data=assessment_values(assessment, coordinator_a),
    )
    with pytest.raises(ValidationError, match="changed or expired"):
        finalize_plan(
            plan=plan, actor=coordinator_a, center=plan.center, language="en", data=values
        )
    signed = sign(plan, coordinator_a)
    assert signed.snapshot["review"]["barthel"]["score"] == "55.00"
    from apps.casework.assessment_engine import correct_assessment

    response_data = [
        {
            "template_field": field,
            "choice_value": str(max(choice["score"] for choice in field.allowed_choices)),
        }
        for field in assessment.template_version.fields.all()
    ]
    new_assessment = correct_assessment(
        assessment,
        response_data=response_data,
        actor=coordinator_a,
        reason="Synthetic correction for snapshot verification",
    )
    finalize_assessment(
        assessment=new_assessment,
        actor=coordinator_a,
        center=plan.center,
        language="en",
        data=assessment_values(new_assessment, coordinator_a),
    )
    signed.refresh_from_db()
    assert signed.snapshot["review"]["barthel"]["score"] == "55.00"
