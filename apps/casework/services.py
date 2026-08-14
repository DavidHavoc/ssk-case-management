from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal

from django.db import connection, transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import ServiceVisit, SpecialistMonthlyServiceSummary


def _lock_summary_scope(specialist_id, center_id, summary_month: date) -> None:
    if connection.vendor != "postgresql":
        return
    value = f"{specialist_id}:{center_id}:{summary_month:%Y-%m}".encode()
    lock_key = int.from_bytes(hashlib.sha256(value).digest()[:8], "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])


@transaction.atomic
def rebuild_monthly_summary(
    specialist_id, center_id, summary_month: date
) -> SpecialistMonthlyServiceSummary | None:
    month = summary_month.replace(day=1)
    _lock_summary_scope(specialist_id, center_id, month)
    visits = ServiceVisit.objects.filter(
        specialist_id=specialist_id,
        center_id=center_id,
        visit_month=month,
    )
    if not visits.exists():
        SpecialistMonthlyServiceSummary.objects.filter(
            specialist_id=specialist_id,
            center_id=center_id,
            summary_month=month,
        ).delete()
        return None
    totals = visits.aggregate(
        completed_visits=Count("id", filter=Q(status=ServiceVisit.Status.COMPLETED)),
        total_service_units=Coalesce(
            Sum("service_units", filter=Q(status=ServiceVisit.Status.COMPLETED)),
            Decimal("0"),
        ),
        total_duration_minutes=Coalesce(
            Sum("duration_minutes", filter=Q(status=ServiceVisit.Status.COMPLETED)), 0
        ),
        unique_beneficiaries=Count(
            "beneficiary_id", distinct=True, filter=Q(status=ServiceVisit.Status.COMPLETED)
        ),
        no_show_count=Count("id", filter=Q(status=ServiceVisit.Status.NO_SHOW)),
        cancelled_count=Count("id", filter=Q(status=ServiceVisit.Status.CANCELLED)),
    )
    summary, _ = SpecialistMonthlyServiceSummary.objects.update_or_create(
        specialist_id=specialist_id,
        center_id=center_id,
        summary_month=month,
        defaults={**totals, "last_rebuilt_at": timezone.now()},
    )
    return summary
