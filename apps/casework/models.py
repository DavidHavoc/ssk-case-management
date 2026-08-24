from __future__ import annotations

import hashlib
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.signals import m2m_changed, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _

from apps.centers.models import Center, SpecialistProfile
from apps.core.models import ValidatedModel
from apps.core.validators import phone_number_validator

from .age import CompletedAge, calculate_completed_age, ssk_age_band
from .storage import private_file_storage
from .validators import validate_private_upload


class EffectiveDatedCatalogModel(ValidatedModel):
    code = models.CharField(max_length=48, unique=True)
    name_en = models.CharField(max_length=180)
    name_ka = models.CharField(max_length=180)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    source_version = models.CharField(max_length=120, blank=True)

    class Meta:
        abstract = True

    def clean(self) -> None:
        self.code = self.code.strip().upper()
        self.name_en = self.name_en.strip()
        self.name_ka = self.name_ka.strip()
        self.source_version = self.source_version.strip()
        if self.valid_from and self.valid_to and self.valid_to <= self.valid_from:
            raise ValidationError({"valid_to": _("Valid to must be later than valid from.")})

    def is_effective(self, on_date: date) -> bool:
        return (
            self.is_active
            and (self.valid_from is None or self.valid_from <= on_date)
            and (self.valid_to is None or on_date < self.valid_to)
        )

    @property
    def localized_name(self) -> str:
        language = (get_language() or "en").split("-", maxsplit=1)[0]
        return self.name_ka if language == "ka" else self.name_en


class ServiceDefinition(EffectiveDatedCatalogModel):
    class Family(models.TextChoices):
        HOME_CARE = "home_care", _("Home Care")
        FOOD_DELIVERY = "food_delivery", _("Food Delivery")
        EARLY_INTERVENTION = "early_intervention", _("Early Intervention")
        FUTURE = "future", _("Future Service")
        LEGACY = "legacy", _("Legacy Service")

    family = models.CharField(max_length=32, choices=Family.choices, db_index=True)
    description = models.TextField(blank=True)
    reporting_order = models.PositiveIntegerField(default=0)
    allow_same_service_overlap = models.BooleanField(default=False)

    class Meta:
        ordering = ["reporting_order", "name_en", "code"]

    def __str__(self) -> str:
        return self.localized_name

    def clean(self) -> None:
        super().clean()
        self.description = self.description.strip()


class ServiceActivityDefinition(EffectiveDatedCatalogModel):
    applicable_services = models.ManyToManyField(
        ServiceDefinition,
        related_name="service_activities",
        blank=True,
        help_text=_("Leave empty to allow this activity for every service."),
    )
    default_unit_label = models.CharField(max_length=48, default="service unit")
    reporting_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["reporting_order", "name_en", "code"]

    def __str__(self) -> str:
        return self.localized_name

    def clean(self) -> None:
        super().clean()
        self.default_unit_label = self.default_unit_label.strip()

    def is_available_for(self, service_id, on_date: date) -> bool:
        if not self.is_effective(on_date):
            return False
        configured_services = self.applicable_services.all()
        return (
            not configured_services.exists() or configured_services.filter(pk=service_id).exists()
        )


class VisitLocationDefinition(EffectiveDatedCatalogModel):
    class Kind(models.TextChoices):
        PHYSICAL = "physical", _("Physical")
        REMOTE = "remote", _("Remote")

    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.PHYSICAL)
    reporting_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["reporting_order", "name_en", "code"]

    def __str__(self) -> str:
        return self.localized_name


class CenterServiceOffering(ValidatedModel):
    center = models.ForeignKey(Center, on_delete=models.PROTECT, related_name="service_offerings")
    service = models.ForeignKey(
        ServiceDefinition, on_delete=models.PROTECT, related_name="center_offerings"
    )
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["center__name", "service__reporting_order", "service__name_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["center", "service", "valid_from"],
                name="unique_center_service_offering_start",
            ),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True)
                | Q(valid_from__isnull=True)
                | Q(valid_to__gt=F("valid_from")),
                name="center_service_offering_dates_ordered",
            ),
        ]
        indexes = [models.Index(fields=["center", "service", "is_active"])]

    def __str__(self) -> str:
        return f"{self.service} at {self.center}"

    def clean(self) -> None:
        if self.valid_from and self.valid_to and self.valid_to <= self.valid_from:
            raise ValidationError({"valid_to": _("Valid to must be later than valid from.")})

    def is_effective(self, on_date: date) -> bool:
        return (
            self.is_active
            and self.center.is_active
            and self.service.is_effective(on_date)
            and (self.valid_from is None or self.valid_from <= on_date)
            and (self.valid_to is None or on_date < self.valid_to)
        )


class Region(EffectiveDatedCatalogModel):
    class Meta:
        ordering = ["name_en"]

    def __str__(self) -> str:
        return self.localized_name


class Municipality(EffectiveDatedCatalogModel):
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="municipalities")

    class Meta:
        ordering = ["region__name_en", "name_en"]
        indexes = [models.Index(fields=["region", "is_active"])]

    def __str__(self) -> str:
        return f"{self.localized_name}, {self.region.localized_name}"


class DiagnosisDefinition(EffectiveDatedCatalogModel):
    coding_system = models.CharField(max_length=80)
    applicable_services = models.ManyToManyField(
        ServiceDefinition, related_name="diagnosis_definitions", blank=True
    )

    class Meta:
        ordering = ["coding_system", "code"]

    def __str__(self) -> str:
        return f"{self.code} | {self.localized_name}"

    def clean(self) -> None:
        super().clean()
        self.coding_system = self.coding_system.strip()


class SocialStatusDefinition(EffectiveDatedCatalogModel):
    class Sensitivity(models.TextChoices):
        STANDARD = "standard", _("Standard")
        RESTRICTED = "restricted", _("Restricted")

    sensitivity = models.CharField(
        max_length=16,
        choices=Sensitivity.choices,
        default=Sensitivity.RESTRICTED,
    )

    class Meta:
        ordering = ["name_en", "code"]

    def __str__(self) -> str:
        return self.localized_name


