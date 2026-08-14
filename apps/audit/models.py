from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.centers.models import Center


class AuditEvent(models.Model):
    class EventType(models.TextChoices):
        SENSITIVE_READ = "sensitive_read", _("Sensitive read")
        CREATE = "create", _("Create")
        UPDATE = "update", _("Update")
        DELETE = "delete", _("Delete")
        EXPORT = "export", _("Export")
        DOWNLOAD = "download", _("Download")
        LOGIN_SUCCESS = "login_success", _("Login success")
        LOGIN_FAILURE = "login_failure", _("Login failure")

    class Outcome(models.TextChoices):
        SUCCESS = "success", _("Success")
        DENIED = "denied", _("Denied")
        FAILURE = "failure", _("Failure")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    center = models.ForeignKey(
        Center,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    event_type = models.CharField(max_length=24, choices=EventType.choices, db_index=True)
    outcome = models.CharField(
        max_length=16, choices=Outcome.choices, default=Outcome.SUCCESS, db_index=True
    )
    target_type = models.CharField(max_length=64)
    target_id = models.UUIDField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["center", "occurred_at"]),
            models.Index(fields=["actor", "occurred_at"]),
            models.Index(fields=["target_type", "target_id"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk and AuditEvent.objects.filter(pk=self.pk).exists():
            raise TypeError("Audit events are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("Audit events are append-only.")
