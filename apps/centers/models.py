from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import ValidatedModel
from apps.core.validators import phone_number_validator


class Center(ValidatedModel):
    code = models.CharField(max_length=24, unique=True)
    name = models.CharField(max_length=180, unique=True)
    is_active = models.BooleanField(default=True, db_index=True)
    phone = models.CharField(max_length=40, blank=True, validators=[phone_number_validator])
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        self.phone = self.phone.strip()
        self.email = self.email.strip().lower()


class StaffProfile(ValidatedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        INACTIVE = "inactive", _("Inactive")
        FINISHED = "finished", _("Finished")

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="staff_profile"
    )
    employee_number = models.CharField(max_length=40, unique=True)
    project_program = models.CharField(
        max_length=180, blank=True, verbose_name=_("Project or program")
    )
    job_title = models.CharField(max_length=120, blank=True, verbose_name=_("Position"))
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    contact_number = models.CharField(
        max_length=40,
        blank=True,
        validators=[phone_number_validator],
        verbose_name=_("Contact number"),
    )
    contract_signed_on = models.DateField(
        null=True, blank=True, verbose_name=_("Contract signing date")
    )
    contract_valid_until = models.DateField(
        null=True, blank=True, verbose_name=_("Contract valid until")
    )
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    primary_center = models.ForeignKey(
        Center,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="primary_staff",
    )
    centers = models.ManyToManyField(Center, related_name="staff", blank=True)

    class Meta:
        ordering = ["user__last_name", "user__first_name", "employee_number"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(contract_signed_on__isnull=True)
                    | Q(contract_valid_until__isnull=True)
                    | Q(contract_valid_until__gte=models.F("contract_signed_on"))
                ),
                name="staff_contract_dates_ordered",
            )
        ]

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        return self.user.get_full_name().strip() or self.user.username

    def clean(self) -> None:
        self.employee_number = self.employee_number.strip().upper()
        self.project_program = self.project_program.strip()
        self.job_title = self.job_title.strip()
        self.contact_number = self.contact_number.strip()
        self.description = self.description.strip()
        self.notes = self.notes.strip()
        if (
            self.contract_signed_on
            and self.contract_valid_until
            and self.contract_valid_until < self.contract_signed_on
        ):
            raise ValidationError(
                {"contract_valid_until": _("Contract validity cannot end before it begins.")}
            )


class SpecialistProfile(ValidatedModel):
    staff_profile = models.OneToOneField(
        StaffProfile, on_delete=models.PROTECT, related_name="specialist_profile"
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["staff_profile__user__last_name", "staff_profile__user__first_name"]

    def __str__(self) -> str:
        return self.staff_profile.display_name

    def clean(self) -> None:
        self.description = self.description.strip()

    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        if self.staff_profile.description != self.description:
            self.staff_profile.description = self.description
            self.staff_profile.save(update_fields=["description", "updated_at"])
        return result


class SpecialistCenterAssignment(ValidatedModel):
    specialist = models.ForeignKey(
        SpecialistProfile, on_delete=models.PROTECT, related_name="center_assignments"
    )
    center = models.ForeignKey(
        Center, on_delete=models.PROTECT, related_name="specialist_assignments"
    )
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["center__name", "specialist__staff_profile__user__last_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["specialist", "center"], name="unique_specialist_center_assignment"
            ),
            models.UniqueConstraint(
                fields=["specialist"],
                condition=Q(is_primary=True),
                name="one_primary_center_per_specialist",
            ),
        ]
        indexes = [models.Index(fields=["center", "specialist"])]

    def __str__(self) -> str:
        return f"{self.specialist} at {self.center}"

    def clean(self) -> None:
        if self.is_primary and self.specialist_id:
            duplicate = SpecialistCenterAssignment.objects.filter(
                specialist_id=self.specialist_id, is_primary=True
            ).exclude(pk=self.pk)
            if duplicate.exists():
                raise ValidationError(
                    {"is_primary": _("A specialist can have only one primary center.")}
                )

    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        self.specialist.staff_profile.centers.add(self.center)
        if self.is_primary and self.specialist.staff_profile.primary_center_id != self.center_id:
            self.specialist.staff_profile.primary_center = self.center
            self.specialist.staff_profile.save(update_fields=["primary_center", "updated_at"])
        return result
