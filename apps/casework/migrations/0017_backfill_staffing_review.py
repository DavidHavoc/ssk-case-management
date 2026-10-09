from django.db import migrations
from django.db.models import F, Q
from django.utils import timezone


def backfill(apps, schema_editor):
    alias = schema_editor.connection.alias
    today = timezone.localdate()
    Beneficiary = apps.get_model("casework", "Beneficiary")
    Enrollment = apps.get_model("casework", "ServiceEnrollment")
    Assignment = apps.get_model("casework", "EnrollmentSpecialistAssignment")
    Placement = apps.get_model("casework", "EnrollmentCenterPlacement")
    Period = apps.get_model("casework", "BeneficiaryStaffingPeriod")
    Grant = apps.get_model("casework", "LegacyStaffingGrant")
    Specialist = apps.get_model("centers", "SpecialistProfile")
    terminal = {"exited", "completed", "cancelled"}
    for person in Beneficiary.objects.using(alias).all().iterator():
        teams = []
        uncertain = False
        enrollments = Enrollment.objects.using(alias).filter(beneficiary=person).exclude(status__in=terminal)
        if not enrollments.exists():
            continue
        for enrollment in enrollments:
            placements = Placement.objects.using(alias).filter(
                enrollment=enrollment, valid_from__lte=today,
            ).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=today))
            if placements.count() != 1 or not placements.get().center.is_active:
                uncertain = True
                continue
            center = placements.get().center
            all_rows = Assignment.objects.using(alias).filter(enrollment=enrollment)
            rows = all_rows.filter(valid_from__lte=today).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=today))
            eligible = Specialist.objects.using(alias).filter(
                center_assignments__center=center, staff_profile__user__is_active=True,
                staff_profile__status="active",
            ).values_list("pk", flat=True)
            eligible_ids = set(eligible)
            for row in rows:
                if row.specialist_id in eligible_ids:
                    Grant.objects.using(alias).get_or_create(assignment_id=row.pk, defaults={
                        "enrollment_id": enrollment.pk, "specialist_id": row.specialist_id, "center_id": center.pk,
                        "placement_id": placements.get().pk,
                        # Owner decision, 2026-10-09: preserve evidence but end legacy
                        # authorization at deployment. Expiry is exclusive.
                        "captured_on": today, "expires_on": today,
                        "valid_from": row.valid_from, "valid_to": row.valid_to,
                    })
            # Unknown or future appointments, duplicate roles and unequal service teams need review.
            if all_rows.filter(Q(valid_from__isnull=True) | Q(valid_from__gt=today)).exists():
                uncertain = True
            leads = list(rows.filter(assignment_role="primary"))
            helpers = list(rows.filter(assignment_role="secondary"))
            if len(leads) != 1 or len(helpers) > 1:
                uncertain = True
                continue
            lead = leads[0]
            helper = helpers[0] if helpers else None
            if any(row.specialist_id not in eligible_ids or row.legacy_dates_incomplete for row in rows):
                uncertain = True
            if helper and (helper.specialist_id == lead.specialist_id or
                           (helper.valid_from, helper.valid_to) != (lead.valid_from, lead.valid_to)):
                uncertain = True
            teams.append((lead.specialist_id, helper.specialist_id if helper else None,
                          lead.valid_from, lead.valid_to))
        if not uncertain and teams and len(teams) == enrollments.count() and len(set(teams)) == 1:
            lead, helper, _start, end = teams[0]
            period = Period.objects.using(alias).create(
                beneficiary_id=person.pk, lead_id=lead, helper_id=helper,
                valid_from=today, valid_to=end, migration_backfill=True,
            )
            Period.objects.using(alias).filter(pk=period.pk).update(updated_at=period.created_at)


def reverse_backfill(apps, schema_editor):
    alias = schema_editor.connection.alias
    Period = apps.get_model("casework", "BeneficiaryStaffingPeriod")
    Grant = apps.get_model("casework", "LegacyStaffingGrant")
    if Period.objects.using(alias).filter(Q(migration_backfill=False) | ~Q(updated_at=F("created_at"))).exists():
        raise RuntimeError("Staffing has changed since migration. Preserve the schema and review rollback; no history was deleted.")
    Period.objects.using(alias).all().delete()
    Grant.objects.using(alias).all().delete()


class Migration(migrations.Migration):
    dependencies = [("casework", "0016_beneficiary_staffing_periods")]
    operations = [migrations.RunPython(backfill, reverse_backfill)]