class Beneficiary(ValidatedModel):
    class ServiceType(models.TextChoices):
        DISABILITY = "disability_support", _("Disability Support")
        CHILD_PROTECTION = "child_protection", _("Child Protection")
        SOCIAL_PROTECTION = "social_protection", _("Social Protection")
        REHABILITATION = "rehabilitation", _("Rehabilitation")
        OTHER = "other", _("Other")

    class ServiceStatus(models.TextChoices):
        APPLIED = "applied", _("Applied")
        ACTIVE = "active", _("Active")
        ON_HOLD = "on_hold", _("On Hold")
        EXITED = "exited", _("Exited")

    class Sex(models.TextChoices):
        MALE = "male", _("Male")
        FEMALE = "female", _("Female")
        OTHER = "other", _("Other")

    class FamilyStatus(models.TextChoices):
        SINGLE = "single", _("Single")
        MARRIED = "married", _("Married")
        DIVORCED = "divorced", _("Divorced")
        WIDOWED = "widowed", _("Widowed")
        SEPARATED = "separated", _("Separated")
        OTHER = "other", _("Other")

    beneficiary_code = models.CharField(max_length=32, unique=True)
    service_type = models.CharField(max_length=32, choices=ServiceType.choices, db_index=True)
    service_status = models.CharField(
        max_length=16, choices=ServiceStatus.choices, default=ServiceStatus.APPLIED, db_index=True
    )
    center = models.ForeignKey(Center, on_delete=models.PROTECT, related_name="beneficiaries")
    full_name = models.CharField(max_length=180)
    personal_id = models.CharField(max_length=64, blank=True)
    sex = models.CharField(max_length=16, choices=Sex.choices, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    region = models.CharField(max_length=120, blank=True)
    municipality = models.CharField(max_length=120, blank=True)
    region_ref = models.ForeignKey(
        Region,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="beneficiaries",
        verbose_name=_("Region"),
    )
    municipality_ref = models.ForeignKey(
        Municipality,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="beneficiaries",
        verbose_name=_("Municipality"),
    )
    address = models.TextField(blank=True)
    guardian_parent = models.CharField(max_length=180, blank=True)
    phone = models.CharField(max_length=40, blank=True, validators=[phone_number_validator])
    email = models.EmailField(blank=True)
    diagnosis_status = models.TextField(blank=True)
    barthel_index = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    first_assessment_date = models.DateField(null=True, blank=True)
    family_status = models.CharField(max_length=16, choices=FamilyStatus.choices, blank=True)
    enrollment_date = models.DateField(null=True, blank=True, db_index=True)
    first_service_date = models.DateField(null=True, blank=True)
    application_contract_number = models.CharField(max_length=80, blank=True)
    exit_date = models.DateField(null=True, blank=True, db_index=True)
    exit_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    specialists = models.ManyToManyField(
        SpecialistProfile,
        through="BeneficiarySpecialistAssignment",
        related_name="beneficiaries",
    )

    class Meta:
        ordering = ["full_name", "beneficiary_code"]
        indexes = [
            models.Index(fields=["center", "service_status"]),
            models.Index(fields=["center", "full_name"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["personal_id"],
                condition=~Q(personal_id=""),
                name="unique_nonblank_beneficiary_personal_id",
            )
        ]

    def __str__(self) -> str:
        return f"{self.beneficiary_code} | {self.full_name}"

    @property
    def age(self) -> int | None:
        calculated = self.age_on(timezone.localdate())
        return calculated.years if calculated else None

    def age_on(self, reference_date: date) -> CompletedAge | None:
        if not self.birth_date:
            return None
        return calculate_completed_age(self.birth_date, reference_date)

    @property
    def age_years_months(self) -> str:
        calculated = self.age_on(timezone.localdate())
        if not calculated:
            return ""
        return str(
            _("%(years)s years, %(months)s months")
            % {"years": calculated.years, "months": calculated.months}
        )

    def ssk_age_band_on(self, reference_date: date) -> str | None:
        calculated = self.age_on(reference_date)
        return ssk_age_band(calculated.total_months) if calculated else None

    @property
    def ssk_age_band(self) -> str:
        return self.ssk_age_band_on(timezone.localdate()) or ""

    @property
    def age_category(self) -> str:
        age = self.age
        if age is None:
            return ""
        if age < 6:
            return str(_("Early Childhood"))
        if age < 18:
            return str(_("Child or Adolescent"))
        if age < 60:
            return str(_("Adult"))
        return str(_("Senior"))

    def clean(self) -> None:
        self.beneficiary_code = self.beneficiary_code.strip().upper()
        self.full_name = self.full_name.strip()
        self.personal_id = self.personal_id.strip()
        self.region = self.region.strip()
        self.municipality = self.municipality.strip()
        self.address = self.address.strip()
        self.guardian_parent = self.guardian_parent.strip()
        self.phone = self.phone.strip()
        self.email = self.email.strip().lower()
        self.diagnosis_status = self.diagnosis_status.strip()
        self.application_contract_number = self.application_contract_number.strip()
        self.exit_reason = self.exit_reason.strip()
        self.notes = self.notes.strip()
        today = timezone.localdate()
        errors = {}
        if self.birth_date and self.birth_date > today:
            errors["birth_date"] = _("Birth date cannot be in the future.")
        if self.municipality_ref_id and not self.region_ref_id:
            errors["region_ref"] = _("Select the municipality's region.")
        if (
            self.municipality_ref_id
            and self.region_ref_id
            and self.municipality_ref.region_id != self.region_ref_id
        ):
            errors["municipality_ref"] = _(
                "The municipality does not belong to the selected region."
            )
        if self.exit_date and self.enrollment_date and self.exit_date < self.enrollment_date:
            errors["exit_date"] = _("Exit date cannot be before enrollment date.")
        if (
            self.first_service_date
            and self.enrollment_date
            and self.first_service_date < self.enrollment_date
        ):
            errors["first_service_date"] = _("First service date cannot be before enrollment date.")
        if errors:
            raise ValidationError(errors)


class ServiceEnrollment(ValidatedModel):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        ACTIVE = "active", _("Active")
        SUSPENDED = "suspended", _("Suspended")
        COMPLETED = "completed", _("Completed")
        EXITED = "exited", _("Exited")
        CANCELLED = "cancelled", _("Cancelled")

    TERMINAL_STATUSES = frozenset({Status.COMPLETED, Status.EXITED, Status.CANCELLED})

    beneficiary = models.ForeignKey(
        Beneficiary, on_delete=models.PROTECT, related_name="enrollments"
    )
    service = models.ForeignKey(
        ServiceDefinition, on_delete=models.PROTECT, related_name="enrollments"
    )
    episode_code = models.CharField(max_length=48, unique=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    start_date = models.DateField(null=True, blank=True, db_index=True)
    end_date = models.DateField(null=True, blank=True, db_index=True)
    first_service_date = models.DateField(null=True, blank=True)
    application_contract_number = models.CharField(max_length=80, blank=True)
    exit_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    prior_enrollment = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="subsequent_enrollments",
    )
    legacy_source_id = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    legacy_service_value = models.CharField(max_length=32, blank=True, editable=False)
    legacy_status_value = models.CharField(max_length=16, blank=True, editable=False)
    legacy_dates_incomplete = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ["-start_date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True)
                | Q(start_date__isnull=True)
                | Q(end_date__gte=F("start_date")),
                name="service_enrollment_dates_ordered",
            )
        ]
        indexes = [
            models.Index(fields=["beneficiary", "status"]),
            models.Index(fields=["service", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.episode_code} | {self.service}"

    @property
    def is_terminal(self) -> bool:
        return self.status in self.TERMINAL_STATUSES

    def placement_on(self, on_date: date):
        return (
            self.center_placements.filter(
                Q(valid_to__isnull=True) | Q(valid_to__gt=on_date),
                valid_from__lte=on_date,
            )
            .select_related("center", "offering", "offering__service")
            .first()
        )

    def status_on(self, on_date: date) -> str | None:
        if self.start_date and on_date < self.start_date:
            return None
        if self.end_date and on_date >= self.end_date:
            return None
        state_event = (
            self.state_events.filter(effective_date__isnull=False, effective_date__lte=on_date)
            .order_by("-effective_date", "-created_at", "-id")
            .first()
        )
        if state_event:
            return state_event.new_state
        if self.start_date and on_date >= self.start_date:
            return self.Status.ACTIVE
        return None

    @property
    def current_placement(self):
        return self.placement_on(timezone.localdate())

    @property
    def current_center(self):
        placement = self.current_placement
        return placement.center if placement else None

    def clean(self) -> None:
        self.episode_code = self.episode_code.strip().upper()
        self.application_contract_number = self.application_contract_number.strip()
        self.exit_reason = self.exit_reason.strip()
        self.notes = self.notes.strip()
        errors = {}
        if (
            self.start_date
            and self.end_date
            and self.end_date <= self.start_date
            and not (self.legacy_source_id and self.end_date == self.start_date)
        ):
            errors["end_date"] = _("End date must be later than start date.")
        if (
            self.first_service_date
            and self.start_date
            and self.first_service_date < self.start_date
        ):
            errors["first_service_date"] = _(
                "First service date cannot be before enrollment start date."
            )
        if self.prior_enrollment_id:
            prior = self.prior_enrollment
            if prior.pk == self.pk:
                errors["prior_enrollment"] = _("An enrollment cannot link to itself.")
            elif prior.beneficiary_id != self.beneficiary_id:
                errors["prior_enrollment"] = _(
                    "Prior enrollment must belong to the same beneficiary."
                )
            elif prior.service_id != self.service_id:
                errors["prior_enrollment"] = _("Prior enrollment must use the same service.")
            elif not prior.is_terminal:
                errors["prior_enrollment"] = _("Prior enrollment must be terminal.")

        if self.beneficiary_id and self.service_id and not self.service.allow_same_service_overlap:
            overlap = ServiceEnrollment.objects.filter(
                beneficiary_id=self.beneficiary_id,
                service_id=self.service_id,
            ).exclude(pk=self.pk)
            if self.end_date:
                overlap = overlap.filter(
                    Q(start_date__isnull=True) | Q(start_date__lt=self.end_date)
                )
            if self.start_date:
                overlap = overlap.filter(
                    Q(end_date__isnull=True)
                    | Q(start_date__isnull=True)
                    | Q(end_date__gt=self.start_date)
                )
            if overlap.exists():
                errors["service"] = _(
                    "This beneficiary already has an overlapping enrollment for this service."
                )
        if errors:
            raise ValidationError(errors)


class EnrollmentStateEvent(ValidatedModel):
    class Kind(models.TextChoices):
        LEGACY_IMPORT = "legacy_import", _("Legacy Import")
        CREATED = "created", _("Created")
        ADMISSION = "admission", _("Admission")
        SUSPENSION = "suspension", _("Suspension")
        RESUMPTION = "resumption", _("Resumption")
        TRANSFER = "transfer", _("Transfer")
        COMPLETION = "completion", _("Completion")
        EXIT = "exit", _("Exit")
        CANCELLATION = "cancellation", _("Cancellation")
        RE_ENROLLMENT = "re_enrollment", _("Re-enrollment")

    enrollment = models.ForeignKey(
        ServiceEnrollment, on_delete=models.PROTECT, related_name="state_events"
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    previous_state = models.CharField(
        max_length=16, choices=ServiceEnrollment.Status.choices, blank=True
    )
    new_state = models.CharField(max_length=16, choices=ServiceEnrollment.Status.choices)
    effective_date = models.DateField(null=True, blank=True, db_index=True)
    reason = models.CharField(max_length=180, blank=True)
    notes = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enrollment_state_events",
    )

    class Meta:
        ordering = ["effective_date", "created_at", "id"]
        indexes = [models.Index(fields=["enrollment", "effective_date"])]

    def __str__(self) -> str:
        return f"{self.enrollment.episode_code} | {self.get_kind_display()}"

    def clean(self) -> None:
        self.reason = self.reason.strip()
        self.notes = self.notes.strip()
        if self.pk and EnrollmentStateEvent.objects.filter(pk=self.pk).exists():
            raise ValidationError(_("Enrollment history events are append-only."))


class EnrollmentCenterPlacement(ValidatedModel):
    enrollment = models.ForeignKey(
        ServiceEnrollment, on_delete=models.PROTECT, related_name="center_placements"
    )
    center = models.ForeignKey(
        Center, on_delete=models.PROTECT, related_name="enrollment_placements"
    )
    offering = models.ForeignKey(
        CenterServiceOffering,
        on_delete=models.PROTECT,
        related_name="enrollment_placements",
    )
    valid_from = models.DateField(null=True, blank=True, db_index=True)
    valid_to = models.DateField(null=True, blank=True, db_index=True)
    transfer_reason = models.CharField(max_length=180, blank=True)
    notes = models.TextField(blank=True)
    legacy_dates_incomplete = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ["valid_from", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True)
                | Q(valid_from__isnull=True)
                | Q(valid_to__gte=F("valid_from")),
                name="enrollment_placement_dates_ordered",
            )
        ]
        indexes = [
            models.Index(fields=["enrollment", "valid_from", "valid_to"]),
            models.Index(fields=["center", "valid_from", "valid_to"]),
        ]

    def __str__(self) -> str:
        return f"{self.enrollment.episode_code} at {self.center}"

    def clean(self) -> None:
        self.transfer_reason = self.transfer_reason.strip()
        self.notes = self.notes.strip()
        errors = {}
        if (
            self.valid_from
            and self.valid_to
            and self.valid_to <= self.valid_from
            and not (self.legacy_dates_incomplete and self.valid_to == self.valid_from)
        ):
            errors["valid_to"] = _("Valid to must be later than valid from.")
        if self.offering_id and self.enrollment_id:
            if self.offering.center_id != self.center_id:
                errors["offering"] = _("The offering does not belong to the selected center.")
            elif self.offering.service_id != self.enrollment.service_id:
                errors["offering"] = _("The offering does not provide the enrollment service.")
            if self.valid_from and not self.offering.is_effective(self.valid_from):
                errors["offering"] = _(
                    "The center offering is not effective on the placement start date."
                )
            if self.valid_to and self.offering.valid_to and self.valid_to > self.offering.valid_to:
                errors["valid_to"] = _("Placement extends beyond the center offering.")

        if self.enrollment_id:
            overlap = EnrollmentCenterPlacement.objects.filter(
                enrollment_id=self.enrollment_id
            ).exclude(pk=self.pk)
            if self.valid_to:
                overlap = overlap.filter(
                    Q(valid_from__isnull=True) | Q(valid_from__lt=self.valid_to)
                )
            if self.valid_from:
                overlap = overlap.filter(Q(valid_to__isnull=True) | Q(valid_to__gt=self.valid_from))
            if overlap.exists():
                errors["valid_from"] = _("Center placements cannot overlap.")
        if errors:
            raise ValidationError(errors)


class EnrollmentSpecialistAssignment(ValidatedModel):
    class Role(models.TextChoices):
        PRIMARY = "primary", _("Primary")
        SECONDARY = "secondary", _("Secondary")

    enrollment = models.ForeignKey(
        ServiceEnrollment, on_delete=models.PROTECT, related_name="specialist_assignments"
    )
    specialist = models.ForeignKey(
        SpecialistProfile,
        on_delete=models.PROTECT,
        related_name="enrollment_assignments",
    )
    assignment_role = models.CharField(max_length=16, choices=Role.choices, default=Role.PRIMARY)
    valid_from = models.DateField(null=True, blank=True, db_index=True)
    valid_to = models.DateField(null=True, blank=True, db_index=True)
    legacy_dates_incomplete = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ["assignment_role", "specialist__staff_profile__user__last_name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True)
                | Q(valid_from__isnull=True)
                | Q(valid_to__gte=F("valid_from")),
                name="enrollment_assignment_dates_ordered",
            )
        ]
        indexes = [
            models.Index(fields=["enrollment", "valid_from", "valid_to"]),
            models.Index(fields=["specialist", "valid_from", "valid_to"]),
        ]

    def __str__(self) -> str:
        return f"{self.specialist} | {self.enrollment.episode_code}"

    def is_effective(self, on_date: date) -> bool:
        return (
            self.valid_from is not None
            and self.valid_from <= on_date
            and (self.valid_to is None or on_date < self.valid_to)
        )

    @property
    def effective_status(self) -> str:
        on_date = timezone.localdate()
        if self.valid_to and on_date >= self.valid_to:
            return "expired"
        if self.valid_from is None:
            return "unknown"
        if on_date < self.valid_from:
            return "future"
        return "current"

    def clean(self) -> None:
        errors = {}
        if self.valid_from is None and not self.legacy_dates_incomplete:
            errors["valid_from"] = _("Valid from is required for a new specialist assignment.")
        if (
            self.valid_from
            and self.valid_to
            and self.valid_to <= self.valid_from
            and not (self.legacy_dates_incomplete and self.valid_to == self.valid_from)
        ):
            errors["valid_to"] = _("Valid to must be later than valid from.")
        if self.enrollment_id and self.specialist_id:
            placements = self.enrollment.center_placements.all()
            if self.valid_to:
                placements = placements.filter(
                    Q(valid_from__isnull=True) | Q(valid_from__lt=self.valid_to)
                )
            if self.valid_from:
                placements = placements.filter(
                    Q(valid_to__isnull=True) | Q(valid_to__gt=self.valid_from)
                )
            placement_centers = set(placements.values_list("center_id", flat=True))
            specialist_centers = set(
                self.specialist.center_assignments.values_list("center_id", flat=True)
            )
            if placement_centers and not placement_centers.issubset(specialist_centers):
                errors["specialist"] = _(
                    "The specialist is not assigned to every center in this assignment period."
                )
        if errors:
            raise ValidationError(errors)


class BeneficiaryDiagnosis(ValidatedModel):
    class VerificationStatus(models.TextChoices):
        REPORTED = "reported", _("Reported")
        UNVERIFIED = "unverified", _("Unverified")
        VERIFIED = "verified", _("Verified")

    beneficiary = models.ForeignKey(Beneficiary, on_delete=models.PROTECT, related_name="diagnoses")
    definition = models.ForeignKey(
        DiagnosisDefinition, on_delete=models.PROTECT, related_name="beneficiary_values"
    )
    enrollment = models.ForeignKey(
        ServiceEnrollment,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="diagnoses",
    )
    recorded_on = models.DateField(default=timezone.localdate)
    valid_from = models.DateField(null=True, blank=True, db_index=True)
    valid_to = models.DateField(null=True, blank=True, db_index=True)
    verification_status = models.CharField(
        max_length=16,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
    )
    visible_to_specialists = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_beneficiary_diagnoses",
    )

    class Meta:
        ordering = ["-valid_from", "definition__code"]
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True)
                | Q(valid_from__isnull=True)
                | Q(valid_to__gt=F("valid_from")),
                name="beneficiary_diagnosis_dates_ordered",
            )
        ]
        indexes = [models.Index(fields=["beneficiary", "valid_from", "valid_to"])]

    def __str__(self) -> str:
        return str(self.definition)

    def clean(self) -> None:
        self.notes = self.notes.strip()
        errors = {}
        if self.valid_from and self.valid_to and self.valid_to <= self.valid_from:
            errors["valid_to"] = _("Valid to must be later than valid from.")
        if self.enrollment_id and self.enrollment.beneficiary_id != self.beneficiary_id:
            errors["enrollment"] = _("Enrollment must belong to this beneficiary.")
        if (
            self.definition_id
            and self.valid_from
            and not self.definition.is_effective(self.valid_from)
        ):
            errors["definition"] = _("Diagnosis code is not effective on the start date.")
        if errors:
            raise ValidationError(errors)


