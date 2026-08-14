from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.models import LoginThrottle
from apps.audit.models import AuditEvent
from apps.casework.models import AttachmentParentType, PrivateAttachment

from .factories import make_assessment, make_coordinator, make_visit, set_active_center

pytestmark = pytest.mark.django_db
User = get_user_model()


def _attachment(
    *,
    parent,
    parent_type: str,
    user,
    filename: str = "synthetic.pdf",
    content: bytes = b"%PDF-1.7\nSynthetic test file",
) -> PrivateAttachment:
    return PrivateAttachment.objects.create(
        parent_type=parent_type,
        parent_id=parent.pk,
        center=parent.center,
        file=SimpleUploadedFile(filename, content, content_type="application/pdf"),
        original_filename=filename,
        content_type="application/pdf",
        uploaded_by=user,
    )


@pytest.fixture(autouse=True)
def private_media_root(tmp_path, settings):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    return settings.PRIVATE_MEDIA_ROOT


def test_private_attachment_randomizes_path_and_sanitizes_name(
    coordinator_a, beneficiary_a, private_media_root
):
    attachment = _attachment(
        parent=beneficiary_a,
        parent_type=AttachmentParentType.BENEFICIARY,
        user=coordinator_a,
        filename="../../synthetic record.pdf",
    )
    stored_path = Path(attachment.file.path)
    assert stored_path.is_relative_to(private_media_root)
    assert stored_path.name != "synthetic record.pdf"
    assert stored_path.suffix == ".pdf"
    assert attachment.original_filename == "synthetic record.pdf"
    assert attachment.sha256
    with pytest.raises(ValueError, match="do not have public URLs"):
        _ = attachment.file.url

    windows_name = _attachment(
        parent=beneficiary_a,
        parent_type=AttachmentParentType.BENEFICIARY,
        user=coordinator_a,
        filename=r"..\private\synthetic.pdf",
    )
    assert windows_name.original_filename == "synthetic.pdf"
    assert windows_name.content_type == "application/pdf"


def test_private_attachment_validates_extension_content_and_size(
    coordinator_a, beneficiary_a, settings
):
    with pytest.raises(ValidationError, match="not allowed"):
        _attachment(
            parent=beneficiary_a,
            parent_type=AttachmentParentType.BENEFICIARY,
            user=coordinator_a,
            filename="malware.exe",
            content=b"MZ synthetic",
        )
    with pytest.raises(ValidationError, match="does not match a PDF"):
        _attachment(
            parent=beneficiary_a,
            parent_type=AttachmentParentType.BENEFICIARY,
            user=coordinator_a,
            filename="forged.pdf",
            content=b"not a pdf",
        )
    settings.MAX_UPLOAD_SIZE = 8
    with pytest.raises(ValidationError, match="too large"):
        _attachment(
            parent=beneficiary_a,
            parent_type=AttachmentParentType.BENEFICIARY,
            user=coordinator_a,
            content=b"%PDF-1.7 synthetic",
        )


def test_beneficiary_attachment_download_is_parent_authorized_and_audited(
    client, coordinator_a, specialist_a, center_a, beneficiary_a
):
    attachment = _attachment(
        parent=beneficiary_a,
        parent_type=AttachmentParentType.BENEFICIARY,
        user=coordinator_a,
    )
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    response = client.get(reverse("attachment_download", kwargs={"pk": attachment.pk}))
    assert response.status_code == 200
    assert response.streaming
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.DOWNLOAD,
        target_id=attachment.pk,
        outcome=AuditEvent.Outcome.SUCCESS,
    ).exists()

    client.force_login(specialist_a.staff_profile.user)
    set_active_center(client, center_a)
    denied = client.get(reverse("attachment_download", kwargs={"pk": attachment.pk}))
    assert denied.status_code == 404
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.DOWNLOAD,
        target_id=attachment.pk,
        outcome=AuditEvent.Outcome.DENIED,
    ).exists()


def test_attachment_upload_sets_parent_before_validation_and_audits(
    client, coordinator_a, center_a, beneficiary_a
):
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    response = client.post(
        reverse(
            "attachment_upload",
            kwargs={
                "parent_type": AttachmentParentType.BENEFICIARY,
                "parent_id": beneficiary_a.pk,
            },
        ),
        {
            "file": SimpleUploadedFile(
                r"folder\synthetic.txt",
                b"Synthetic attachment without beneficiary data.",
                content_type="application/x-untrusted",
            )
        },
    )

    assert response.status_code == 302
    attachment = PrivateAttachment.objects.get()
    assert attachment.parent_id == beneficiary_a.pk
    assert attachment.center == center_a
    assert attachment.uploaded_by == coordinator_a
    assert attachment.original_filename == "synthetic.txt"
    assert attachment.content_type == "text/plain"
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.CREATE,
        target_type="PrivateAttachment",
        target_id=attachment.pk,
    ).exists()


