from __future__ import annotations

import hashlib
import uuid
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.centers.models import Center, SpecialistProfile
from apps.core.models import ValidatedModel
from apps.core.validators import phone_number_validator

from .storage import private_file_storage
from .validators import validate_private_upload


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
        if not self.birth_date:
            return None
        today = timezone.localdate()
        return max(
            0,
            today.year
            - self.birth_date.year
            - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day)),
        )

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

    def clean(self) -> None:
        if self.to_date and self.from_date and self.to_date < self.from_date:
            raise ValidationError({"to_date": _("To date cannot be before from date.")})
        if self.beneficiary_id and self.specialist_id:
            available = self.specialist.center_assignments.filter(
                center_id=self.beneficiary.center_id
            ).exists()
            if not available:
                raise ValidationError(
                    {"specialist": _("The specialist is not assigned to this center.")}
                )


class ServiceVisit(ValidatedModel):
    class VisitType(models.TextChoices):
        CENTER = "center_visit", _("Center Visit")
        HOME = "home_visit", _("Home Visit")
        SCHOOL = "school_visit", _("School Visit")
        HOSPITAL = "hospital_visit", _("Hospital Visit")
        COMMUNITY = "community_outreach", _("Community Outreach")
        REMOTE = "remote_session", _("Remote Session")
        GROUP = "group_session", _("Group Session")
        CONFERENCE = "case_conference", _("Case Conference")
        OTHER = "other", _("Other")

    class Status(models.TextChoices):
        COMPLETED = "completed", _("Completed")
        NO_SHOW = "no_show", _("No Show")
        CANCELLED = "cancelled", _("Cancelled")

    beneficiary = models.ForeignKey(Beneficiary, on_delete=models.PROTECT, related_name="visits")
    center = models.ForeignKey(Center, on_delete=models.PROTECT, related_name="service_visits")
    specialist = models.ForeignKey(
        SpecialistProfile, on_delete=models.PROTECT, related_name="service_visits"
    )
    visit_date = models.DateField(db_index=True)
    visit_month = models.DateField(editable=False, db_index=True)
    visit_type = models.CharField(max_length=32, choices=VisitType.choices, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, db_index=True)
    service_units = models.DecimalField(
        max_digits=8, decimal_places=2, default=1, validators=[MinValueValidator(0)]
    )
    duration_minutes = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-visit_date", "-created_at"]
        indexes = [
            models.Index(fields=["center", "visit_date", "status"]),
            models.Index(fields=["specialist", "visit_month", "status"]),
            models.Index(fields=["beneficiary", "visit_date"]),
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
        ]

    def __str__(self) -> str:
        return f"{self.beneficiary.beneficiary_code} | {self.visit_date}"

    @property
    def month_label(self) -> str:
        return self.visit_month.strftime("%Y-%m")

    def clean(self) -> None:
        self.notes = self.notes.strip()
        if self.beneficiary_id:
            if self.center_id and self.center_id != self.beneficiary.center_id:
                raise ValidationError(
                    {"center": _("Service visit center must match beneficiary center.")}
                )
            self.center_id = self.beneficiary.center_id
        if self.visit_date:
            self.visit_month = date(self.visit_date.year, self.visit_date.month, 1)
        if self.status == self.Status.CANCELLED:
            self.service_units = 0
        if self.beneficiary_id and self.specialist_id:
            assigned = BeneficiarySpecialistAssignment.objects.filter(
                beneficiary_id=self.beneficiary_id, specialist_id=self.specialist_id
            ).exists()
            if not assigned:
                raise ValidationError(
                    {"specialist": _("The specialist is not assigned to this beneficiary.")}
                )


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
    scoring_tool = models.CharField(max_length=16, choices=ScoringTool.choices)
    total_score = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)]
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
        if self.beneficiary_id:
            if self.center_id and self.center_id != self.beneficiary.center_id:
                raise ValidationError(
                    {"center": _("Assessment center must match beneficiary center.")}
                )
            self.center_id = self.beneficiary.center_id
        if self.beneficiary_id and self.specialist_id:
            assigned = BeneficiarySpecialistAssignment.objects.filter(
                beneficiary_id=self.beneficiary_id, specialist_id=self.specialist_id
            ).exists()
            if not assigned:
                raise ValidationError(
                    {"specialist": _("The specialist is not assigned to this beneficiary.")}
                )
        if self.next_review_date and self.assessment_date:
            if self.next_review_date < self.assessment_date:
                raise ValidationError(
                    {"next_review_date": _("Next review date cannot be before assessment date.")}
                )
        if self.assessment_type == self.AssessmentType.INITIAL:
            self.previous_assessment = None
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
            if self.assessment_date and previous.assessment_date > self.assessment_date:
                raise ValidationError(
                    {
                        "previous_assessment": _(
                            "Previous assessment cannot be later than this assessment."
                        )
                    }
                )
        if self.beneficiary_id and self.assessment_date:
            earlier = Assessment.objects.filter(
                beneficiary_id=self.beneficiary_id, assessment_date__lte=self.assessment_date
            ).exclude(pk=self.pk)
            self.assessment_cycle_number = earlier.count() + 1


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


class IndividualPlan(ValidatedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        ACTIVE = "active", _("Active")
        COMPLETED = "completed", _("Completed")

    class ReviewFrequency(models.TextChoices):
        WEEKLY = "weekly", _("Weekly")
        MONTHLY = "monthly", _("Monthly")
        QUARTERLY = "quarterly", _("Quarterly")

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
            )
        ]

    def __str__(self) -> str:
        return f"{self.beneficiary.beneficiary_code} | {self.get_status_display()}"

    def clean(self) -> None:
        self.notes = self.notes.strip()
        if self.beneficiary_id:
            if self.center_id and self.center_id != self.beneficiary.center_id:
                raise ValidationError(
                    {"center": _("Individual plan center must match beneficiary center.")}
                )
            self.center_id = self.beneficiary.center_id
        if self.beneficiary_id and self.specialist_id:
            assigned = BeneficiarySpecialistAssignment.objects.filter(
                beneficiary_id=self.beneficiary_id, specialist_id=self.specialist_id
            ).exists()
            if not assigned:
                raise ValidationError(
                    {"specialist": _("The specialist is not assigned to this beneficiary.")}
                )
        if self.plan_end_date and self.plan_start_date:
            if self.plan_end_date < self.plan_start_date:
                raise ValidationError(
                    {"plan_end_date": _("Plan end date cannot be before plan start date.")}
                )


class IndividualPlanGoal(ValidatedModel):
    class Status(models.TextChoices):
        PLANNED = "planned", _("Planned")
        IN_PROGRESS = "in_progress", _("In Progress")
        ACHIEVED = "achieved", _("Achieved")
        DEFERRED = "deferred", _("Deferred")

    plan = models.ForeignKey(IndividualPlan, on_delete=models.CASCADE, related_name="goals")
    goal = models.TextField()
    target_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PLANNED)
    progress_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["target_date", "created_at"]

    def __str__(self) -> str:
        return self.goal[:80]

    def clean(self) -> None:
        self.goal = self.goal.strip()
        self.progress_notes = self.progress_notes.strip()


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