class BeneficiarySocialStatus(ValidatedModel):
    class VerificationStatus(models.TextChoices):
        REPORTED = "reported", _("Reported")
        UNVERIFIED = "unverified", _("Unverified")
        VERIFIED = "verified", _("Verified")

    beneficiary = models.ForeignKey(
        Beneficiary, on_delete=models.PROTECT, related_name="social_statuses"
    )
    definition = models.ForeignKey(
        SocialStatusDefinition,
        on_delete=models.PROTECT,
        related_name="beneficiary_values",
    )
    enrollment = models.ForeignKey(
        ServiceEnrollment,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="social_statuses",
    )
    recorded_on = models.DateField(default=timezone.localdate)
    valid_from = models.DateField(null=True, blank=True, db_index=True)
    valid_to = models.DateField(null=True, blank=True, db_index=True)
    verification_status = models.CharField(
        max_length=16,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
    )
    visible_to_specialists = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_beneficiary_social_statuses",
    )

    class Meta:
        ordering = ["-valid_from", "definition__code"]
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True)
                | Q(valid_from__isnull=True)
                | Q(valid_to__gt=F("valid_from")),
                name="beneficiary_social_status_dates_ordered",
            )
        ]
        indexes = [models.Index(fields=["beneficiary", "valid_from", "valid_to"])]

    def __str__(self) -> str:
        return str(self.definition)

    def clean(self) -> None:
        self.notes = self.notes.strip()
        errors = {}
        if self.valid_from and self.valid_to and self.valid_to <= self.valid_from:
            errors["valid_to"] = _("Valid to must be later than valid from.")
        if self.enrollment_id and self.enrollment.beneficiary_id != self.beneficiary_id:
            errors["enrollment"] = _("Enrollment must belong to this beneficiary.")
        if (
            self.definition_id
            and self.valid_from
            and not self.definition.is_effective(self.valid_from)
        ):
            errors["definition"] = _("Social status is not effective on the start date.")
        if errors:
            raise ValidationError(errors)


class BeneficiarySpecialistAssignment(ValidatedModel):
    class Role(models.TextChoices):
        PRIMARY = "primary", _("Primary")
        SECONDARY = "secondary", _("Secondary")

    beneficiary = models.ForeignKey(
        Beneficiary, on_delete=models.CASCADE, related_name="specialist_assignments"
    )
    specialist = models.ForeignKey(
        SpecialistProfile, on_delete=models.PROTECT, related_name="beneficiary_assignments"
    )
    assignment_role = models.CharField(max_length=16, choices=Role.choices, default=Role.PRIMARY)
    from_date = models.DateField(null=True, blank=True)
    to_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["assignment_role", "specialist__staff_profile__user__last_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["beneficiary", "specialist"],
                name="unique_beneficiary_specialist_assignment",
            ),
            models.CheckConstraint(
                condition=Q(to_date__isnull=True)
                | Q(from_date__isnull=True)
                | Q(to_date__gte=F("from_date")),
                name="beneficiary_assignment_dates_ordered",
            ),
        ]
        indexes = [models.Index(fields=["specialist", "beneficiary"])]

    def is_effective(self, on_date: date) -> bool:
        return (
            self.from_date is not None
            and self.from_date <= on_date
            and (self.to_date is None or on_date < self.to_date)
        )

    @property
    def effective_status(self) -> str:
        on_date = timezone.localdate()
        if self.to_date and on_date >= self.to_date:
            return "expired"
        if self.from_date is None:
            return "unknown"
        if on_date < self.from_date:
            return "future"
        return "current"

    def clean(self) -> None:
        if self.to_date and self.from_date and self.to_date <= self.from_date:
            raise ValidationError({"to_date": _("To date must be later than from date.")})
        if self.beneficiary_id and self.specialist_id:
            available = self.specialist.center_assignments.filter(
                center_id=self.beneficiary.center_id
            ).exists()
            if not available:
                raise ValidationError(
                    {"specialist": _("The specialist is not assigned to this center.")}
                )


def _infer_single_enrollment(beneficiary_id):
    if not beneficiary_id:
        return None
    enrollments = ServiceEnrollment.objects.filter(beneficiary_id=beneficiary_id).order_by(
        "created_at"
    )
    if enrollments.count() == 1:
        return enrollments.first()
    return None


class ParticipationFormat(models.TextChoices):
    INDIVIDUAL = "individual", _("Individual")
    GROUP = "group", _("Group")


class EnrollmentServiceSchedule(ValidatedModel):
    enrollment = models.ForeignKey(
        ServiceEnrollment,
        on_delete=models.PROTECT,
        related_name="service_schedules",
    )
    schedule_month = models.DateField(db_index=True)
    activity = models.ForeignKey(
        ServiceActivityDefinition,
        on_delete=models.PROTECT,
        related_name="service_schedules",
    )
    delivery_location = models.ForeignKey(
        VisitLocationDefinition,
        on_delete=models.PROTECT,
        related_name="service_schedules",
    )
    participation_format = models.CharField(
        max_length=16,
        choices=ParticipationFormat.choices,
        default=ParticipationFormat.INDIVIDUAL,
    )
    planned_visits = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    planned_units = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(0)],
    )
    expected_participants = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-schedule_month", "enrollment__episode_code", "activity__reporting_order"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "enrollment",
                    "schedule_month",
                    "activity",
                    "delivery_location",
                    "participation_format",
                ],
                name="unique_enrollment_month_service_schedule",
            ),
            models.CheckConstraint(
                condition=Q(schedule_month__day=1),
                name="service_schedule_month_is_first_day",
            ),
            models.CheckConstraint(
                condition=Q(planned_visits__gt=0),
                name="service_schedule_visits_positive",
            ),
            models.CheckConstraint(
                condition=Q(planned_units__gte=0),
                name="service_schedule_units_nonnegative",
            ),
        ]
        indexes = [
            models.Index(fields=["enrollment", "schedule_month"]),
            models.Index(fields=["activity", "delivery_location", "schedule_month"]),
        ]

    def __str__(self) -> str:
        return f"{self.enrollment.episode_code} | {self.schedule_month:%Y-%m} | {self.activity}"

    def clean(self) -> None:
        self.notes = self.notes.strip()
        errors = {}
        if self.schedule_month:
            self.schedule_month = self.schedule_month.replace(day=1)
        if self.enrollment_id and self.schedule_month:
            if self.enrollment.status_on(self.schedule_month) not in {
                ServiceEnrollment.Status.PENDING,
                ServiceEnrollment.Status.ACTIVE,
            }:
                errors["schedule_month"] = _(
                    "The enrollment is not open for service in this schedule month."
                )
            if not self.enrollment.placement_on(self.schedule_month):
                errors["enrollment"] = _(
                    "Enrollment has no center placement in this schedule month."
                )
            has_specialist = self.enrollment.specialist_assignments.filter(
                Q(valid_to__isnull=True) | Q(valid_to__gt=self.schedule_month),
                valid_from__lte=self.schedule_month,
            ).exists()
            if not has_specialist:
                errors["enrollment"] = _(
                    "The enrollment has no specialist assignment effective on the selected date."
                )
        if self.activity_id and self.enrollment_id and self.schedule_month:
            if not self.activity.is_available_for(self.enrollment.service_id, self.schedule_month):
                errors["activity"] = _(
                    "The activity is not available for this service and schedule month."
                )
        if (
            self.delivery_location_id
            and self.schedule_month
            and not self.delivery_location.is_effective(self.schedule_month)
        ):
            errors["delivery_location"] = _(
                "The delivery location is not effective in this schedule month."
            )
        if self.participation_format == ParticipationFormat.INDIVIDUAL:
            self.expected_participants = 1
        elif self.expected_participants < 2:
            errors["expected_participants"] = _(
                "Group schedules require at least two expected participants."
            )
        if errors:
            raise ValidationError(errors)


