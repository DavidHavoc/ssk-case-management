from datetime import date

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils.translation import override

from apps.audit.models import AuditEvent
from apps.casework.models import AttachmentParentType, PrivateAttachment
from apps.centers.forms import StaffProfileForm
from apps.centers.models import StaffProfile
from apps.core.authorization import accessible_centers

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def private_media_root(tmp_path, settings):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    return settings.PRIVATE_MEDIA_ROOT


def test_staff_contract_dates_must_be_ordered(specialist_a):
    staff = specialist_a.staff_profile
    staff.contract_signed_on = date(2026, 8, 15)
    staff.contract_valid_until = date(2026, 8, 14)

    with pytest.raises(ValidationError, match="cannot end before it begins"):
        staff.full_clean()


def test_manager_updates_complete_staff_record(client, manager, specialist_a):
    staff = specialist_a.staff_profile
    client.force_login(manager)
    response = client.post(
        reverse("staff_update", kwargs={"pk": staff.pk}),
        {
            "project_program": "Synthetic Youth Program",
            "job_title": "Lead Specialist",
            "status": StaffProfile.Status.FINISHED,
            "contact_number": "+995 555 100 200",
            "email": "updated.staff@example.invalid",
            "contract_signed_on": "2026-01-15",
            "contract_valid_until": "2026-12-31",
            "description": "Synthetic professional description.",
            "notes": "Synthetic internal staff notes.",
        },
    )

    assert response.status_code == 302
    staff.refresh_from_db()
    staff.user.refresh_from_db()
    specialist_a.refresh_from_db()
    assert staff.project_program == "Synthetic Youth Program"
    assert staff.job_title == "Lead Specialist"
    assert staff.status == StaffProfile.Status.FINISHED
    assert staff.contact_number == "+995 555 100 200"
    assert staff.user.email == "updated.staff@example.invalid"
    assert staff.contract_signed_on == date(2026, 1, 15)
    assert staff.contract_valid_until == date(2026, 12, 31)
    assert staff.description == "Synthetic professional description."
    assert staff.notes == "Synthetic internal staff notes."
    assert specialist_a.description == staff.description
    assert not accessible_centers(staff.user).exists()
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.UPDATE,
        target_type="StaffProfile",
        target_id=staff.pk,
        actor=manager,
    ).exists()

    response = client.get(reverse("staff_detail", kwargs={"pk": staff.pk}))
    body = response.content.decode()
    assert "Synthetic Youth Program" in body
    assert "Lead Specialist" in body
    assert "+995 555 100 200" in body
    assert "Synthetic internal staff notes." in body


def test_staff_fields_have_georgian_labels(specialist_a):
    with override("ka"):
        form = StaffProfileForm(instance=specialist_a.staff_profile)
        assert str(form.fields["project_program"].label) == "პროექტი/პროგრამა"
        assert str(form.fields["job_title"].label) == "თანამდებობა"
        assert str(form.fields["contact_number"].label) == "საკონტაქტო ნომერი"
        assert str(form.fields["email"].label) == "ელ-ფოსტა"
        assert str(StaffProfile.Status.FINISHED.label) == "დასრულებული"
        assert (
            str(PrivateAttachment.DocumentType.EMPLOYEE_CONTRACT.label)
            == "თანამშრომლის ხელშეკრულება"
        )


def test_view_permission_does_not_allow_staff_changes(client, coordinator_a, specialist_a):
    view_permission = Permission.objects.get(
        codename="view_staffprofile", content_type__app_label="centers"
    )
    coordinator_a.user_permissions.add(view_permission)
    client.force_login(coordinator_a)

    assert (
        client.get(
            reverse("staff_detail", kwargs={"pk": specialist_a.staff_profile.pk})
        ).status_code
        == 200
    )
    assert (
        client.get(
            reverse("staff_update", kwargs={"pk": specialist_a.staff_profile.pk})
        ).status_code
        == 403
    )
    assert (
        client.get(
            reverse("staff_attachment_upload", kwargs={"pk": specialist_a.staff_profile.pk})
        ).status_code
        == 403
    )


def test_change_permission_allows_staff_changes(client, coordinator_a, specialist_a):
    change_permission = Permission.objects.get(
        codename="change_staffprofile", content_type__app_label="centers"
    )
    coordinator_a.user_permissions.add(change_permission)
    client.force_login(coordinator_a)

    response = client.post(
        reverse("staff_update", kwargs={"pk": specialist_a.staff_profile.pk}),
        {
            "project_program": "Permission Managed Program",
            "job_title": "Specialist",
            "status": StaffProfile.Status.ACTIVE,
            "contact_number": "+995 555 300 400",
            "email": specialist_a.staff_profile.user.email,
            "contract_signed_on": "",
            "contract_valid_until": "",
            "description": specialist_a.description,
            "notes": "",
        },
    )

    assert response.status_code == 302
    specialist_a.staff_profile.refresh_from_db()
    assert specialist_a.staff_profile.project_program == "Permission Managed Program"


def test_staff_contract_upload_download_and_pdf_requirement(
    client, manager, coordinator_a, specialist_a
):
    staff = specialist_a.staff_profile
    client.force_login(manager)
    upload_url = reverse("staff_attachment_upload", kwargs={"pk": staff.pk})

    response = client.post(
        upload_url,
        {
            "document_type": PrivateAttachment.DocumentType.EMPLOYEE_CONTRACT,
            "file": SimpleUploadedFile(
                "synthetic-contract.pdf",
                b"%PDF-1.7\nSynthetic employee contract",
                content_type="application/pdf",
            ),
        },
    )
    assert response.status_code == 302
    attachment = PrivateAttachment.objects.get()
    assert attachment.parent_type == AttachmentParentType.STAFF_PROFILE
    assert attachment.parent_id == staff.pk
    assert attachment.document_type == PrivateAttachment.DocumentType.EMPLOYEE_CONTRACT

    response = client.get(reverse("staff_attachment_download", kwargs={"pk": attachment.pk}))
    assert response.status_code == 200
    assert response.streaming
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.DOWNLOAD,
        target_id=attachment.pk,
        actor=manager,
    ).exists()

    response = client.post(
        upload_url,
        {
            "document_type": PrivateAttachment.DocumentType.PROJECT_AGREEMENT,
            "file": SimpleUploadedFile(
                "not-a-contract.txt",
                b"Synthetic text file",
                content_type="text/plain",
            ),
        },
    )
    assert response.status_code == 200
    assert "must be PDFs" in response.content.decode()
    assert PrivateAttachment.objects.count() == 1

    view_permission = Permission.objects.get(
        codename="view_staffprofile", content_type__app_label="centers"
    )
    coordinator_a.user_permissions.add(view_permission)
    client.force_login(coordinator_a)
    response = client.get(reverse("staff_attachment_download", kwargs={"pk": attachment.pk}))
    assert response.status_code == 200