def test_case_attachment_follows_case_record_access(client, specialist_a, center_a, beneficiary_a):
    assessment = make_assessment(beneficiary_a, specialist_a)
    user = specialist_a.staff_profile.user
    attachment = _attachment(
        parent=assessment,
        parent_type=AttachmentParentType.ASSESSMENT,
        user=user,
    )
    client.force_login(user)
    set_active_center(client, center_a)
    assert (
        client.get(reverse("attachment_download", kwargs={"pk": attachment.pk})).status_code == 200
    )


def test_cross_center_attachment_download_is_denied(
    client, center_a, center_b, coordinator_a, beneficiary_b
):
    coordinator_b = make_coordinator(center_b, "coordinator-b")
    attachment = _attachment(
        parent=beneficiary_b,
        parent_type=AttachmentParentType.BENEFICIARY,
        user=coordinator_b,
    )
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    assert (
        client.get(reverse("attachment_download", kwargs={"pk": attachment.pk})).status_code == 404
    )


def test_attachment_delete_rechecks_parent_access_and_removes_file_after_commit(
    client,
    specialist_a,
    center_a,
    beneficiary_a,
    coordinator_a,
    django_capture_on_commit_callbacks,
):
    assessment = make_assessment(beneficiary_a, specialist_a)
    attachment = _attachment(
        parent=assessment,
        parent_type=AttachmentParentType.ASSESSMENT,
        user=coordinator_a,
    )
    stored_path = Path(attachment.file.path)
    client.force_login(specialist_a.staff_profile.user)
    set_active_center(client, center_a)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(reverse("attachment_delete", kwargs={"pk": attachment.pk}))

    assert response.status_code == 302
    assert not PrivateAttachment.objects.filter(pk=attachment.pk).exists()
    assert not stored_path.exists()
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.DELETE,
        target_id=attachment.pk,
    ).exists()


def test_specialist_cannot_delete_beneficiary_attachment(
    client, specialist_a, center_a, beneficiary_a, coordinator_a
):
    attachment = _attachment(
        parent=beneficiary_a,
        parent_type=AttachmentParentType.BENEFICIARY,
        user=coordinator_a,
    )
    client.force_login(specialist_a.staff_profile.user)
    set_active_center(client, center_a)

    response = client.post(reverse("attachment_delete", kwargs={"pk": attachment.pk}))

    assert response.status_code == 404
    assert PrivateAttachment.objects.filter(pk=attachment.pk).exists()


def test_case_delete_is_manager_only_center_scoped_and_audited(
    client,
    manager,
    coordinator_a,
    specialist_a,
    center_a,
    beneficiary_a,
):
    visit = make_visit(beneficiary_a, specialist_a)
    url = reverse("visit_delete", kwargs={"pk": visit.pk})

    for user in (coordinator_a, specialist_a.staff_profile.user):
        client.force_login(user)
        set_active_center(client, center_a)
        assert client.post(url).status_code == 403
        assert visit.__class__.objects.filter(pk=visit.pk).exists()

    client.force_login(manager)
    set_active_center(client, center_a)
    response = client.post(url)
    assert response.status_code == 302
    assert not visit.__class__.objects.filter(pk=visit.pk).exists()
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.DELETE,
        target_type="ServiceVisit",
        target_id=visit.pk,
        actor=manager,
    ).exists()


def test_manager_delete_cannot_cross_active_center(
    client, manager, center_a, beneficiary_b, specialist_b
):
    visit = make_visit(beneficiary_b, specialist_b)
    client.force_login(manager)
    set_active_center(client, center_a)

    response = client.post(reverse("visit_delete", kwargs={"pk": visit.pk}))

    assert response.status_code == 404
    assert visit.__class__.objects.filter(pk=visit.pk).exists()