class ServiceVisit(ValidatedModel):
    class LegacyVisitType(models.TextChoices):
        CENTER = "center_visit", _("Center Visit")
        HOME = "home_visit", _("Home Visit")
        SCHOOL = "school_visit", _("School Visit")
        HOSPITAL = "hospital_visit", _("Hospital Visit")
        COMMUNITY = "community_outreach", _("Community Outreach")
        REMOTE = "remote_session", _("Remote Session")
        GROUP = "group_session", _("Group Session")
        CONFERENCE = "case_conference", _("Case Conference")
        OTHER = "other", _("Other")

    VisitType = LegacyVisitType

    class Status(models.TextChoices):
        PLANNED = "planned", _("Planned")
        COMPLETED = "completed", _("Completed")
        NO_SHOW = "no_show", _("No Show")
        CANCELLED = "cancelled", _("Cancelled")

    enrollment = models.ForeignKey(
        ServiceEnrollment,
        on_delete=models.PROTECT,
        related_name="visits",
    )
    beneficiary = models.ForeignKey(Beneficiary, on_delete=models.PROTECT, related_name="visits")
    center = models.ForeignKey(Center, on_delete=models.PROTECT, related_name="service_visits")
    specialist = models.ForeignKey(
        SpecialistProfile, on_delete=models.PROTECT, related_name="service_visits"
    )
    visit_date = models.DateField(db_index=True)
    visit_month = models.DateField(editable=False, db_index=True)
    activity = models.ForeignKey(
        ServiceActivityDefinition,
        on_delete=models.PROTECT,
        related_name="service_visits",
    )
    delivery_location = models.ForeignKey(
        VisitLocationDefinition,
        on_delete=models.PROTECT,
        related_name="service_visits",
    )
    participation_format = models.CharField(
        max_length=16,
        choices=ParticipationFormat.choices,
        default=ParticipationFormat.INDIVIDUAL,
        db_index=True,
    )
    legacy_visit_type = models.CharField(
        max_length=32,
        choices=LegacyVisitType.choices,
        blank=True,
        editable=False,
        db_index=True,
    )
    status = models.CharField(max_length=16, choices=Status.choices, db_index=True)
    service_units = models.DecimalField(
        max_digits=8, decimal_places=2, default=1, validators=[MinValueValidator(0)]
    )
    duration_minutes = models.PositiveIntegerField(default=0)
    participants = models.PositiveIntegerField(default=1)
    cancellation_reason = models.CharField(max_length=240, blank=True)
    notes = models.TextField(blank=True)
    goals_worked_on = models.ManyToManyField(
        "IndividualPlanGoal",
        related_name="service_visits",
        blank=True,
        help_text=_("Optional goals addressed during this visit."),
    )

    class Meta:
        ordering = ["-visit_date", "-created_at"]
        indexes = [
            models.Index(fields=["center", "visit_date", "status"]),
            models.Index(fields=["specialist", "visit_month", "status"]),
            models.Index(fields=["beneficiary", "visit_date"]),
            models.Index(fields=["activity", "delivery_location", "visit_month", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(service_units__gte=0), name="visit_units_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(duration_minutes__gte=0), name="visit_duration_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(visit_month__day=1), name="visit_month_is_first_day"
            ),
            models.CheckConstraint(
                condition=~Q(status="cancelled") | Q(service_units=0),
                name="cancelled_visit_has_zero_units",
            ),
            models.CheckConstraint(
                condition=~Q(status__in=["planned", "no_show"]) | Q(service_units=0),
                name="undelivered_visit_has_zero_units",
            ),
            models.CheckConstraint(
                condition=Q(participants__gt=0),
                name="visit_participants_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.beneficiary.beneficiary_code} | {self.visit_date}"

    @property
    def month_label(self) -> str:
        return self.visit_month.strftime("%Y-%m")

    def clean(self) -> None:
        self.notes = self.notes.strip()
        self.cancellation_reason = self.cancellation_reason.strip()
        errors = {}
        if not self.enrollment_id:
            inferred = _infer_single_enrollment(self.beneficiary_id)
            if inferred:
                self.enrollment = inferred
        if self.enrollment_id:
            if self.beneficiary_id and self.beneficiary_id != self.enrollment.beneficiary_id:
                errors["beneficiary"] = _("Beneficiary must match the selected enrollment.")
            self.beneficiary_id = self.enrollment.beneficiary_id
            placement = self.enrollment.placement_on(self.visit_date) if self.visit_date else None
            if self.visit_date and not placement:
                errors["enrollment"] = _("Enrollment has no center placement on the visit date.")
            if placement:
                if self.center_id and self.center_id != placement.center_id:
                    errors["center"] = _("Service visit center must match enrollment placement.")
                self.center_id = placement.center_id
        if self.visit_date:
            self.visit_month = date(self.visit_date.year, self.visit_date.month, 1)
        if self.status != self.Status.COMPLETED:
            self.service_units = 0
        if self.status == self.Status.CANCELLED:
            if not self.cancellation_reason:
                errors["cancellation_reason"] = _(
                    "A cancellation reason is required for a cancelled visit."
                )
        elif self.cancellation_reason:
            errors["cancellation_reason"] = _(
                "Cancellation reason is only allowed for cancelled visits."
            )
        if self.status == self.Status.COMPLETED:
            if self.visit_date and self.visit_date > timezone.localdate():
                errors["visit_date"] = _("A completed visit cannot be dated in the future.")
            if self.service_units <= 0:
                errors["service_units"] = _("A completed visit requires positive service units.")
            if self.duration_minutes <= 0:
                errors["duration_minutes"] = _("A completed visit requires a duration.")
        if self.status == self.Status.NO_SHOW and self.visit_date:
            if self.visit_date > timezone.localdate():
                errors["visit_date"] = _("A no-show visit cannot be dated in the future.")
        if self.enrollment_id and self.visit_date:
            allowed_states = {ServiceEnrollment.Status.ACTIVE}
            if self.status == self.Status.PLANNED:
                allowed_states.add(ServiceEnrollment.Status.PENDING)
            if self.enrollment.status_on(self.visit_date) not in allowed_states:
                errors["visit_date"] = _(
                    "The enrollment is not open for this visit status on the selected date."
                )
        if self.activity_id and self.enrollment_id and self.visit_date:
            if not self.activity.is_available_for(self.enrollment.service_id, self.visit_date):
                errors["activity"] = _(
                    "The activity is not available for this enrollment service and date."
                )
        if (
            self.delivery_location_id
            and self.visit_date
            and not self.delivery_location.is_effective(self.visit_date)
        ):
            errors["delivery_location"] = _(
                "The delivery location is not effective on the visit date."
            )
        if self.participation_format == ParticipationFormat.INDIVIDUAL:
            self.participants = 1
        elif self.participants < 2:
            errors["participants"] = _("Group visits require at least two participants.")
        if self.activity_id and self.activity.code == "OTHER" and not self.notes:
            errors["notes"] = _("Notes are required when the activity is Other.")
        if self.enrollment_id and self.specialist_id and self.visit_date:
            assigned = (
                EnrollmentSpecialistAssignment.objects.filter(
                    enrollment_id=self.enrollment_id,
                    specialist_id=self.specialist_id,
                )
                .filter(
                    Q(valid_to__isnull=True) | Q(valid_to__gt=self.visit_date),
                    valid_from__lte=self.visit_date,
                )
                .exists()
            )
            if not assigned:
                errors["specialist"] = _(
                    "The specialist is not assigned to this beneficiary enrollment."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.enrollment_id:
            self.enrollment = _infer_single_enrollment(self.beneficiary_id)
        return super().save(*args, **kwargs)


class ServiceVisitCorrection(ValidatedModel):
    visit = models.ForeignKey(
        ServiceVisit,
        on_delete=models.PROTECT,
        related_name="corrections",
    )
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="service_visit_corrections",
    )
    reason = models.CharField(max_length=240)
    before_values = models.JSONField()
    after_values = models.JSONField()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["visit", "created_at"])]

    def __str__(self) -> str:
        return f"{self.visit} | {self.created_at:%Y-%m-%d %H:%M}"

    def clean(self) -> None:
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValidationError({"reason": _("A correction reason is required.")})
        if self.pk and ServiceVisitCorrection.objects.filter(pk=self.pk).exists():
            raise ValidationError(_("Visit correction records are append-only."))

    def delete(self, *args, **kwargs):
        raise TypeError("Visit correction records are append-only.")


class AssessmentInstrument(ValidatedModel):
    class Identifier(models.TextChoices):
        BARTHEL = "barthel", _("Barthel")
        AEPS_OLD = "aeps_old", _("AEPS (Old)")
        AEPS_NEW = "aeps_new", _("AEPS (New)")
        ICF = "icf", _("ICF-Based")
        OTHER = "other", _("Other")

    code = models.CharField(max_length=48, unique=True)
    name = models.CharField(max_length=180)
    identifier = models.CharField(
        max_length=16,
        choices=Identifier.choices,
        default=Identifier.OTHER,
        db_index=True,
    )
    lineage_code = models.CharField(
        max_length=48,
        help_text=_("Assessments may be chained only within the same lineage code."),
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name", "code"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"

    def clean(self) -> None:
        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        self.lineage_code = self.lineage_code.strip().upper()
        self.description = self.description.strip()
        if not self.code:
            raise ValidationError({"code": _("Instrument code is required.")})
        if not self.lineage_code:
            raise ValidationError({"lineage_code": _("Instrument lineage is required.")})
        if self.pk:
            current = type(self).objects.filter(pk=self.pk).first()
            if current and current.template_versions.exists():
                changed = any(
                    getattr(current, field) != getattr(self, field)
                    for field in ("code", "identifier", "lineage_code")
                )
                if changed:
                    raise ValidationError(
                        _("Instrument identity and lineage cannot change after a version exists.")
                    )

    def delete(self, *args, **kwargs):
        if self.template_versions.exists():
            raise models.ProtectedError(
                _("An instrument with template versions cannot be deleted."),
                {self},
            )
        return super().delete(*args, **kwargs)


class AssessmentTemplateVersion(ValidatedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")
        WITHDRAWN = "withdrawn", _("Withdrawn")

    class ScoringMethod(models.TextChoices):
        SUM = "sum", _("Sum")
        AVERAGE = "average", _("Average")
        NONE = "none", _("No total")

    instrument = models.ForeignKey(
        AssessmentInstrument,
        on_delete=models.PROTECT,
        related_name="template_versions",
    )
    version = models.CharField(max_length=48)
    name = models.CharField(max_length=180)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    applicable_services = models.ManyToManyField(
        ServiceDefinition,
        related_name="assessment_template_versions",
        blank=True,
        help_text=_("Leave empty to allow this version for every service."),
    )
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    scoring_method = models.CharField(
        max_length=16,
        choices=ScoringMethod.choices,
        default=ScoringMethod.SUM,
    )
    score_minimum = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    score_maximum = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    score_increment = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1"),
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    comparison_group = models.CharField(
        max_length=48,
        blank=True,
        help_text=_("Different versions are comparable only when this explicit group is the same."),
    )
    is_legacy = models.BooleanField(default=False, db_index=True)
    publication_notes = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="published_assessment_templates",
        editable=False,
    )

    class Meta:
        ordering = ["instrument__name", "version"]
        constraints = [
            models.UniqueConstraint(
                fields=["instrument", "version"],
                name="unique_assessment_instrument_version",
            )
        ]

    def __str__(self) -> str:
        return f"{self.instrument.name} {self.version}"

    @property
    def is_locked(self) -> bool:
        return self.status != self.Status.DRAFT or (
            self.pk is not None and self.assessments.exists()
        )

    @property
    def fields(self):
        return AssessmentTemplateField.objects.filter(section__template_version=self)

    def clean(self) -> None:
        self.version = self.version.strip()
        self.name = self.name.strip()
        self.comparison_group = self.comparison_group.strip().upper()
        self.publication_notes = self.publication_notes.strip()
        errors = {}
        if not self.version:
            errors["version"] = _("Template version is required.")
        if self.effective_from and self.effective_to and self.effective_to <= self.effective_from:
            errors["effective_to"] = _("Effective to must be later than effective from.")
        if (
            self.score_minimum is not None
            and self.score_maximum is not None
            and self.score_maximum < self.score_minimum
        ):
            errors["score_maximum"] = _("Score maximum cannot be below score minimum.")
        if errors:
            raise ValidationError(errors)
        if self.pk:
            current = type(self).objects.filter(pk=self.pk).first()
            if current and current.is_locked:
                fields = (
                    "instrument_id",
                    "version",
                    "name",
                    "effective_from",
                    "effective_to",
                    "scoring_method",
                    "score_minimum",
                    "score_maximum",
                    "score_increment",
                    "comparison_group",
                    "is_legacy",
                    "publication_notes",
                )
                if any(getattr(current, field) != getattr(self, field) for field in fields):
                    raise ValidationError(_("Published or used template versions are immutable."))
                if current.status == self.Status.WITHDRAWN and self.status != current.status:
                    raise ValidationError(_("A withdrawn template version cannot be republished."))
                if current.status == self.Status.PUBLISHED and self.status == self.Status.DRAFT:
                    raise ValidationError(_("A published template version cannot return to draft."))

    def validate_for_publication(self) -> None:
        self.full_clean()
        if not self.pk:
            raise ValidationError(_("Save the draft before publication."))
        template_fields = list(self.fields.select_related("section").all())
        if not template_fields:
            raise ValidationError(_("A template must contain at least one response field."))
        for template_field in template_fields:
            template_field.full_clean()
        if self.instrument.identifier == AssessmentInstrument.Identifier.BARTHEL:
            self._validate_barthel_bands()

    def _validate_barthel_bands(self) -> None:
        if self.score_minimum is None or self.score_maximum is None:
            raise ValidationError(
                _("Barthel templates require an explicit minimum and maximum score.")
            )
        bands = list(self.score_bands.order_by("lower_bound", "upper_bound"))
        if not bands:
            raise ValidationError(_("Barthel templates require classification bands."))
        expected_lower = self.score_minimum
        for band in bands:
            band.full_clean()
            if band.lower_bound != expected_lower:
                if band.lower_bound < expected_lower:
                    raise ValidationError(
                        _("Barthel classification bands overlap or duplicate a boundary.")
                    )
                raise ValidationError(_("Barthel classification bands contain a gap."))
            expected_lower = band.upper_bound + self.score_increment
        if bands[-1].upper_bound != self.score_maximum:
            raise ValidationError(
                _("Barthel classification bands must end at the template maximum score.")
            )

    def publish(self, *, actor=None) -> None:
        if self.status != self.Status.DRAFT:
            raise ValidationError(_("Only a draft template version can be published."))
        self.validate_for_publication()
        self.status = self.Status.PUBLISHED
        self.published_at = timezone.now()
        self.published_by = actor
        super().save()
        if actor is not None:
            from apps.audit.services import record_event

            record_event(
                actor=actor,
                event_type="update",
                target_type="AssessmentTemplateVersion",
                target_id=self.pk,
                metadata={
                    "instrument_code": self.instrument.code,
                    "template_version_id": str(self.pk),
                },
            )

    def withdraw(self) -> None:
        if self.status != self.Status.PUBLISHED:
            raise ValidationError(_("Only a published template version can be withdrawn."))
        type(self).objects.filter(pk=self.pk).update(
            status=self.Status.WITHDRAWN,
            updated_at=timezone.now(),
        )
        self.status = self.Status.WITHDRAWN

    def is_available_for(self, service_id, on_date: date) -> bool:
        if self.status != self.Status.PUBLISHED:
            return False
        if self.effective_from and on_date < self.effective_from:
            return False
        if self.effective_to and on_date >= self.effective_to:
            return False
        configured_services = self.applicable_services.all()
        return (
            not configured_services.exists() or configured_services.filter(pk=service_id).exists()
        )

    def save(self, *args, **kwargs):
        current_status = (
            type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if self.pk
            else None
        )
        if self.status == self.Status.PUBLISHED and current_status != self.Status.PUBLISHED:
            self.validate_for_publication()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_locked:
            raise models.ProtectedError(
                _("Published or used template versions cannot be deleted."),
                {self},
            )
        return super().delete(*args, **kwargs)


class AssessmentTemplateSection(ValidatedModel):
    template_version = models.ForeignKey(
        AssessmentTemplateVersion,
        on_delete=models.CASCADE,
        related_name="sections",
    )
    code = models.CharField(max_length=48)
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["template_version", "code"],
                name="unique_assessment_template_section_code",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        self.description = self.description.strip()
        if self.template_version_id and self.template_version.is_locked:
            raise ValidationError(_("Published or used template versions are immutable."))

    def delete(self, *args, **kwargs):
        if self.template_version.is_locked:
            raise models.ProtectedError(
                _("Published or used template sections cannot be deleted."),
                {self},
            )
        return super().delete(*args, **kwargs)


class AssessmentTemplateField(ValidatedModel):
    class ResponseType(models.TextChoices):
        NUMERIC_SCORE = "numeric", _("Numeric score")
        PERCENTAGE = "percentage", _("Percentage")
        ASSESSED_NOT_ASSESSED = "assessed_state", _("Assessed or not assessed")
        CHOICE = "choice", _("Choice")
        TEXT = "text", _("Text")
        NOT_APPLICABLE = "not_applicable", _("Not applicable")

    class DelayedOperator(models.TextChoices):
        LESS_THAN = "lt", _("Below threshold")
        LESS_THAN_OR_EQUAL = "lte", _("At or below threshold")
        GREATER_THAN = "gt", _("Above threshold")
        GREATER_THAN_OR_EQUAL = "gte", _("At or above threshold")

    section = models.ForeignKey(
        AssessmentTemplateSection,
        on_delete=models.CASCADE,
        related_name="fields",
    )
    code = models.CharField(max_length=64)
    label = models.CharField(max_length=240)
    help_text = models.TextField(blank=True)
    response_type = models.CharField(max_length=24, choices=ResponseType.choices)
    display_order = models.PositiveIntegerField(default=0)
    is_required = models.BooleanField(default=True)
    minimum_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    maximum_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    value_increment = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1"),
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    allowed_choices = models.JSONField(default=list, blank=True)
    allow_not_assessed = models.BooleanField(default=False)
    allow_not_applicable = models.BooleanField(default=False)
    include_in_total = models.BooleanField(default=False)
    is_delayed_domain = models.BooleanField(default=False)
    delayed_threshold = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    delayed_operator = models.CharField(
        max_length=4,
        choices=DelayedOperator.choices,
        default=DelayedOperator.LESS_THAN,
    )

    class Meta:
        ordering = ["section__display_order", "display_order", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["section", "code"],
                name="unique_assessment_template_field_code",
            )
        ]

    def __str__(self) -> str:
        return self.label

    @property
    def template_version(self):
        return self.section.template_version

    def clean(self) -> None:
        self.code = self.code.strip().upper()
        self.label = self.label.strip()
        self.help_text = self.help_text.strip()
        errors = {}
        if self.section_id and self.section.template_version.is_locked:
            errors["section"] = _("Published or used template versions are immutable.")
        if (
            self.section_id
            and type(self)
            .objects.filter(
                section__template_version_id=self.section.template_version_id,
                code=self.code,
            )
            .exclude(pk=self.pk)
            .exists()
        ):
            errors["code"] = _("Field codes must be unique within a template version.")
        numeric_types = {self.ResponseType.NUMERIC_SCORE, self.ResponseType.PERCENTAGE}
        if self.response_type == self.ResponseType.PERCENTAGE:
            if self.minimum_value is None:
                self.minimum_value = Decimal("0")
            if self.maximum_value is None:
                self.maximum_value = Decimal("100")
        if self.response_type in numeric_types:
            if (
                self.minimum_value is not None
                and self.maximum_value is not None
                and self.maximum_value < self.minimum_value
            ):
                errors["maximum_value"] = _("Maximum value cannot be below minimum value.")
        elif self.minimum_value is not None or self.maximum_value is not None:
            errors["minimum_value"] = _("Only numeric responses may define numeric ranges.")
        choices = self.allowed_choices
        if self.response_type == self.ResponseType.CHOICE:
            if (
                not isinstance(choices, list)
                or not choices
                or any(not isinstance(choice, str) or not choice.strip() for choice in choices)
            ):
                errors["allowed_choices"] = _("Choice responses require a non-empty list.")
            elif len(set(choices)) != len(choices):
                errors["allowed_choices"] = _("Choice response values must be unique.")
        elif choices:
            errors["allowed_choices"] = _("Only choice responses may define choices.")
        if self.is_delayed_domain:
            if self.response_type not in numeric_types:
                errors["is_delayed_domain"] = _("Delayed domains require a numeric response.")
            if self.delayed_threshold is None:
                errors["delayed_threshold"] = _("Delayed domains require a threshold.")
        elif self.delayed_threshold is not None:
            errors["delayed_threshold"] = _("Only delayed domains may define a threshold.")
        if errors:
            raise ValidationError(errors)

    def delete(self, *args, **kwargs):
        if self.section.template_version.is_locked:
            raise models.ProtectedError(
                _("Published or used template fields cannot be deleted."),
                {self},
            )
        return super().delete(*args, **kwargs)


class AssessmentScoreBand(ValidatedModel):
    template_version = models.ForeignKey(
        AssessmentTemplateVersion,
        on_delete=models.CASCADE,
        related_name="score_bands",
    )
    code = models.CharField(max_length=48)
    label = models.CharField(max_length=180)
    lower_bound = models.DecimalField(max_digits=10, decimal_places=2)
    upper_bound = models.DecimalField(max_digits=10, decimal_places=2)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "lower_bound"]
        constraints = [
            models.UniqueConstraint(
                fields=["template_version", "code"],
                name="unique_assessment_score_band_code",
            )
        ]

    def __str__(self) -> str:
        return self.label

    def clean(self) -> None:
        self.code = self.code.strip().upper()
        self.label = self.label.strip()
        errors = {}
        if self.template_version_id and self.template_version.is_locked:
            errors["template_version"] = _("Published or used template versions are immutable.")
        if self.upper_bound < self.lower_bound:
            errors["upper_bound"] = _("Band upper bound cannot be below its lower bound.")
        if errors:
            raise ValidationError(errors)

    def delete(self, *args, **kwargs):
        if self.template_version.is_locked:
            raise models.ProtectedError(
                _("Published or used score bands cannot be deleted."),
                {self},
            )
        return super().delete(*args, **kwargs)


