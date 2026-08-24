from __future__ import annotations

from collections.abc import Mapping

from .models import AuditEvent

SAFE_METADATA_KEYS = {
    "format",
    "record_count",
    "report_type",
    "parent_type",
    "file_extension",
    "result",
    "instrument_code",
    "template_version_id",
}


def record_event(
    *,
    actor,
    event_type: str,
    target_type: str,
    target_id=None,
    center=None,
    outcome: str = AuditEvent.Outcome.SUCCESS,
    metadata: Mapping[str, object] | None = None,
) -> AuditEvent:
    safe_metadata = {
        key: value for key, value in (metadata or {}).items() if key in SAFE_METADATA_KEYS
    }
    return AuditEvent.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        center=center,
        event_type=event_type,
        outcome=outcome,
        target_type=target_type[:64],
        target_id=target_id,
        metadata=safe_metadata,
    )