def test_failed_attachment_audit_rolls_back_row_and_stored_file(
    client,
    monkeypatch,
    coordinator_a,
    center_a,
    beneficiary_a,
    private_media_root,
):
    def fail_audit(**kwargs):
        raise RuntimeError("synthetic audit failure")

    monkeypatch.setattr("apps.casework.views.record_event", fail_audit)
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    client.raise_request_exception = False
    response = client.post(
        reverse(
            "attachment_upload",
            kwargs={
                "parent_type": AttachmentParentType.BENEFICIARY,
                "parent_id": beneficiary_a.pk,
            },
        ),
        {
            "file": SimpleUploadedFile(
                "synthetic.pdf", b"%PDF-1.7\nSynthetic", content_type="application/pdf"
            )
        },
    )

    assert response.status_code == 500
    assert PrivateAttachment.objects.count() == 0
    assert not [path for path in private_media_root.rglob("*") if path.is_file()]


def test_csv_export_escapes_formulas_and_excludes_other_centers(
    client, coordinator_a, center_a, beneficiary_a, beneficiary_b
):
    beneficiary_a.full_name = '=HYPERLINK("https://example.invalid")'
    beneficiary_a.save()
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    response = client.get(reverse("report_export"), {"type": "beneficiaries"})
    body = response.content.decode("utf-8-sig")
    assert response.status_code == 200
    assert "'=HYPERLINK" in body
    assert beneficiary_b.full_name not in body
    assert beneficiary_a.personal_id not in body
    assert AuditEvent.objects.filter(event_type=AuditEvent.EventType.EXPORT).exists()


def test_specialist_cannot_export_reports(client, specialist_a, center_a):
    client.force_login(specialist_a.staff_profile.user)
    set_active_center(client, center_a)
    response = client.get(reverse("report_export"), {"type": "visits"})
    assert response.status_code == 403


def test_csrf_protects_state_changing_views(coordinator_a, center_a, beneficiary_a):
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(coordinator_a)
    set_active_center(csrf_client, center_a)
    response = csrf_client.post(
        reverse("beneficiary_update", kwargs={"pk": beneficiary_a.pk}),
        {"full_name": "Unauthorized without CSRF"},
    )
    assert response.status_code == 403


def test_security_headers_are_present(client):
    response = client.get(reverse("login"))
    assert response["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response["Content-Security-Policy"]
    assert response["Cross-Origin-Resource-Policy"] == "same-origin"


@override_settings(LOGIN_RATE_LIMIT_ATTEMPTS=2, LOGIN_RATE_LIMIT_WINDOW_SECONDS=900)
def test_login_rate_limit_blocks_repeated_failures(client, coordinator_a):
    url = reverse("login")
    for _ in range(2):
        response = client.post(
            url,
            {"username": coordinator_a.username, "password": "incorrect"},
            REMOTE_ADDR="203.0.113.10",
        )
        assert response.status_code == 200
    assert LoginThrottle.objects.filter(failure_count__gte=2).exists()

    blocked = client.post(
        url,
        {
            "username": coordinator_a.username,
            "password": "Synthetic-Test-Password-42!",
        },
        REMOTE_ADDR="203.0.113.10",
    )
    assert blocked.status_code == 200
    assert "Unable to sign in" in blocked.content.decode()


def test_user_email_is_unique_case_insensitively_for_password_reset(manager):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            User.objects.create_user(
                username="different.synthetic.user@example.invalid",
                email=manager.email.upper(),
                password="Synthetic-Test-Password-42!",
            )


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_password_reset_sends_token_without_disclosing_unknown_accounts(client, manager):
    response = client.post(reverse("password_reset"), {"email": manager.email})
    assert response.status_code == 302
    assert response.url == reverse("password_reset_done")
    assert len(mail.outbox) == 1
    assert "/accounts/reset/" in mail.outbox[0].body

    response = client.post(
        reverse("password_reset"), {"email": "unknown.synthetic@example.invalid"}
    )
    assert response.status_code == 302
    assert response.url == reverse("password_reset_done")
    assert len(mail.outbox) == 1


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    LOGIN_RATE_LIMIT_ATTEMPTS=1,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS=900,
)
def test_password_reset_rate_limit_keeps_generic_response_and_stops_email_flood(client, manager):
    url = reverse("password_reset")
    first = client.post(url, {"email": manager.email}, REMOTE_ADDR="203.0.113.20")
    second = client.post(url, {"email": manager.email}, REMOTE_ADDR="203.0.113.20")

    assert first.status_code == 302
    assert second.status_code == 302
    assert first.url == second.url == reverse("password_reset_done")
    assert len(mail.outbox) == 1
    assert LoginThrottle.objects.filter(failure_count=1).count() == 2