class Assessment(ValidatedModel):
    class AssessmentType(models.TextChoices):
        INITIAL = "initial", _("Initial")
        REPEATED = "repeated", _("Repeated")
        FINAL = "final", _("Final")

    class ScoringTool(models.TextChoices):
        BARTHEL = "barthel", _("Barthel")
        AEPS_OLD = "aeps_old", _("AEPS (Old)")
        AEPS_NEW = "aeps_new", _("AEPS (New)")
        ICF = "icf", _("ICF-Based")
        OTHER = "other", _("Other")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        COMPLETED = "completed", _("Completed")
        SUPERSEDED = "superseded", _("Superseded by correction")

    enrollment = models.ForeignKey(
        ServiceEnrollment,
        on_delete=models.PROTECT,
        related_name="assessments",
    )
    beneficiary = models.ForeignKey(
        Beneficiary, on_delete=models.PROTECT, related_name="assessments"
    )
    center = models.ForeignKey(Center, on_delete=models.PROTECT, related_name="assessments")
    specialist = models.ForeignKey(
        SpecialistProfile, on_delete=models.PROTECT, related_name="assessments"
    )
    assessment_date = models.DateField(db_index=True)
    assessment_type = models.CharField(max_length=16, choices=AssessmentType.choices, db_index=True)
    previous_assessment = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="next_assessments",
    )
    assessment_cycle_number = models.PositiveIntegerField(default=1, editable=False)
    chain_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    chain_number = models.PositiveIntegerField(default=1, editable=False)
    template_version = models.ForeignKey(
        AssessmentTemplateVersion,
        on_delete=models.PROTECT,
        related_name="assessments",
    )
    scoring_tool = models.CharField(max_length=16, choices=ScoringTool.choices)
    total_score = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        editable=False,
    )
    derived_classification = models.CharField(max_length=180, blank=True, editable=False)
    delayed_domain_count = models.PositiveIntegerField(default=0, editable=False)
    scoring_rule_version = models.CharField(max_length=48, blank=True, editable=False)
    calculation_trace = models.JSONField(default=dict, blank=True, editable=False)
    calculated_at = models.DateTimeField(null=True, blank=True, editable=False)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        editable=False,
    )
    revision_of = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="corrections",
        editable=False,
    )
    revision_number = models.PositiveIntegerField(default=1, editable=False)
    correction_reason = models.TextField(blank=True, editable=False)
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assessment_corrections",
        editable=False,
    )
    responsible_specialists = models.ManyToManyField(
        SpecialistProfile,
        through="AssessmentResponsibleSpecialist",
        related_name="responsible_assessments",
    )
    service_schedule_count = models.PositiveIntegerField(default=0)
    progress_summary = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    next_review_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-assessment_date", "-created_at"]
        indexes = [
            models.Index(fields=["center", "assessment_date", "assessment_type"]),
            models.Index(fields=["specialist", "assessment_date"]),
            models.Index(fields=["beneficiary", "assessment_date"]),
            models.Index(fields=["enrollment", "chain_id", "assessment_cycle_number"]),
            models.Index(fields=["template_version", "assessment_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(assessment_type="initial", previous_assessment__isnull=True)
                    | Q(
                        assessment_type__in=("repeated", "final"),
                        previous_assessment__isnull=False,
                    )
                ),
                name="assessment_type_previous_consistent",
            ),
            models.CheckConstraint(
                condition=Q(next_review_date__isnull=True)
                | Q(next_review_date__gte=F("assessment_date")),
                name="assessment_review_date_ordered",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.beneficiary.beneficiary_code} | {self.get_assessment_type_display()}"

    def clean(self) -> None:
        self.progress_summary = self.progress_summary.strip()
        self.recommendations = self.recommendations.strip()
        self.notes = self.notes.strip()
        self.correction_reason = self.correction_reason.strip()
        if not self.enrollment_id:
            inferred = _infer_single_enrollment(self.beneficiary_id)
            if inferred:
                self.enrollment = inferred
        if self.enrollment_id:
            if self.beneficiary_id and self.beneficiary_id != self.enrollment.beneficiary_id:
                raise ValidationError(
                    {"beneficiary": _("Beneficiary must match the selected enrollment.")}
                )
            self.beneficiary_id = self.enrollment.beneficiary_id
            placement = (
                self.enrollment.placement_on(self.assessment_date) if self.assessment_date else None
            )
            if self.assessment_date and not placement:
                raise ValidationError(
                    {"enrollment": _("Enrollment has no center placement on the assessment date.")}
                )
            if placement:
                if self.center_id and self.center_id != placement.center_id:
                    raise ValidationError(
                        {"center": _("Assessment center must match enrollment placement.")}
                    )
                self.center_id = placement.center_id
        elif self.beneficiary_id:
            if self.center_id and self.center_id != self.beneficiary.center_id:
                raise ValidationError(
                    {"center": _("Assessment center must match beneficiary center.")}
                )
            self.center_id = self.beneficiary.center_id
        if self.enrollment_id and self.specialist_id and self.assessment_date:
            assigned = (
                EnrollmentSpecialistAssignment.objects.filter(
                    enrollment_id=self.enrollment_id,
                    specialist_id=self.specialist_id,
                )
                .filter(
                    Q(valid_to__isnull=True) | Q(valid_to__gt=self.assessment_date),
                    valid_from__lte=self.assessment_date,
                )
                .exists()
            )
            if not assigned:
                raise ValidationError(
                    {"specialist": _("The specialist is not assigned to this enrollment.")}
                )
        elif self.beneficiary_id and self.specialist_id:
            assigned = (
                BeneficiarySpecialistAssignment.objects.filter(
                    beneficiary_id=self.beneficiary_id,
                    specialist_id=self.specialist_id,
                )
                .filter(
                    Q(to_date__isnull=True) | Q(to_date__gt=self.assessment_date),
                    from_date__lte=self.assessment_date,
                )
                .exists()
            )
            if not assigned:
                raise ValidationError(
                    {"specialist": _("The specialist is not assigned to this beneficiary.")}
                )
        if not self.template_version_id and self.scoring_tool:
            self.template_version = (
                AssessmentTemplateVersion.objects.filter(
                    instrument__identifier=self.scoring_tool,
                    is_legacy=True,
                )
                .order_by("created_at")
                .first()
            )
        if not self.template_version_id:
            raise ValidationError({"template_version": _("An assessment template is required.")})
        self.scoring_tool = self.template_version.instrument.identifier
        if (
            self.enrollment_id
            and self.assessment_date
            and self._state.adding
            and not self.revision_of_id
            and not self.template_version.is_legacy
        ):
            if not self.template_version.is_available_for(
                self.enrollment.service_id, self.assessment_date
            ):
                raise ValidationError(
                    {
                        "template_version": _(
                            "The template is not published and effective for this service and date."
                        )
                    }
                )
        if self.next_review_date and self.assessment_date:
            if self.next_review_date < self.assessment_date:
                raise ValidationError(
                    {"next_review_date": _("Next review date cannot be before assessment date.")}
                )
        if self.assessment_type == self.AssessmentType.INITIAL:
            if self.previous_assessment_id:
                raise ValidationError(
                    {"previous_assessment": _("An initial assessment cannot have a predecessor.")}
                )
        elif not self.previous_assessment_id:
            raise ValidationError({"previous_assessment": _("A previous assessment is required.")})
        if self.previous_assessment_id:
            previous = self.previous_assessment
            if previous.pk == self.pk:
                raise ValidationError(
                    {"previous_assessment": _("An assessment cannot reference itself.")}
                )
            if previous.beneficiary_id != self.beneficiary_id:
                raise ValidationError(
                    {"previous_assessment": _("Previous assessment must use the same beneficiary.")}
                )
            if self.enrollment_id and previous.enrollment_id != self.enrollment_id:
                raise ValidationError(
                    {"previous_assessment": _("Previous assessment must use the same enrollment.")}
                )
            if (
                previous.template_version.instrument.lineage_code
                != self.template_version.instrument.lineage_code
            ):
                raise ValidationError(
                    {
                        "previous_assessment": _(
                            "Previous assessment must use a compatible instrument lineage."
                        )
                    }
                )
            if previous.assessment_type == self.AssessmentType.FINAL:
                raise ValidationError(
                    {"previous_assessment": _("A final assessment closes its assessment chain.")}
                )
            if (
                self._state.adding
                and not self.revision_of_id
                and previous.status != self.Status.COMPLETED
            ):
                raise ValidationError(
                    {"previous_assessment": _("Previous assessment must be completed.")}
                )
            if self.assessment_date and previous.assessment_date > self.assessment_date:
                raise ValidationError(
                    {
                        "previous_assessment": _(
                            "Previous assessment cannot be later than this assessment."
                        )
                    }
                )
        if self.revision_of_id:
            source = self.revision_of
            if source.revision_of_id:
                raise ValidationError(
                    {"revision_of": _("Corrections must reference the original.")}
                )
            for field in (
                "enrollment_id",
                "beneficiary_id",
                "center_id",
                "assessment_date",
                "assessment_type",
                "previous_assessment_id",
                "template_version_id",
                "chain_id",
                "chain_number",
                "assessment_cycle_number",
            ):
                if getattr(source, field) != getattr(self, field):
                    raise ValidationError(
                        {"revision_of": _("A correction must preserve assessment identity.")}
                    )
            if not self.correction_reason:
                raise ValidationError({"correction_reason": _("A correction reason is required.")})
        elif self._state.adding:
            lineage = self.template_version.instrument.lineage_code
            lineage_assessments = Assessment.objects.filter(
                enrollment_id=self.enrollment_id,
                template_version__instrument__lineage_code=lineage,
                revision_of__isnull=True,
            )
            if self.assessment_type == self.AssessmentType.INITIAL:
                latest = lineage_assessments.order_by(
                    "-chain_number", "-assessment_cycle_number", "-created_at"
                ).first()
                if latest and latest.assessment_type != self.AssessmentType.FINAL:
                    raise ValidationError(
                        {
                            "assessment_type": _(
                                "Complete the open instrument chain before starting another."
                            )
                        }
                    )
                if latest and self.assessment_date < latest.assessment_date:
                    raise ValidationError(
                        {
                            "assessment_date": _(
                                "A new chain cannot be backdated before the closed chain."
                            )
                        }
                    )
                self.chain_number = latest.chain_number + 1 if latest else 1
                self.assessment_cycle_number = 1
            else:
                previous_root_id = (
                    self.previous_assessment.revision_of_id or self.previous_assessment_id
                )
                predecessor_ids = Assessment.objects.filter(
                    Q(pk=previous_root_id) | Q(revision_of_id=previous_root_id)
                ).values("pk")
                successor_exists = (
                    Assessment.objects.filter(
                        previous_assessment_id__in=predecessor_ids,
                        revision_of__isnull=True,
                    )
                    .exclude(pk=self.pk)
                    .exists()
                )
                if successor_exists:
                    raise ValidationError(
                        {
                            "previous_assessment": _(
                                "The previous assessment already has a successor."
                            )
                        }
                    )
                self.chain_id = self.previous_assessment.chain_id
                self.chain_number = self.previous_assessment.chain_number
                self.assessment_cycle_number = self.previous_assessment.assessment_cycle_number + 1
        if self.pk:
            current = type(self).objects.filter(pk=self.pk).first()
            if current and current.status in {self.Status.COMPLETED, self.Status.SUPERSEDED}:
                immutable_fields = (
                    "enrollment_id",
                    "beneficiary_id",
                    "center_id",
                    "specialist_id",
                    "assessment_date",
                    "assessment_type",
                    "previous_assessment_id",
                    "template_version_id",
                    "chain_id",
                    "chain_number",
                    "assessment_cycle_number",
                    "revision_of_id",
                    "revision_number",
                    "status",
                )
                if any(
                    getattr(current, field) != getattr(self, field) for field in immutable_fields
                ):
                    raise ValidationError(_("Completed assessment identity is immutable."))
                self.total_score = current.total_score
                self.derived_classification = current.derived_classification
                self.delayed_domain_count = current.delayed_domain_count
                self.scoring_rule_version = current.scoring_rule_version
                self.calculation_trace = current.calculation_trace
                self.calculated_at = current.calculated_at
        if self.status == self.Status.DRAFT:
            self.total_score = Decimal("0")
            self.derived_classification = ""
            self.delayed_domain_count = 0
            self.scoring_rule_version = ""
            self.calculation_trace = {}
            self.calculated_at = None

    def save(self, *args, **kwargs):
        if not self.enrollment_id:
            self.enrollment = _infer_single_enrollment(self.beneficiary_id)
        if not self.template_version_id and self.scoring_tool:
            self.template_version = (
                AssessmentTemplateVersion.objects.filter(
                    instrument__identifier=self.scoring_tool,
                    is_legacy=True,
                )
                .order_by("created_at")
                .first()
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status != self.Status.DRAFT:
            raise models.ProtectedError(
                _("Completed assessments cannot be deleted. Create an audited correction."),
                {self},
            )
        return super().delete(*args, **kwargs)


class AssessmentResponse(ValidatedModel):
    class State(models.TextChoices):
        ASSESSED = "assessed", _("Assessed")
        NOT_ASSESSED = "not_assessed", _("Not assessed")
        NOT_APPLICABLE = "not_applicable", _("Not applicable")

    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.CASCADE,
        related_name="responses",
    )
    template_field = models.ForeignKey(
        AssessmentTemplateField,
        on_delete=models.PROTECT,
        related_name="responses",
    )
    state = models.CharField(max_length=16, choices=State.choices, default=State.ASSESSED)
    numeric_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    text_value = models.TextField(blank=True)
    choice_value = models.CharField(max_length=240, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = [
            "template_field__section__display_order",
            "template_field__display_order",
            "created_at",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "template_field"],
                name="unique_assessment_template_response",
            )
        ]

    def __str__(self) -> str:
        return f"{self.assessment} | {self.template_field.code}"

    def clean(self) -> None:
        self.text_value = self.text_value.strip()
        self.choice_value = self.choice_value.strip()
        self.notes = self.notes.strip()
        errors = {}
        if self.numeric_value == "":
            self.numeric_value = None
        elif self.numeric_value is not None and not isinstance(self.numeric_value, Decimal):
            try:
                self.numeric_value = Decimal(str(self.numeric_value))
            except (InvalidOperation, TypeError, ValueError):
                errors["numeric_value"] = _("Enter a valid numeric response.")
                self.numeric_value = None
        if (
            self.assessment_id
            and self.template_field_id
            and self.template_field.section.template_version_id
            != self.assessment.template_version_id
        ):
            errors["template_field"] = _(
                "Response field does not belong to the assessment template."
            )
        if self.assessment_id and self.assessment.status != Assessment.Status.DRAFT:
            current = type(self).objects.filter(pk=self.pk).first() if self.pk else None
            if current is None or any(
                getattr(current, field) != getattr(self, field)
                for field in ("state", "numeric_value", "text_value", "choice_value", "notes")
            ):
                errors["assessment"] = _("Completed assessment responses are immutable.")
        if not self.template_field_id:
            if errors:
                raise ValidationError(errors)
            return
        field = self.template_field
        response_type = field.response_type
        if self.state == self.State.NOT_ASSESSED:
            if (
                not field.allow_not_assessed
                and response_type != field.ResponseType.ASSESSED_NOT_ASSESSED
            ):
                errors["state"] = _("This response cannot be marked not assessed.")
            if self.numeric_value is not None or self.text_value or self.choice_value:
                errors["state"] = _("Not assessed responses cannot contain a value.")
        elif self.state == self.State.NOT_APPLICABLE:
            if (
                not field.allow_not_applicable
                and response_type != field.ResponseType.NOT_APPLICABLE
            ):
                errors["state"] = _("This response cannot be marked not applicable.")
            if self.numeric_value is not None or self.text_value or self.choice_value:
                errors["state"] = _("Not applicable responses cannot contain a value.")
        elif response_type == field.ResponseType.NOT_APPLICABLE:
            errors["state"] = _("This response must be marked not applicable.")
        elif response_type == field.ResponseType.ASSESSED_NOT_ASSESSED:
            if self.numeric_value is not None or self.text_value or self.choice_value:
                errors["state"] = _("Assessment-state responses cannot contain a value.")
        elif response_type in {field.ResponseType.NUMERIC_SCORE, field.ResponseType.PERCENTAGE}:
            if self.numeric_value is None:
                errors["numeric_value"] = _("A numeric response is required.")
            else:
                if field.minimum_value is not None and self.numeric_value < field.minimum_value:
                    errors["numeric_value"] = _("Response is below the allowed minimum.")
                if field.maximum_value is not None and self.numeric_value > field.maximum_value:
                    errors["numeric_value"] = _("Response is above the allowed maximum.")
                if field.minimum_value is not None:
                    offset = self.numeric_value - field.minimum_value
                    if offset % field.value_increment != 0:
                        errors["numeric_value"] = _("Response does not use the allowed increment.")
            if self.text_value or self.choice_value:
                errors["numeric_value"] = _(
                    "Numeric responses cannot contain text or choice values."
                )
        elif response_type == field.ResponseType.CHOICE:
            if self.choice_value not in field.allowed_choices:
                errors["choice_value"] = _("Select an allowed choice.")
            if self.numeric_value is not None or self.text_value:
                errors["choice_value"] = _("Choice responses cannot contain other values.")
        elif response_type == field.ResponseType.TEXT:
            if self.numeric_value is not None or self.choice_value:
                errors["text_value"] = _("Text responses cannot contain other values.")
        if errors:
            raise ValidationError(errors)

    def delete(self, *args, **kwargs):
        if self.assessment.status != Assessment.Status.DRAFT:
            raise models.ProtectedError(
                _("Completed assessment responses cannot be deleted."),
                {self},
            )
        return super().delete(*args, **kwargs)


