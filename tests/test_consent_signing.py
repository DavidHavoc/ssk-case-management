import base64
import io
import uuid
from html import unescape
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse
from django.utils import translation
from PIL import Image, ImageDraw

from apps.audit.models import AuditEvent
from apps.casework.consent_signing import (
    MAX_SIGNATURE_CHARACTERS,
    ConsentSigningForm,
    consent_review,
    finalize_consent,
    issue_review_token,
    validate_signature,
)
from apps.casework.intake import save_beneficiary_intake
from apps.casework.models import AttachmentParentType, Beneficiary, PrivateAttachment, SignedConsent
from apps.casework.storage import private_file_storage

from .factories import set_active_center

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def private_root(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    return settings.PRIVATE_MEDIA_ROOT


def png_value(*, size=(1000, 360), blank=False, mode="RGB", color="white", format="PNG"):
    image = Image.new(mode, size, color)
    if not blank:
        ImageDraw.Draw(image).line(
            [(60, 140), (140, 70), (115, 160), (260, 110)], fill="black", width=5
        )
    data = io.BytesIO()
    image.save(data, format=format)
    return "data:image/png;base64," + base64.b64encode(data.getvalue()).decode()


def post_data(client, person, *, role="representative", language="en"):
    client.cookies["django_language"] = language
    with translation.override(language):
        response = client.get(reverse("consent_sign", args=[person.pk]))
    assert response.status_code == 200
    return {
        "review_token": response.context["form"].initial["review_token"],
        "signer_name": "Synthetic signer <script>alert(1)</script>",
        "signer_role": role,
        "relationship": "Synthetic stated relative",
        "signature_data": png_value(),
        "reviewed": "on",
    }


def create_signed(client, manager, center, person, language="en", role="representative"):
    client.force_login(manager)
    set_active_center(client, center)
    data = post_data(client, person, language=language, role=role)
    with translation.override(language):
        response = client.post(reverse("consent_sign", args=[person.pk]), data)
    assert response.status_code == 302, response.content.decode()[:3000]
    return SignedConsent.objects.get(), data


def artifact_bytes(record):
    attachment = PrivateAttachment.objects.get(
        parent_id=record.pk, original_filename="signed-consent.txt"
    )
    with attachment.file.open("rb") as source:
        return source.read()


@pytest.mark.parametrize("language", ["en", "ka"])
@pytest.mark.parametrize("staff", ["manager", "coordinator_a"])
@pytest.mark.parametrize("role", ["beneficiary", "representative"])
def test_complete_bilingual_flow_exact_evidence(
    client, request, staff, center_a, beneficiary_a, language, role
):
    actor = request.getfixturevalue(staff)
    save_beneficiary_intake(
        beneficiary=beneficiary_a,
        actor=actor,
        center=center_a,
        values={
            "service_consent": "no",
            "care_sharing_consent": "yes",
            "confidentiality_consent": "",
            "media_consent": "decline",
        },
    )
    record, data = create_signed(client, actor, center_a, beneficiary_a, language, role)
    assert record.recorded_by == actor
    assert record.language == language
    assert record.snapshot["beneficiary"] == {
        "name": beneficiary_a.full_name,
        "code": beneficiary_a.beneficiary_code,
    }
    assert [d["value"] for d in record.snapshot["decisions"]] == ["no", "yes", "", "decline"]
    assert record.snapshot["execution"]["signer_name"] == data["signer_name"]
    assert record.snapshot["execution"]["role"] == role
    assert record.snapshot["execution"]["relationship"] == (
        "" if role == "beneficiary" else data["relationship"]
    )
    text = artifact_bytes(record).decode()
    for decision in record.snapshot["decisions"]:
        assert decision["wording"] in unescape(text) and decision["answer"] in unescape(text)
    for phrase in record.snapshot["media"]:
        assert phrase in unescape(text)
    assert record.signed_at.isoformat() in text
    assert (actor.get_full_name() or actor.username) in text
    assert "data:image/png;base64," in text and "data:font/ttf;base64," in text
    assert "SIL OPEN FONT LICENSE Version 1.1" in text
    assert "&lt;script&gt;" in text and "<script>" not in text
    assert ("ხელმომწერის სახელი და გვარი" if language == "ka" else "Signer full name") in text
    client.cookies["django_language"] = "en" if language == "ka" else "ka"
    viewed = client.get(reverse("consent_document", args=[record.pk]))
    assert b"".join(viewed.streaming_content) == artifact_bytes(record)
    downloaded = client.get(reverse("consent_download", args=[record.pk]))
    assert b"".join(downloaded.streaming_content) == artifact_bytes(record)
    assert downloaded["Content-Type"] == "text/html; charset=utf-8"
    assert downloaded["Content-Disposition"] == 'attachment; filename="signed-consent.html"'
    assert "no-store" in downloaded["Cache-Control"]
    assert downloaded["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'none'" in downloaded["Content-Security-Policy"]
    assert PrivateAttachment.objects.filter(parent_id=record.pk).count() == 2
    assert AuditEvent.objects.filter(target_type="SignedConsent", event_type="create").count() == 1
    assert (
        AuditEvent.objects.filter(target_type="PrivateAttachment", event_type="download").count()
        == 2
    )
    assert all(
        not event.metadata or set(event.metadata) <= {"parent_type", "file_extension"}
        for event in AuditEvent.objects.filter(
            target_type__in=["SignedConsent", "PrivateAttachment"]
        )
    )


def test_old_files_and_snapshot_survive_changes_and_new_signature(
    client, manager, center_a, beneficiary_a
):
    old, data = create_signed(client, manager, center_a, beneficiary_a)
    old_bytes = artifact_bytes(old)
    old_snapshot = old.snapshot.copy()
    beneficiary_a.full_name = "Changed synthetic beneficiary"
    beneficiary_a.save()
    save_beneficiary_intake(
        beneficiary=beneficiary_a, actor=manager, center=center_a, values={"service_consent": "yes"}
    )
    manager.first_name = "Changed synthetic recorder"
    manager.save()
    detail = client.get(reverse("beneficiary_detail", args=[beneficiary_a.pk]))
    assert detail.context["consent_decisions_differ"]
    # A retry of a completed token returns its original document, even after current edits.
    response = client.post(reverse("consent_sign", args=[beneficiary_a.pk]), data)
    assert response.url == reverse("consent_document", args=[old.pk])
    assert SignedConsent.objects.count() == 1
    fresh = post_data(client, beneficiary_a)
    response = client.post(reverse("consent_sign", args=[beneficiary_a.pk]), fresh)
    assert response.status_code == 302 and SignedConsent.objects.count() == 2
    old.refresh_from_db()
    assert old.snapshot == old_snapshot and artifact_bytes(old) == old_bytes
    detail = client.get(reverse("beneficiary_detail", args=[beneficiary_a.pk]))
    assert not detail.context["consent_decisions_differ"]
    assert len(detail.context["signed_consents"]) == 2


@pytest.mark.parametrize(
    "change",
    ["decision", "identity", "wording", "version", "language", "expired", "tampered", "reverted"],
)
def test_stale_submission_rereviews_and_clears_drawing(
    client, manager, center_a, beneficiary_a, change
):
    client.force_login(manager)
    set_active_center(client, center_a)
    data = post_data(client, beneficiary_a)
    if change in {"decision", "reverted"}:
        save_beneficiary_intake(
            beneficiary=beneficiary_a,
            actor=manager,
            center=center_a,
            values={"media_consent": "decline"},
        )
        if change == "reverted":
            save_beneficiary_intake(
                beneficiary=beneficiary_a,
                actor=manager,
                center=center_a,
                values={"media_consent": ""},
            )
    if change == "identity":
        Beneficiary.objects.filter(pk=beneficiary_a.pk).update(full_name="Changed synthetic name")
    if change == "language":
        client.cookies["django_language"] = "ka"
    if change == "tampered":
        data["review_token"] += "x"
    context = (
        patch("apps.casework.consent_signing.TEMPLATE_VERSION", "SSK-CONSENT-2")
        if change == "version"
        else patch("apps.casework.consent_signing.MEDIA_DECLARATION", ["Changed wording"])
        if change == "wording"
        else patch("apps.casework.consent_signing.TOKEN_MAX_AGE", -1)
        if change == "expired"
        else patch("apps.casework.consent_signing.TOKEN_MAX_AGE", 3600)
    )
    with context, translation.override("ka" if change == "language" else "en"):
        response = client.post(reverse("consent_sign", args=[beneficiary_a.pk]), data)
    assert response.status_code == 200
    assert response.context["form"].non_field_errors()
    assert response.context["form"]["signature_data"].value() == ""
    assert not response.context["form"]["reviewed"].value()
    assert response.context["form"]["review_token"].value() != data["review_token"]
    assert not SignedConsent.objects.exists() and not PrivateAttachment.objects.exists()


@pytest.mark.parametrize(
    "value",
    [
        "",
        "data:image/jpeg;base64,aGVsbG8=",
        "data:image/png;base64,@@@@",
        "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nmalformed").decode(),
        "x" * (MAX_SIGNATURE_CHARACTERS + 1),
    ],
)
def test_invalid_signature_data(value):
    with pytest.raises(ValidationError):
        validate_signature(value)


@pytest.mark.parametrize(
    "options",
    [
        dict(blank=True),
        dict(size=(199, 80)),
        dict(size=(1401, 600)),
        dict(size=(200, 601)),
        dict(mode="RGBA", color=(0, 0, 0, 0), blank=True),
        dict(blank=True, color="black"),
        dict(format="JPEG"),
    ],
)
def test_decoding_dimensions_blank_and_invisible_drawing(options):
    with pytest.raises(ValidationError):
        validate_signature(png_value(**options))


@pytest.mark.parametrize("language", ["en", "ka"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("signature_data", ""),
        ("signer_name", ""),
        ("signer_role", ""),
        ("signer_role", "forged"),
        ("relationship", ""),
        ("reviewed", ""),
    ],
)
def test_invalid_fields_save_nothing_and_translated_errors(
    client, manager, center_a, beneficiary_a, language, field, value
):
    client.force_login(manager)
    set_active_center(client, center_a)
    data = post_data(client, beneficiary_a, language=language)
    data[field] = value
    with translation.override(language):
        response = client.post(reverse("consent_sign", args=[beneficiary_a.pk]), data)
    assert response.status_code == 200 and field in response.context["form"].errors
    assert not SignedConsent.objects.exists() and not PrivateAttachment.objects.exists()
    assert (
        "ხელმოწერილი თანხმობის შენახვა" if language == "ka" else "Save signed consent"
    ) in response.content.decode()


@pytest.mark.parametrize("actor_name", ["specialist_a", "specialist_b", "central_hr"])
def test_no_signature_access_for_other_roles(
    client, request, manager, center_a, beneficiary_a, actor_name
):
    record, _ = create_signed(client, manager, center_a, beneficiary_a)
    actor = request.getfixturevalue(actor_name)
    actor = (
        actor.staff_profile.user
        if hasattr(actor, "staff_profile") and not hasattr(actor, "is_authenticated")
        else actor
    )
    client.force_login(actor)
    set_active_center(client, center_a)
    for route, pk in [
        ("consent_sign", beneficiary_a.pk),
        ("consent_print", beneficiary_a.pk),
        ("consent_document", record.pk),
        ("consent_download", record.pk),
    ]:
        assert client.get(reverse(route, args=[pk])).status_code in {403, 404}
    assert client.post(reverse("consent_sign", args=[beneficiary_a.pk]), {}).status_code in {
        403,
        404,
    }


def test_anonymous_and_csrf_and_forged_binding(
    client, manager, coordinator_a, center_a, beneficiary_a, beneficiary_b
):
    record, data = create_signed(client, manager, center_a, beneficiary_a)
    client.logout()
    for route, pk in [
        ("consent_sign", beneficiary_a.pk),
        ("consent_print", beneficiary_a.pk),
        ("consent_document", record.pk),
        ("consent_download", record.pk),
    ]:
        assert client.get(reverse(route, args=[pk])).status_code == 302
    csrf = Client(enforce_csrf_checks=True)
    csrf.force_login(manager)
    set_active_center(csrf, center_a)
    assert csrf.post(reverse("consent_sign", args=[beneficiary_a.pk]), data).status_code == 403
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    assert client.get(reverse("consent_sign", args=[beneficiary_b.pk])).status_code == 404
    response = client.post(reverse("consent_sign", args=[beneficiary_a.pk]), data)
    assert response.status_code == 200 and response.context["form"].non_field_errors()
    assert SignedConsent.objects.count() == 1
    assert client.get(reverse("consent_document", args=[uuid.uuid4()])).status_code == 404


def test_private_files_cannot_use_general_attachment_routes(
    client, manager, center_a, beneficiary_a
):
    record, _ = create_signed(client, manager, center_a, beneficiary_a)
    attachment = PrivateAttachment.objects.filter(parent_id=record.pk).first()
    assert client.get(reverse("attachment_download", args=[attachment.pk])).status_code == 404
    assert client.post(reverse("attachment_delete", args=[attachment.pk])).status_code == 404
    assert (
        client.get(
            reverse("attachment_upload", args=[AttachmentParentType.SIGNED_CONSENT, record.pk])
        ).status_code
        == 404
    )
    with pytest.raises(ValueError):
        _ = attachment.file.url
    assert SignedConsent.objects.count() == 1 and PrivateAttachment.objects.count() == 2


@pytest.mark.parametrize("failure", ["first_write", "second_write", "after_write", "audit"])
def test_atomic_rollback_cleans_even_storage_failure_after_bytes(
    client, manager, center_a, beneficiary_a, private_root, failure
):
    client.force_login(manager)
    set_active_center(client, center_a)
    data = post_data(client, beneficiary_a)
    original = private_file_storage._save
    calls = 0

    def storage_save(name, content):
        nonlocal calls
        calls += 1
        if failure == "first_write" or (failure == "second_write" and calls == 2):
            raise OSError("Synthetic failure")
        result = original(name, content)
        if failure == "after_write" and calls == 2:
            raise OSError("Synthetic failure after bytes")
        return result

    with (
        patch.object(private_file_storage, "_save", side_effect=storage_save),
        patch(
            "apps.casework.consent_signing.record_event",
            side_effect=OSError("Synthetic audit failure"),
        )
        if failure == "audit"
        else patch("apps.casework.consent_signing.TOKEN_MAX_AGE", 3600),
    ):
        response = client.post(reverse("consent_sign", args=[beneficiary_a.pk]), data)
    assert response.status_code == 200 and response.context["form"].non_field_errors()
    assert not SignedConsent.objects.exists() and not PrivateAttachment.objects.exists()
    assert not list(private_root.rglob("*.*"))
    assert not AuditEvent.objects.filter(
        event_type="create", target_type__in=["SignedConsent", "PrivateAttachment"]
    ).exists()


def test_completed_evidence_rejects_model_queryset_update_and_delete(
    client, manager, center_a, beneficiary_a
):
    record, _ = create_signed(client, manager, center_a, beneficiary_a)
    with pytest.raises(ValidationError):
        record.save()
    with pytest.raises(TypeError):
        record.delete()
    with pytest.raises(TypeError), transaction.atomic():
        SignedConsent.objects.filter(pk=record.pk).delete()
    attachment = PrivateAttachment.objects.filter(parent_id=record.pk).first()
    with pytest.raises(ValidationError):
        attachment.save()
    with pytest.raises(TypeError), transaction.atomic():
        PrivateAttachment.objects.filter(pk=attachment.pk).delete()
    for model, pk, values in [
        (SignedConsent, record.pk, {"snapshot": {}}),
        (PrivateAttachment, attachment.pk, {"parent_type": "beneficiary"}),
    ]:
        with pytest.raises(DatabaseError), transaction.atomic():
            model.objects.filter(pk=pk).update(**values)


def test_printable_fallback_unknown_decisions_and_no_automatic_record(
    client, manager, center_a, beneficiary_a
):
    client.force_login(manager)
    set_active_center(client, center_a)
    review = client.get(reverse("consent_sign", args=[beneficiary_a.pk]))
    assert all(
        d["value"] == "" and d["answer"] == "Not recorded"
        for d in review.context["document"]["decisions"]
    )
    assert review.context["form"]["signer_role"].value() is None
    assert not review.context["form"]["reviewed"].value()
    printed = client.get(reverse("consent_print", args=[beneficiary_a.pk]))
    assert printed.status_code == 200
    assert "Unsigned printable copy" in printed.content.decode()
    assert "data:image/png" not in printed.content.decode()
    assert "data:font/ttf" in printed.content.decode()
    assert not SignedConsent.objects.exists()
    assert client.post(reverse("consent_document", args=[uuid.uuid4()]), {}).status_code == 405


@pytest.mark.parametrize("revocation", ["account", "staff", "membership", "center", "transfer"])
def test_save_reloads_authority_after_review(
    client, manager, coordinator_a, center_a, center_b, beneficiary_a, revocation
):
    from django.utils import timezone

    from apps.casework.services import transfer_enrollment
    from apps.centers.models import StaffProfile

    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    data = post_data(client, beneficiary_a)
    form = ConsentSigningForm(data)
    assert form.is_valid()
    if revocation == "account":
        type(coordinator_a).objects.filter(pk=coordinator_a.pk).update(is_active=False)
    elif revocation == "staff":
        StaffProfile.objects.filter(user=coordinator_a).update(status=StaffProfile.Status.INACTIVE)
    elif revocation == "membership":
        coordinator_a.staff_profile.centers.remove(center_a)
    elif revocation == "center":
        type(center_a).objects.filter(pk=center_a.pk).update(is_active=False)
    else:
        enrollment = beneficiary_a.enrollments.first()
        transfer_enrollment(
            enrollment,
            destination_offering=center_b.service_offerings.get(service=enrollment.service),
            effective_date=timezone.localdate(),
            reason="Synthetic transfer",
            actor=manager,
        )
    with pytest.raises(Exception) as error:
        finalize_consent(
            person=beneficiary_a,
            actor=coordinator_a,
            center=center_a,
            language="en",
            values=form.cleaned_data,
        )
    assert type(error.value).__name__ in {"Http404", "PermissionDenied"}
    assert not SignedConsent.objects.exists() and not PrivateAttachment.objects.exists()


def test_transfer_keeps_signed_files_in_original_center(
    client, manager, coordinator_a, center_a, center_b, beneficiary_a
):
    from django.utils import timezone

    from apps.casework.services import transfer_enrollment

    from .factories import make_coordinator

    record, _ = create_signed(client, coordinator_a, center_a, beneficiary_a)
    original = artifact_bytes(record)
    enrollment = beneficiary_a.enrollments.first()
    transfer_enrollment(
        enrollment,
        destination_offering=center_b.service_offerings.get(service=enrollment.service),
        effective_date=timezone.localdate(),
        reason="Synthetic transfer",
        actor=manager,
    )
    coordinator_b = make_coordinator(center_b, "consent-transfer-b")
    client.force_login(coordinator_b)
    set_active_center(client, center_b)
    for route in ("consent_document", "consent_download"):
        assert client.get(reverse(route, args=[record.pk])).status_code == 404
    detail = client.get(reverse("beneficiary_detail", args=[beneficiary_a.pk]))
    assert detail.status_code == 200 and not detail.context["signed_consents"].exists()
    assert record.template_version not in detail.content.decode()
    assert artifact_bytes(record) == original
    client.force_login(manager)
    set_active_center(client, center_b)
    assert client.get(reverse("consent_download", args=[record.pk])).status_code == 404


def test_confirmed_lead_helper_keep_health_access_without_signatures(
    client, manager, center_a, specialist_a, beneficiary_a
):
    from django.utils import timezone

    from apps.casework.services import replace_beneficiary_staffing

    from .factories import make_specialist

    helper = make_specialist(center_a, "consent-helper")
    replace_beneficiary_staffing(
        beneficiary=beneficiary_a,
        lead=specialist_a,
        helper=helper,
        effective_date=timezone.localdate(),
        center=center_a,
        actor=manager,
    )
    record, _ = create_signed(client, manager, center_a, beneficiary_a)
    for person in (specialist_a, helper):
        client.force_login(person.staff_profile.user)
        set_active_center(client, center_a)
        detail = client.get(reverse("beneficiary_detail", args=[beneficiary_a.pk]))
        assert detail.status_code == 200
        assert "can_sign_consent" not in detail.context
        assert "SSK-CONSENT-1" not in detail.content.decode()
        assert (
            client.get(reverse("beneficiary_intake_update", args=[beneficiary_a.pk])).status_code
            == 200
        )
        assert client.get(reverse("consent_download", args=[record.pk])).status_code == 404


def test_signature_is_absent_from_general_exports(client, manager, center_a, beneficiary_a):
    record, _ = create_signed(client, manager, center_a, beneficiary_a)
    exported = client.get(reverse("report_export"), {"type": "beneficiaries"}).content.decode(
        "utf-8-sig"
    )
    assert "Synthetic signer" not in exported and "data:image" not in exported
    assert str(record.pk) not in exported


@pytest.mark.django_db(transaction=True)
def test_postgres_concurrent_retry_and_raw_delete_preservation(manager, center_a, beneficiary_a):
    if connection.vendor != "postgresql":
        pytest.skip("Row locking and raw delete guard require PostgreSQL.")
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections

    review = consent_review(beneficiary_a, "en")
    values = {
        "review_token": issue_review_token(beneficiary_a, manager, center_a, review),
        "signer_name": "Synthetic concurrent signer",
        "signer_role": "beneficiary",
        "relationship": "",
        "signature_data": png_value(),
        "reviewed": "on",
    }
    barrier = Barrier(2)

    def worker():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return finalize_consent(
                person=beneficiary_a, actor=manager, center=center_a, language="en", values=values
            ).pk
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = [future.result(timeout=20) for future in [pool.submit(worker) for _ in range(2)]]
    assert (
        ids[0] == ids[1]
        and SignedConsent.objects.count() == 1
        and PrivateAttachment.objects.count() == 2
    )
    for table, pk in [
        ("casework_signedconsent", ids[0]),
        ("casework_privateattachment", PrivateAttachment.objects.first().pk),
    ]:
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {table} WHERE id=%s", [pk])


@pytest.mark.django_db(transaction=True)
def test_postgres_review_write_serializes_with_intake(manager, center_a, beneficiary_a):
    if connection.vendor != "postgresql":
        pytest.skip("Consent and intake row locking requires PostgreSQL.")
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections

    from apps.casework.consent_signing import StaleConsent

    review = consent_review(beneficiary_a, "en")
    values = {
        "review_token": issue_review_token(beneficiary_a, manager, center_a, review),
        "signer_name": "Synthetic stale signer",
        "signer_role": "beneficiary",
        "signature_data": png_value(),
        "reviewed": "on",
    }
    barrier = Barrier(2)

    def worker():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            finalize_consent(
                person=beneficiary_a, actor=manager, center=center_a, language="en", values=values
            )
            return "signed"
        except StaleConsent:
            return "stale"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            Beneficiary.objects.select_for_update().get(pk=beneficiary_a.pk)
            future = pool.submit(worker)
            barrier.wait(timeout=10)
            save_beneficiary_intake(
                beneficiary=beneficiary_a,
                actor=manager,
                center=center_a,
                values={"service_consent": "no"},
            )
        assert future.result(timeout=20) == "stale"
    assert not SignedConsent.objects.exists() and not PrivateAttachment.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_signing_schema_forward_reverse_preserves_original_rows(manager, center_a, beneficiary_a):
    from django.db.migrations.executor import MigrationExecutor

    base = ("casework", "0019_beneficiary_intake")
    leaf = ("casework", "0022_signed_consent_guards")
    executor = MigrationExecutor(connection)
    executor.migrate([base])
    old_apps = executor.loader.project_state([base]).apps

    def rows():
        return {
            model._meta.label: list(model.objects.order_by("pk").values())
            for model in old_apps.get_models()
        }

    original = rows()
    try:
        executor = MigrationExecutor(connection)
        executor.migrate([leaf])
        assert rows() == original
        assert not SignedConsent.objects.exists()
        executor = MigrationExecutor(connection)
        executor.migrate([base])
        assert rows() == original
        executor = MigrationExecutor(connection)
        executor.migrate([leaf])
        assert rows() == original
    finally:
        MigrationExecutor(connection).migrate([leaf])


@pytest.mark.django_db(transaction=True)
def test_schema_reversal_refuses_to_remove_completed_evidence(manager, center_a, beneficiary_a):
    from django.db.migrations.executor import MigrationExecutor

    review = consent_review(beneficiary_a, "en")
    record = finalize_consent(
        person=beneficiary_a,
        actor=manager,
        center=center_a,
        language="en",
        values={
            "review_token": issue_review_token(beneficiary_a, manager, center_a, review),
            "signer_name": "Synthetic migration signer",
            "signer_role": "beneficiary",
            "signature_data": png_value(),
            "reviewed": "on",
        },
    )
    original = artifact_bytes(record)
    with pytest.raises(RuntimeError, match="Signed consent evidence exists"):
        MigrationExecutor(connection).migrate([("casework", "0019_beneficiary_intake")])
    assert (
        SignedConsent.objects.filter(pk=record.pk).exists() and artifact_bytes(record) == original
    )
    assert PrivateAttachment.objects.filter(parent_id=record.pk).count() == 2
