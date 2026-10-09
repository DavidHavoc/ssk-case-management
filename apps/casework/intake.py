"""Authorized projection and atomic writes for optional beneficiary intake."""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.centers.models import Center
from apps.core.authorization import beneficiary_intake_capabilities

from .intake_schema import CARE_FIELDS, CONSENT_FIELDS, HEALTH_FIELDS, SOCIAL_FIELDS
from .models import Beneficiary, BeneficiaryIntake, BeneficiaryIntakeRevision


def intake_field_names(capabilities):
    names = ()
    if capabilities["health_social"]:
        names += HEALTH_FIELDS + SOCIAL_FIELDS
    if capabilities["consent"]:
        names += CONSENT_FIELDS
    if capabilities["care"]:
        names += CARE_FIELDS
    return names


def intake_initial(beneficiary, names):
    # values() prevents restricted consent data entering a specialist form/context.
    if beneficiary._state.adding or not names:
        return {}
    return (
        BeneficiaryIntake.objects.filter(beneficiary_id=beneficiary.pk).values(*names).first() or {}
    )


@transaction.atomic
def save_beneficiary_intake(*, beneficiary, actor, center, values):
    beneficiary = Beneficiary.objects.select_for_update().get(pk=beneficiary.pk)
    actor = get_user_model().objects.get(pk=actor.pk)
    center = Center.objects.get(pk=center.pk)
    allowed = intake_field_names(beneficiary_intake_capabilities(actor, center, beneficiary))
    if not allowed or not set(values).issubset(allowed):
        raise PermissionDenied
    if not values:
        return None
    intake = BeneficiaryIntake.objects.filter(beneficiary=beneficiary).first()
    before = {name: getattr(intake, name) for name in allowed} if intake else {}
    if intake is None and not any(values.values()):
        return None
    intake = intake or BeneficiaryIntake(beneficiary=beneficiary)
    for name, value in values.items():
        setattr(intake, name, value)
    intake.full_clean()
    after = {name: getattr(intake, name) for name in allowed}
    if before == after:
        return intake
    intake.save()
    BeneficiaryIntakeRevision.objects.create(
        intake=intake, recorded_by=actor, before_values=before, after_values=after
    )
    record_event(
        actor=actor,
        center=center,
        event_type=AuditEvent.EventType.UPDATE,
        target_type="BeneficiaryIntake",
        target_id=intake.pk,
    )
    return intake