class AssessmentResponsibleSpecialist(ValidatedModel):
    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.CASCADE,
        related_name="responsible_specialist_links",
    )
    specialist = models.ForeignKey(
        SpecialistProfile,
        on_delete=models.PROTECT,
        related_name="assessment_responsibilities",
    )

    class Meta:
        ordering = ["specialist__staff_profile__user__last_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "specialist"],
                name="unique_assessment_responsible_specialist",
            )
        ]

    def clean(self) -> None:
        if not self.assessment_id or not self.specialist_id:
            return
        if self.assessment.status != Assessment.Status.DRAFT and self._state.adding:
            raise ValidationError(
                {"assessment": _("Completed assessment responsibility is immutable.")}
            )
        assigned = (
            EnrollmentSpecialistAssignment.objects.filter(
                enrollment_id=self.assessment.enrollment_id,
                specialist_id=self.specialist_id,
                valid_from__lte=self.assessment.assessment_date,
            )
            .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=self.assessment.assessment_date))
            .exists()
        )
        if not assigned:
            raise ValidationError(
                {"specialist": _("The specialist is not assigned on the assessment date.")}
            )

    def delete(self, *args, **kwargs):
        if self.assessment.status != Assessment.Status.DRAFT:
            raise models.ProtectedError(
                _("Completed assessment responsibility is immutable."),
                {self},
            )
        return super().delete(*args, **kwargs)


class AssessmentDomainScore(ValidatedModel):
    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="domain_scores"
    )
    domain = models.CharField(max_length=180)
    baseline_score = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    current_score = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    progress_notes = models.TextField(blank=True)
    template_field = models.ForeignKey(
        AssessmentTemplateField,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="legacy_domain_scores",
    )
    mapping_status = models.CharField(
        max_length=24,
        choices=(
            ("review_required", _("Review required")),
            ("mapped", _("Mapped")),
        ),
        default="review_required",
        editable=False,
    )

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "domain"], name="unique_assessment_domain"
            )
        ]

    def __str__(self) -> str:
        return self.domain

    def clean(self) -> None:
        self.domain = self.domain.strip()
        self.progress_notes = self.progress_notes.strip()
        if (
            self.assessment_id
            and not self.assessment.template_version.is_legacy
            and self._state.adding
        ):
            raise ValidationError(
                _("Free-text domain rows are retained for legacy assessments only.")
            )
        if self.template_field_id and (
            self.template_field.section.template_version_id != self.assessment.template_version_id
        ):
            raise ValidationError(
                {"template_field": _("Mapped field must belong to the assessment template.")}
            )


@receiver(
    m2m_changed,
    sender=AssessmentTemplateVersion.applicable_services.through,
)
def protect_locked_template_service_scope(sender, instance, action, **kwargs) -> None:
    if action in {"pre_add", "pre_remove", "pre_clear"} and instance.is_locked:
        raise ValidationError(_("Published or used template versions are immutable."))


@receiver(pre_delete, sender=AssessmentTemplateSection)
@receiver(pre_delete, sender=AssessmentTemplateField)
@receiver(pre_delete, sender=AssessmentScoreBand)
def protect_locked_template_children(sender, instance, **kwargs) -> None:
    template = (
        instance.template_version
        if isinstance(instance, (AssessmentTemplateSection, AssessmentScoreBand))
        else instance.section.template_version
    )
    if template.is_locked:
        raise models.ProtectedError(
            _("Published or used template structures cannot be deleted."),
            {instance},
        )


@receiver(m2m_changed, sender=Assessment.responsible_specialists.through)
def protect_assessment_responsibility(sender, instance, action, reverse, pk_set, **kwargs) -> None:
    if action not in {"pre_add", "pre_remove", "pre_clear"}:
        return
    if reverse and pk_set is None:
        assessments = instance.responsible_assessments.all()
    elif reverse:
        assessments = Assessment.objects.filter(pk__in=pk_set)
    else:
        assessments = Assessment.objects.filter(pk=instance.pk)
    for assessment in assessments:
        if assessment.status != Assessment.Status.DRAFT:
            raise ValidationError(_("Completed assessment responsibility is immutable."))
        if action == "pre_add":
            specialist_ids = {instance.pk} if reverse else pk_set
            assigned_ids = set(
                EnrollmentSpecialistAssignment.objects.filter(
                    enrollment_id=assessment.enrollment_id,
                    specialist_id__in=specialist_ids,
                    valid_from__lte=assessment.assessment_date,
                )
                .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=assessment.assessment_date))
                .values_list("specialist_id", flat=True)
            )
            if assigned_ids != set(specialist_ids):
                raise ValidationError(
                    _("Every responsible specialist must be assigned on the assessment date.")
                )


@receiver(pre_delete, sender=AssessmentResponsibleSpecialist)
def protect_completed_assessment_responsibility(sender, instance, **kwargs) -> None:
    if instance.assessment.status != Assessment.Status.DRAFT:
        raise models.ProtectedError(
            _("Completed assessment responsibility is immutable."),
            {instance},
        )


@receiver(pre_delete, sender=AssessmentResponse)
def protect_completed_assessment_response(sender, instance, **kwargs) -> None:
    if instance.assessment.status != Assessment.Status.DRAFT:
        raise models.ProtectedError(
            _("Completed assessment responses cannot be deleted."),
            {instance},
        )


class GoalCategory(EffectiveDatedCatalogModel):
    applicable_services = models.ManyToManyField(
        ServiceDefinition,
        related_name="goal_categories",
        blank=True,
        help_text=_("Leave empty to allow this category for every service."),
    )
    reporting_order = models.PositiveIntegerField(default=0)
    is_legacy = models.BooleanField(default=False)

    class Meta:
        ordering = ["reporting_order", "name_en", "code"]

    def __str__(self) -> str:
        return self.localized_name

    def is_available_for(self, service_id, on_date: date) -> bool:
        if not self.is_effective(on_date):
            return False
        configured_services = self.applicable_services.all()
        return (
            not configured_services.exists() or configured_services.filter(pk=service_id).exists()
        )


class IndividualPlan(ValidatedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        ACTIVE = "active", _("Active")
        COMPLETED = "completed", _("Completed")
        SUPERSEDED = "superseded", _("Superseded")
        CANCELLED = "cancelled", _("Cancelled")

    class ReviewFrequency(models.TextChoices):
        WEEKLY = "weekly", _("Weekly")
        MONTHLY = "monthly", _("Monthly")
        QUARTERLY = "quarterly", _("Quarterly")

    enrollment = models.ForeignKey(
        ServiceEnrollment,
        on_delete=models.PROTECT,
        related_name="plans",
    )
    beneficiary = models.ForeignKey(Beneficiary, on_delete=models.PROTECT, related_name="plans")
    center = models.ForeignKey(Center, on_delete=models.PROTECT, related_name="individual_plans")
    specialist = models.ForeignKey(
        SpecialistProfile, on_delete=models.PROTECT, related_name="individual_plans"
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    plan_start_date = models.DateField(db_index=True)
    plan_end_date = models.DateField(null=True, blank=True, db_index=True)
    review_frequency = models.CharField(max_length=16, choices=ReviewFrequency.choices, blank=True)
    review_due_date = models.DateField(null=True, blank=True, db_index=True)
    version_number = models.PositiveIntegerField(default=0, editable=False)
    previous_plan = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="next_plan",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-plan_start_date", "-created_at"]
        indexes = [
            models.Index(fields=["center", "status", "plan_start_date"]),
            models.Index(fields=["specialist", "status"]),
            models.Index(fields=["beneficiary", "plan_start_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(plan_end_date__isnull=True)
                | Q(plan_end_date__gte=F("plan_start_date")),
                name="individual_plan_dates_ordered",
            ),
            models.UniqueConstraint(
                fields=["enrollment", "version_number"],
                name="unique_plan_version_per_enrollment",
            ),
            models.UniqueConstraint(
                fields=["enrollment"],
                condition=Q(status="active"),
                name="one_active_plan_per_enrollment",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.beneficiary.beneficiary_code} | {self.get_status_display()}"

    def clean(self) -> None:
        self.notes = self.notes.strip()
        if not self.enrollment_id:
            inferred = _infer_single_enrollment(self.beneficiary_id)
            if inferred:
                self.enrollment = inferred
        if self.enrollment_id:
            if self.beneficiary_id and self.beneficiary_id != self.enrollment.beneficiary_id:
                raise ValidationError(
                    {"beneficiary": _("Beneficiary must match the selected enrollment.")}
                )
            self.beneficiary_id = self.enrollment.beneficiary_id
            placement = (
                self.enrollment.placement_on(self.plan_start_date) if self.plan_start_date else None
            )
            if self.plan_start_date and not placement:
                raise ValidationError(
                    {"enrollment": _("Enrollment has no center placement on the plan start date.")}
                )
            if placement:
                if self.center_id and self.center_id != placement.center_id:
                    raise ValidationError(
                        {"center": _("Individual plan center must match enrollment placement.")}
                    )
                self.center_id = placement.center_id
        elif self.beneficiary_id:
            if self.center_id and self.center_id != self.beneficiary.center_id:
                raise ValidationError(
                    {"center": _("Individual plan center must match beneficiary center.")}
                )
            self.center_id = self.beneficiary.center_id
        if self.enrollment_id and self.specialist_id and self.plan_start_date:
            assigned = (
                EnrollmentSpecialistAssignment.objects.filter(
                    enrollment_id=self.enrollment_id,
                    specialist_id=self.specialist_id,
                )
                .filter(
                    Q(valid_to__isnull=True) | Q(valid_to__gt=self.plan_start_date),
                    valid_from__lte=self.plan_start_date,
                )
                .exists()
            )
            if not assigned:
                raise ValidationError(
                    {"specialist": _("The specialist is not assigned to this enrollment.")}
                )
        elif self.beneficiary_id and self.specialist_id:
            assigned = (
                BeneficiarySpecialistAssignment.objects.filter(
                    beneficiary_id=self.beneficiary_id,
                    specialist_id=self.specialist_id,
                )
                .filter(
                    Q(to_date__isnull=True) | Q(to_date__gt=self.plan_start_date),
                    from_date__lte=self.plan_start_date,
                )
                .exists()
            )
            if not assigned:
                raise ValidationError(
                    {"specialist": _("The specialist is not assigned to this beneficiary.")}
                )
        if self.plan_end_date and self.plan_start_date:
            if self.plan_end_date < self.plan_start_date:
                raise ValidationError(
                    {"plan_end_date": _("Plan end date cannot be before plan start date.")}
                )
        if self.review_due_date and self.review_due_date < self.plan_start_date:
            raise ValidationError(
                {"review_due_date": _("Review due date cannot be before plan start date.")}
            )
        if self.previous_plan_id:
            if self.previous_plan_id == self.pk:
                raise ValidationError({"previous_plan": _("A plan cannot follow itself.")})
            if self.enrollment_id != self.previous_plan.enrollment_id:
                raise ValidationError(
                    {"previous_plan": _("Previous plan must belong to the same enrollment.")}
                )
        if self.pk:
            previous_status = (
                IndividualPlan.objects.filter(pk=self.pk).values_list("status", flat=True).first()
            )
            allowed = {
                self.Status.DRAFT: {self.Status.ACTIVE, self.Status.CANCELLED},
                self.Status.ACTIVE: {
                    self.Status.COMPLETED,
                    self.Status.SUPERSEDED,
                    self.Status.CANCELLED,
                },
                self.Status.COMPLETED: set(),
                self.Status.SUPERSEDED: set(),
                self.Status.CANCELLED: set(),
            }
            if (
                previous_status
                and previous_status != self.status
                and self.status not in allowed.get(previous_status, set())
            ):
                raise ValidationError(
                    {"status": _("This individual plan status transition is not allowed.")}
                )

    def save(self, *args, **kwargs):
        if not self.enrollment_id:
            self.enrollment = _infer_single_enrollment(self.beneficiary_id)
        if self._state.adding and not self.version_number and self.enrollment_id:
            latest_version = (
                IndividualPlan.objects.filter(enrollment_id=self.enrollment_id)
                .order_by("-version_number")
                .values_list("version_number", flat=True)
                .first()
                or 0
            )
            self.version_number = latest_version + 1
        return super().save(*args, **kwargs)

    @property
    def latest_review(self):
        return self.reviews.order_by("-review_date", "-created_at").first()

    def goal_totals(self):
        return self.goals.values("status").annotate(total=models.Count("id")).order_by()


class IndividualPlanGoal(ValidatedModel):
    class Status(models.TextChoices):
        PLANNED = "planned", _("Planned")
        IN_PROGRESS = "in_progress", _("In Progress")
        ACHIEVED = "achieved", _("Achieved")
        DEFERRED = "deferred", _("Deferred")
        CANCELLED = "cancelled", _("Cancelled")

    class MeasurementType(models.TextChoices):
        NARRATIVE = "narrative", _("Narrative")
        NUMERIC = "numeric", _("Numeric")
        RATING_SCALE = "rating_scale", _("Rating scale")

    plan = models.ForeignKey(IndividualPlan, on_delete=models.CASCADE, related_name="goals")
    category = models.ForeignKey(
        GoalCategory,
        on_delete=models.PROTECT,
        related_name="goals",
    )
    goal = models.TextField()
    baseline = models.TextField(blank=True)
    measurable_target = models.TextField(blank=True)
    measurement_type = models.CharField(
        max_length=20,
        choices=MeasurementType.choices,
        default=MeasurementType.NARRATIVE,
    )
    measurement_unit_or_scale = models.CharField(max_length=120, blank=True)
    responsible_specialist = models.ForeignKey(
        SpecialistProfile,
        on_delete=models.PROTECT,
        related_name="responsible_plan_goals",
    )
    target_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PLANNED)
    achieved_date = models.DateField(null=True, blank=True)
    evidence = models.TextField(blank=True)
    progress_notes = models.TextField(blank=True)
    requires_review = models.BooleanField(default=False, editable=False, db_index=True)
    assessment_findings = models.ManyToManyField(
        Assessment,
        related_name="linked_plan_goals",
        blank=True,
        help_text=_("Assessment records whose findings support this goal."),
    )

    class Meta:
        ordering = ["target_date", "created_at"]

    def __str__(self) -> str:
        return self.goal[:80]

    def clean(self) -> None:
        self.goal = self.goal.strip()
        self.baseline = self.baseline.strip()
        self.measurable_target = self.measurable_target.strip()
        self.measurement_unit_or_scale = self.measurement_unit_or_scale.strip()
        self.evidence = self.evidence.strip()
        self.progress_notes = self.progress_notes.strip()
        errors = {}
        if self.category_id and self.plan_id:
            if not self.category.is_available_for(
                self.plan.enrollment.service_id,
                self.plan.plan_start_date,
            ):
                errors["category"] = _("Goal category is not available for this plan service.")
        if not self.requires_review:
            if not self.baseline:
                errors["baseline"] = _("A baseline is required.")
            if not self.measurable_target:
                errors["measurable_target"] = _("A measurable target is required.")
            if not self.target_date:
                errors["target_date"] = _("A target date is required.")
        if (
            self.measurement_type
            in {
                self.MeasurementType.NUMERIC,
                self.MeasurementType.RATING_SCALE,
            }
            and not self.measurement_unit_or_scale
        ):
            errors["measurement_unit_or_scale"] = _(
                "A unit or scale is required for this measurement type."
            )
        if self.target_date and self.plan_id and self.target_date < self.plan.plan_start_date:
            errors["target_date"] = _("Target date cannot be before the plan start date.")
        if self.responsible_specialist_id and self.plan_id:
            on_date = self.target_date or self.plan.plan_start_date
            assigned = (
                EnrollmentSpecialistAssignment.objects.filter(
                    enrollment_id=self.plan.enrollment_id,
                    specialist_id=self.responsible_specialist_id,
                    valid_from__lte=on_date,
                )
                .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=on_date))
                .exists()
            )
            if not assigned:
                errors["responsible_specialist"] = _(
                    "The responsible specialist is not assigned on the goal target date."
                )
        if self.status == self.Status.ACHIEVED:
            if not self.achieved_date:
                errors["achieved_date"] = _("Achieved date is required for an achieved goal.")
            if not self.evidence:
                errors["evidence"] = _("Evidence is required for an achieved goal.")
        elif self.achieved_date:
            errors["achieved_date"] = _("Achieved date is only allowed for achieved goals.")
        if self.achieved_date and self.plan_id and self.achieved_date < self.plan.plan_start_date:
            errors["achieved_date"] = _("Achieved date cannot be before the plan start date.")
        if self.pk:
            previous_status = (
                IndividualPlanGoal.objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
            allowed = {
                self.Status.PLANNED: {
                    self.Status.IN_PROGRESS,
                    self.Status.DEFERRED,
                    self.Status.CANCELLED,
                },
                self.Status.IN_PROGRESS: {
                    self.Status.ACHIEVED,
                    self.Status.DEFERRED,
                    self.Status.CANCELLED,
                },
                self.Status.DEFERRED: {
                    self.Status.PLANNED,
                    self.Status.IN_PROGRESS,
                    self.Status.CANCELLED,
                },
                self.Status.ACHIEVED: set(),
                self.Status.CANCELLED: set(),
            }
            if (
                previous_status
                and previous_status != self.status
                and self.status not in allowed.get(previous_status, set())
            ):
                errors["status"] = _("This goal status transition is not allowed.")
        if errors:
            raise ValidationError(errors)


class GoalStatusTransition(ValidatedModel):
    goal = models.ForeignKey(
        IndividualPlanGoal,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    from_status = models.CharField(
        max_length=16,
        choices=IndividualPlanGoal.Status.choices,
        blank=True,
    )
    to_status = models.CharField(max_length=16, choices=IndividualPlanGoal.Status.choices)
    transition_date = models.DateField(default=timezone.localdate, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="goal_status_transitions",
    )
    reason = models.TextField(blank=True)
    evidence = models.TextField(blank=True)

    class Meta:
        ordering = ["transition_date", "created_at"]
        indexes = [models.Index(fields=["goal", "transition_date"])]

    def clean(self) -> None:
        self.reason = self.reason.strip()
        self.evidence = self.evidence.strip()
        if self.pk and GoalStatusTransition.objects.filter(pk=self.pk).exists():
            raise ValidationError(_("Goal status history is append-only."))
        if (
            self.to_status
            in {
                IndividualPlanGoal.Status.DEFERRED,
                IndividualPlanGoal.Status.CANCELLED,
            }
            and not self.reason
        ):
            raise ValidationError({"reason": _("A reason is required for this goal status.")})
        if (
            self.transition_date
            and self.goal_id
            and self.transition_date < self.goal.plan.plan_start_date
        ):
            raise ValidationError(
                {"transition_date": _("Status change date cannot be before the plan start date.")}
            )

    def delete(self, *args, **kwargs):
        raise TypeError("Goal status history is append-only.")


class GoalOutcomeMeasurement(ValidatedModel):
    goal = models.ForeignKey(
        IndividualPlanGoal,
        on_delete=models.CASCADE,
        related_name="measurements",
    )
    measurement_date = models.DateField(db_index=True)
    numeric_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    rating = models.CharField(max_length=120, blank=True)
    unit_or_scale = models.CharField(max_length=120, blank=True)
    interpretation = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="goal_outcome_measurements",
    )
    source_assessment = models.ForeignKey(
        Assessment,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="goal_outcome_measurements",
    )

    class Meta:
        ordering = ["-measurement_date", "-created_at"]
        indexes = [models.Index(fields=["goal", "measurement_date"])]

    def clean(self) -> None:
        self.rating = self.rating.strip()
        self.unit_or_scale = self.unit_or_scale.strip()
        self.interpretation = self.interpretation.strip()
        self.notes = self.notes.strip()
        errors = {}
        if self.numeric_value is None and not self.rating:
            errors["numeric_value"] = _("Enter a numeric value or a rating.")
        if self.source_assessment_id and (
            self.source_assessment.enrollment_id != self.goal.plan.enrollment_id
        ):
            errors["source_assessment"] = _("Source assessment must belong to the goal enrollment.")
        if self.measurement_date and self.measurement_date < self.goal.plan.plan_start_date:
            errors["measurement_date"] = _("Measurement date cannot be before the plan start date.")
        if errors:
            raise ValidationError(errors)
        if self.pk and GoalOutcomeMeasurement.objects.filter(pk=self.pk).exists():
            raise ValidationError(_("Goal outcome measurements are append-only."))

    def delete(self, *args, **kwargs):
        raise TypeError("Goal outcome measurements are append-only.")


class IndividualPlanReview(ValidatedModel):
    class ConditionOutcome(models.TextChoices):
        IMPROVED = "improved", _("Improved")
        WORSENED = "worsened", _("Worsened")
        STABLE = "stable", _("Stable")
        NOT_YET_ASSESSED = "not_yet_assessed", _("Not yet assessed")

    plan = models.ForeignKey(IndividualPlan, on_delete=models.CASCADE, related_name="reviews")
    review_date = models.DateField(db_index=True)
    condition_outcome = models.CharField(max_length=24, choices=ConditionOutcome.choices)
    rationale = models.TextField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="individual_plan_reviews",
    )
    source_assessment = models.ForeignKey(
        Assessment,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="plan_reviews",
    )

    class Meta:
        ordering = ["-review_date", "-created_at"]
        indexes = [models.Index(fields=["plan", "review_date"])]

    def clean(self) -> None:
        self.rationale = self.rationale.strip()
        errors = {}
        if not self.rationale:
            errors["rationale"] = _("A review rationale is required.")
        if self.review_date and self.review_date < self.plan.plan_start_date:
            errors["review_date"] = _("Review date cannot be before the plan start date.")
        if self.source_assessment_id and (
            self.source_assessment.enrollment_id != self.plan.enrollment_id
        ):
            errors["source_assessment"] = _("Source assessment must belong to the plan enrollment.")
        if errors:
            raise ValidationError(errors)
        if self.pk and IndividualPlanReview.objects.filter(pk=self.pk).exists():
            raise ValidationError(_("Plan reviews are append-only."))

    def delete(self, *args, **kwargs):
        raise TypeError("Plan reviews are append-only.")


@receiver(m2m_changed, sender=IndividualPlanGoal.assessment_findings.through)
def protect_goal_assessment_scope(sender, instance, action, reverse, pk_set, **kwargs) -> None:
    if action != "pre_add" or not pk_set:
        return
    if reverse:
        invalid = IndividualPlanGoal.objects.filter(pk__in=pk_set).exclude(
            plan__enrollment_id=instance.enrollment_id
        )
    else:
        invalid = Assessment.objects.filter(pk__in=pk_set).exclude(
            enrollment_id=instance.plan.enrollment_id
        )
    if invalid.exists():
        raise ValidationError(_("Assessment findings must belong to the goal enrollment."))


@receiver(m2m_changed, sender=ServiceVisit.goals_worked_on.through)
def protect_visit_goal_scope(sender, instance, action, reverse, pk_set, **kwargs) -> None:
    if action != "pre_add" or not pk_set:
        return
    if reverse:
        invalid = ServiceVisit.objects.filter(pk__in=pk_set).exclude(
            enrollment_id=instance.plan.enrollment_id
        )
    else:
        invalid = IndividualPlanGoal.objects.filter(pk__in=pk_set).exclude(
            plan__enrollment_id=instance.enrollment_id
        )
    if invalid.exists():
        raise ValidationError(_("Visit goals must belong to the same enrollment."))


class SpecialistMonthlyServiceSummary(ValidatedModel):
    specialist = models.ForeignKey(
        SpecialistProfile, on_delete=models.PROTECT, related_name="monthly_summaries"
    )
    center = models.ForeignKey(Center, on_delete=models.PROTECT, related_name="monthly_summaries")
    summary_month = models.DateField(db_index=True)
    completed_visits = models.PositiveIntegerField(default=0)
    total_service_units = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_duration_minutes = models.PositiveIntegerField(default=0)
    unique_beneficiaries = models.PositiveIntegerField(default=0)
    planned_count = models.PositiveIntegerField(default=0)
    no_show_count = models.PositiveIntegerField(default=0)
    cancelled_count = models.PositiveIntegerField(default=0)
    last_rebuilt_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-summary_month", "specialist__staff_profile__user__last_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["specialist", "center", "summary_month"],
                name="unique_specialist_center_month_summary",
            ),
            models.CheckConstraint(
                condition=Q(summary_month__day=1), name="summary_month_is_first_day"
            ),
        ]
        indexes = [
            models.Index(fields=["center", "summary_month"]),
            models.Index(fields=["specialist", "summary_month"]),
        ]

    def __str__(self) -> str:
        return f"{self.specialist} | {self.summary_month:%Y-%m}"

    def clean(self) -> None:
        if self.summary_month:
            self.summary_month = self.summary_month.replace(day=1)


class AttachmentParentType(models.TextChoices):
    BENEFICIARY = "beneficiary", _("Beneficiary")
    SERVICE_VISIT = "service_visit", _("Service Visit")
    ASSESSMENT = "assessment", _("Assessment")
    INDIVIDUAL_PLAN = "individual_plan", _("Individual Plan")
    STAFF_PROFILE = "staff_profile", _("Staff Profile")


ATTACHMENT_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".txt": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def private_upload_to(instance, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return f"{timezone.now():%Y/%m}/{uuid.uuid4().hex}{suffix}"


class PrivateAttachment(ValidatedModel):
    class DocumentType(models.TextChoices):
        PROJECT_AGREEMENT = "project_agreement", _("Project agreement")
        EMPLOYEE_CONTRACT = "employee_contract", _("Employee contract")
        ADDITIONAL_DOCUMENTATION = "additional_documentation", _("Additional documentation")

    parent_type = models.CharField(max_length=24, choices=AttachmentParentType.choices)
    parent_id = models.UUIDField()
    document_type = models.CharField(max_length=32, choices=DocumentType.choices, blank=True)
    center = models.ForeignKey(Center, on_delete=models.PROTECT, related_name="private_attachments")
    file = models.FileField(
        storage=private_file_storage,
        upload_to=private_upload_to,
        validators=[validate_private_upload],
        max_length=255,
    )
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True, editable=False)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="private_attachments",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["parent_type", "parent_id"]),
            models.Index(fields=["center", "created_at"]),
        ]

    def __str__(self) -> str:
        return self.original_filename

    @property
    def parent_object(self):
        from .private_attachments import _parent_model

        model = _parent_model(self.parent_type)
        if not model:
            return None
        return model.objects.filter(pk=self.parent_id).first()

    def clean(self) -> None:
        self.original_filename = Path(self.original_filename.replace("\\", "/")).name[:255]
        parent = self.parent_object
        if not parent:
            raise ValidationError({"parent_id": _("The attachment parent does not exist.")})
        if self.parent_type == AttachmentParentType.BENEFICIARY:
            self.center_id = self.center_id or parent.center_id
            authorized_center = parent.enrollments.filter(
                center_placements__center_id=self.center_id
            ).exists()
            if not authorized_center:
                raise ValidationError({"center": _("Attachment center must match its parent.")})
        else:
            from .private_attachments import _center_for_parent

            parent_center = _center_for_parent(self.parent_type, parent)
            parent_center_id = parent_center.pk if parent_center else None
            if not parent_center_id:
                raise ValidationError({"center": _("The attachment parent must have a center.")})
            if self.center_id and self.center_id != parent_center_id:
                raise ValidationError({"center": _("Attachment center must match its parent.")})
            self.center_id = parent_center_id
        if self.file:
            validate_private_upload(self.file)
            suffix = Path(self.file.name).suffix.lower()
            if self.parent_type == AttachmentParentType.STAFF_PROFILE:
                if self.document_type not in self.DocumentType.values:
                    raise ValidationError({"document_type": _("Select a staff document type.")})
                if (
                    self.document_type
                    in {
                        self.DocumentType.PROJECT_AGREEMENT,
                        self.DocumentType.EMPLOYEE_CONTRACT,
                    }
                    and suffix != ".pdf"
                ):
                    raise ValidationError(
                        {"file": _("Project agreements and employee contracts must be PDFs.")}
                    )
            elif self.document_type:
                raise ValidationError(
                    {"document_type": _("Document type is available only for staff files.")}
                )
            self.content_type = ATTACHMENT_CONTENT_TYPES.get(suffix, "application/octet-stream")

    def save(self, *args, **kwargs):
        if self.file and not self.sha256:
            digest = hashlib.sha256()
            for chunk in self.file.chunks():
                digest.update(chunk)
            self.sha256 = digest.hexdigest()
            self.size = self.file.size
            self.file.seek(0)
        return super().save(*args, **kwargs)
