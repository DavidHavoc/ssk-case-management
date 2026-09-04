from __future__ import annotations

from datetime import date, datetime

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms import BaseFormSet, BaseInlineFormSet, formset_factory, inlineformset_factory
from django.utils.dateparse import parse_date
from django.utils.translation import gettext_lazy as _

from apps.accounts.roles import is_coordinator, is_system_manager
from apps.centers.models import SpecialistProfile
from apps.core.authorization import (
    assessments_for_user,
    can_create_case_record,
    enrollments_for_user,
    plans_for_user,
    specialist_profile_for_user,
    specialists_for_center,
)
from apps.core.forms import StyledForm, StyledModelForm

from .models import (
    Assessment,
    AssessmentDomainScore,
    AssessmentResponse,
    AssessmentTemplateField,
    AssessmentTemplateVersion,
    Beneficiary,
    BeneficiaryDiagnosis,
    BeneficiarySocialStatus,
    CenterServiceOffering,
    EnrollmentServiceSchedule,
    EnrollmentSpecialistAssignment,
    GoalCategory,
    GoalOutcomeMeasurement,
    IndividualPlan,
    IndividualPlanGoal,
    IndividualPlanReview,
    ServiceActivityDefinition,
    ServiceEnrollment,
    ServiceVisit,
    VisitLocationDefinition,
)

RESTRICTED_BENEFICIARY_FIELDS = (
    "personal_id",
    "address",
    "guardian_parent",
    "phone",
    "email",
    "application_contract_number",
)


class BeneficiaryForm(StyledModelForm):
    class Meta:
        model = Beneficiary
        fields = (
            "beneficiary_code",
            "full_name",
            "personal_id",
            "sex",
            "birth_date",
            "region_ref",
            "municipality_ref",
            "address",
            "guardian_parent",
            "phone",
            "email",
            "family_status",
            "notes",
        )
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, user, center, **kwargs):
        self.user = user
        self.center = center
        super().__init__(*args, **kwargs)
        if not (is_system_manager(user) or is_coordinator(user)):
            for field in RESTRICTED_BENEFICIARY_FIELDS:
                self.fields.pop(field, None)

    def save(self, commit=True):
        if self.instance._state.adding and not self.instance.center_id:
            self.instance.center = self.center
        if not self.instance.service_type:
            self.instance.service_type = Beneficiary.ServiceType.OTHER
        return super().save(commit=commit)


class EnrollmentIntakeForm(StyledForm):
    offering = forms.ModelChoiceField(
        queryset=CenterServiceOffering.objects.none(),
        label=_("Service and center offering"),
    )
    episode_code = forms.CharField(max_length=48, label=_("Enrollment code"))
    status = forms.ChoiceField(
        choices=(
            (ServiceEnrollment.Status.PENDING, _("Pending")),
            (ServiceEnrollment.Status.ACTIVE, _("Active")),
        )
    )
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    first_service_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    application_contract_number = forms.CharField(max_length=80, required=False)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, center, service=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = CenterServiceOffering.objects.filter(
            center=center,
            is_active=True,
            service__is_active=True,
        ).select_related("center", "service")
        if service is not None:
            queryset = queryset.filter(service=service)
        self.fields["offering"].queryset = queryset
        for field in self.fields.values():
            field.widget.attrs.setdefault(
                "class", "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            )

    def clean_episode_code(self):
        return self.cleaned_data["episode_code"].strip().upper()

    def clean(self):
        cleaned = super().clean()
        start_date = cleaned.get("start_date")
        first_service_date = cleaned.get("first_service_date")
        offering = cleaned.get("offering")
        if first_service_date and start_date and first_service_date < start_date:
            self.add_error(
                "first_service_date",
                _("First service date cannot be before enrollment start date."),
            )
        if offering and start_date and not offering.is_effective(start_date):
            self.add_error(
                "offering",
                _("The center offering is not effective on the enrollment start date."),
            )
        return cleaned


class EnrollmentUpdateForm(StyledModelForm):
    class Meta:
        model = ServiceEnrollment
        fields = (
            "first_service_date",
            "application_contract_number",
            "notes",
        )
        widgets = {
            "first_service_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }


class EnrollmentAssignmentForm(StyledModelForm):
    class Meta:
        model = EnrollmentSpecialistAssignment
        fields = ("specialist", "assignment_role", "valid_from", "valid_to")
        widgets = {
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "valid_to": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, center=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["valid_from"].required = not self.instance.legacy_dates_incomplete
        self.fields["valid_from"].help_text = _(
            "Access begins on this date. Leave blank only for approved legacy history."
        )
        self.fields["valid_to"].help_text = _(
            "Access ends at the start of this date. Leave blank for an open assignment."
        )
        queryset = specialists_for_center(center) if center else SpecialistProfile.objects.none()
        if self.instance.pk and self.instance.specialist_id:
            queryset = SpecialistProfile.objects.filter(
                Q(pk__in=queryset) | Q(pk=self.instance.specialist_id)
            )
        self.fields["specialist"].queryset = queryset


EnrollmentAssignmentFormSet = inlineformset_factory(
    ServiceEnrollment,
    EnrollmentSpecialistAssignment,
    form=EnrollmentAssignmentForm,
    fields=("specialist", "assignment_role", "valid_from", "valid_to"),
    extra=1,
    can_delete=True,
)


class BeneficiaryDiagnosisForm(StyledModelForm):
    class Meta:
        model = BeneficiaryDiagnosis
        fields = (
            "definition",
            "enrollment",
            "recorded_on",
            "valid_from",
            "valid_to",
            "verification_status",
            "visible_to_specialists",
            "notes",
        )
        widgets = {
            "recorded_on": forms.DateInput(attrs={"type": "date"}),
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "valid_to": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, beneficiary=None, user=None, center=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = ServiceEnrollment.objects.none()
        if beneficiary and beneficiary.pk and user is not None:
            queryset = (
                beneficiary.enrollments.all()
                if is_system_manager(user)
                else enrollments_for_user(user, center).filter(beneficiary=beneficiary)
            )
        self.fields["enrollment"].queryset = queryset
        if user is not None and not is_system_manager(user):
            self.fields["enrollment"].required = True


class BeneficiarySocialStatusForm(StyledModelForm):
    class Meta:
        model = BeneficiarySocialStatus
        fields = (
            "definition",
            "enrollment",
            "recorded_on",
            "valid_from",
            "valid_to",
            "verification_status",
            "visible_to_specialists",
            "notes",
        )
        widgets = {
            "recorded_on": forms.DateInput(attrs={"type": "date"}),
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "valid_to": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, beneficiary=None, user=None, center=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = ServiceEnrollment.objects.none()
        if beneficiary and beneficiary.pk and user is not None:
            queryset = (
                beneficiary.enrollments.all()
                if is_system_manager(user)
                else enrollments_for_user(user, center).filter(beneficiary=beneficiary)
            )
        self.fields["enrollment"].queryset = queryset
        if user is not None and not is_system_manager(user):
            self.fields["enrollment"].required = True


BeneficiaryDiagnosisFormSet = inlineformset_factory(
    Beneficiary,
    BeneficiaryDiagnosis,
    form=BeneficiaryDiagnosisForm,
    extra=1,
    can_delete=True,
)

BeneficiarySocialStatusFormSet = inlineformset_factory(
    Beneficiary,
    BeneficiarySocialStatus,
    form=BeneficiarySocialStatusForm,
    extra=1,
    can_delete=True,
)


class EnrollmentTransitionForm(StyledForm):
    effective_date = forms.DateField(
        label=_("Effective from"),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    reason = forms.CharField(
        max_length=180,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
    )


class EnrollmentTransferForm(EnrollmentTransitionForm):
    destination_offering = forms.ModelChoiceField(
        queryset=CenterServiceOffering.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, enrollment, **kwargs):
        super().__init__(*args, **kwargs)
        current = enrollment.current_placement
        self.fields["destination_offering"].queryset = CenterServiceOffering.objects.filter(
            service=enrollment.service,
            is_active=True,
            center__is_active=True,
        ).exclude(center_id=getattr(current, "center_id", None))


def _apply_legacy_beneficiary_enrollment(form, enrollment_queryset) -> None:
    if not form.is_bound or form.data.get("enrollment") or not form.data.get("beneficiary"):
        return
    matches = enrollment_queryset.filter(beneficiary_id=form.data.get("beneficiary"))
    if matches.count() == 1:
        data = form.data.copy()
        data["enrollment"] = str(matches.first().pk)
        form.data = data


def _validate_actor_assignment(
    form,
    cleaned_data,
    date_field: str,
    *,
    allowed_statuses=None,
):
    enrollment = cleaned_data.get("enrollment")
    business_date = cleaned_data.get(date_field)
    if (
        enrollment
        and business_date
        and not can_create_case_record(
            form.user,
            form.center,
            enrollment,
            business_date,
            allowed_statuses=allowed_statuses,
        )
    ):
        form.add_error(
            "enrollment",
            _("Your assignment is not effective on the selected record date."),
        )
    return cleaned_data


def _record_business_date(form, date_field: str):
    if form.is_bound:
        raw_value = form.data.get(date_field)
        if isinstance(raw_value, date):
            return raw_value
        if not raw_value:
            return None
        try:
            return datetime.strptime(str(raw_value), "%d/%m/%Y").date()
        except ValueError:
            return parse_date(str(raw_value))
    return getattr(form.instance, date_field, None)


def _specialists_for_record(
    *,
    center,
    enrollment,
    business_date,
    existing_specialist_id=None,
):
    queryset = specialists_for_center(center)
    if enrollment:
        assignment = Q(enrollment_assignments__enrollment=enrollment)
        if business_date:
            assignment &= Q(enrollment_assignments__valid_from__lte=business_date) & (
                Q(enrollment_assignments__valid_to__isnull=True)
                | Q(enrollment_assignments__valid_to__gt=business_date)
            )
        queryset = queryset.filter(assignment)
    if existing_specialist_id:
        queryset = SpecialistProfile.objects.filter(
            Q(pk__in=queryset) | Q(pk=existing_specialist_id)
        )
    return queryset.distinct()


def _validate_enrollment_has_assignment(form, cleaned_data, date_field: str):
    enrollment = cleaned_data.get("enrollment")
    business_date = cleaned_data.get(date_field)
    if (
        enrollment
        and business_date
        and not enrollment.specialist_assignments.filter(
            valid_from__lte=business_date,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=business_date))
        .exists()
    ):
        form.add_error(
            "enrollment",
            _("The enrollment has no specialist assignment effective on the selected date."),
        )
    return cleaned_data


class ServiceVisitForm(StyledModelForm):
    correction_reason = forms.CharField(
        required=False,
        max_length=240,
        label=_("Correction reason"),
        help_text=_("Required when changing an existing visit."),
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    class Meta:
        model = ServiceVisit
        fields = (
            "enrollment",
            "specialist",
            "visit_date",
            "activity",
            "delivery_location",
            "participation_format",
            "status",
            "service_units",
            "duration_minutes",
            "participants",
            "cancellation_reason",
            "notes",
            "goals_worked_on",
        )
        widgets = {
            "visit_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, user, center, **kwargs):
        self.user = user
        self.center = center
        super().__init__(*args, **kwargs)
        is_edit = not self.instance._state.adding
        if self.is_bound and self.data.get("visit_type") and not self.data.get("activity"):
            legacy_type = self.data.get("visit_type")
            location_codes = {
                "center_visit": "CENTER",
                "home_visit": "HOME",
                "school_visit": "SCHOOL",
                "hospital_visit": "HOSPITAL",
                "community_outreach": "COMMUNITY",
                "remote_session": "REMOTE",
                "group_session": "CENTER",
                "case_conference": "CENTER",
                "other": "OTHER",
            }
            activity_code = (
                "GROUP-MEETING" if legacy_type == "group_session" else "INDIVIDUAL-MEETING"
            )
            activity = ServiceActivityDefinition.objects.filter(code=activity_code).first()
            location = VisitLocationDefinition.objects.filter(
                code=location_codes.get(legacy_type, "OTHER")
            ).first()
            data = self.data.copy()
            if activity:
                data["activity"] = str(activity.pk)
            if location:
                data["delivery_location"] = str(location.pk)
            data["participation_format"] = (
                "group" if legacy_type == "group_session" else "individual"
            )
            data.setdefault("participants", "2" if legacy_type == "group_session" else "1")
            self.data = data
        enrollment_queryset = enrollments_for_user(user, center)
        if is_edit:
            enrollment_queryset = ServiceEnrollment.objects.filter(
                Q(pk__in=enrollment_queryset) | Q(pk=self.instance.enrollment_id)
            )
        self.fields["enrollment"].queryset = enrollment_queryset
        _apply_legacy_beneficiary_enrollment(self, enrollment_queryset)
        selected_enrollment_id = (
            self.data.get("enrollment")
            if self.is_bound
            else self.instance.enrollment_id or self.initial.get("enrollment")
        )
        selected_enrollment = enrollment_queryset.filter(pk=selected_enrollment_id).first()
        goal_queryset = IndividualPlanGoal.objects.filter(
            plan__in=plans_for_user(user, center),
        ).select_related("category", "plan")
        if selected_enrollment:
            goal_queryset = goal_queryset.filter(plan__enrollment=selected_enrollment)
        if is_edit:
            goal_queryset = IndividualPlanGoal.objects.filter(
                Q(pk__in=goal_queryset) | Q(service_visits=self.instance)
            )
        self.fields["goals_worked_on"].queryset = goal_queryset.distinct()
        activity_queryset = ServiceActivityDefinition.objects.filter(is_active=True)
        if selected_enrollment:
            activity_queryset = activity_queryset.filter(
                Q(applicable_services__isnull=True)
                | Q(applicable_services=selected_enrollment.service)
            )
        if is_edit and self.instance.activity_id:
            activity_queryset = ServiceActivityDefinition.objects.filter(
                Q(pk__in=activity_queryset) | Q(pk=self.instance.activity_id)
            )
        self.fields["activity"].queryset = activity_queryset.distinct()
        location_queryset = VisitLocationDefinition.objects.filter(is_active=True)
        if is_edit and self.instance.delivery_location_id:
            location_queryset = VisitLocationDefinition.objects.filter(
                Q(pk__in=location_queryset) | Q(pk=self.instance.delivery_location_id)
            )
        self.fields["delivery_location"].queryset = location_queryset.distinct()
        if is_system_manager(user) or is_coordinator(user):
            self.fields["specialist"].queryset = _specialists_for_record(
                center=center,
                enrollment=selected_enrollment,
                business_date=_record_business_date(self, "visit_date"),
                existing_specialist_id=self.instance.specialist_id if is_edit else None,
            )
        else:
            profile = specialist_profile_for_user(user)
            self.fields["specialist"].queryset = _specialists_for_record(
                center=center,
                enrollment=selected_enrollment,
                business_date=_record_business_date(self, "visit_date"),
                existing_specialist_id=self.instance.specialist_id if is_edit else None,
            ).filter(
                pk__in={
                    getattr(profile, "pk", None),
                    self.instance.specialist_id if is_edit else None,
                }
            )
            if profile and not is_edit:
                self.initial["specialist"] = profile
        if is_edit:
            self.fields["correction_reason"].required = True
        else:
            self.fields.pop("correction_reason")

    def clean(self):
        cleaned = super().clean()
        allowed_statuses = {ServiceEnrollment.Status.ACTIVE}
        if cleaned.get("status") == ServiceVisit.Status.PLANNED:
            allowed_statuses.add(ServiceEnrollment.Status.PENDING)
        cleaned = _validate_actor_assignment(
            self,
            cleaned,
            "visit_date",
            allowed_statuses=allowed_statuses,
        )
        enrollment = cleaned.get("enrollment")
        goals = cleaned.get("goals_worked_on")
        if enrollment and goals and goals.exclude(plan__enrollment=enrollment).exists():
            self.add_error(
                "goals_worked_on",
                _("Every selected goal must belong to the visit enrollment."),
            )
        return cleaned


class EnrollmentServiceScheduleForm(StyledModelForm):
    schedule_month = forms.DateField(
        input_formats=["%Y-%m"],
        widget=forms.DateInput(format="%Y-%m", attrs={"type": "month"}),
        label=_("Schedule month"),
    )

    class Meta:
        model = EnrollmentServiceSchedule
        fields = (
            "enrollment",
            "schedule_month",
            "activity",
            "delivery_location",
            "participation_format",
            "planned_visits",
            "planned_units",
            "expected_participants",
            "notes",
        )
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, user, center, enrollment=None, **kwargs):
        self.user = user
        self.center = center
        super().__init__(*args, **kwargs)
        is_edit = not self.instance._state.adding
        enrollment_queryset = enrollments_for_user(user, center)
        if is_edit:
            enrollment_queryset = ServiceEnrollment.objects.filter(
                Q(pk__in=enrollment_queryset) | Q(pk=self.instance.enrollment_id)
            )
        if enrollment is not None:
            enrollment_queryset = enrollment_queryset.filter(pk=enrollment.pk)
            self.initial["enrollment"] = enrollment
        self.fields["enrollment"].queryset = enrollment_queryset
        selected_id = (
            self.data.get("enrollment")
            if self.is_bound
            else self.instance.enrollment_id or getattr(enrollment, "pk", None)
        )
        selected = enrollment_queryset.filter(pk=selected_id).first()
        activities = ServiceActivityDefinition.objects.filter(is_active=True)
        if selected:
            activities = activities.filter(
                Q(applicable_services__isnull=True) | Q(applicable_services=selected.service)
            )
        if is_edit:
            activities = ServiceActivityDefinition.objects.filter(
                Q(pk__in=activities) | Q(pk=self.instance.activity_id)
            )
        self.fields["activity"].queryset = activities.distinct()
        locations = VisitLocationDefinition.objects.filter(is_active=True)
        if is_edit:
            locations = VisitLocationDefinition.objects.filter(
                Q(pk__in=locations) | Q(pk=self.instance.delivery_location_id)
            )
        self.fields["delivery_location"].queryset = locations.distinct()

    def clean(self):
        cleaned = _validate_actor_assignment(self, super().clean(), "schedule_month")
        return _validate_enrollment_has_assignment(self, cleaned, "schedule_month")


class AssessmentForm(StyledModelForm):
    class Meta:
        model = Assessment
        exclude = (
            "center",
            "assessment_cycle_number",
            "beneficiary",
            "scoring_tool",
        )
        widgets = {
            "assessment_date": forms.DateInput(attrs={"type": "date"}),
            "next_review_date": forms.DateInput(attrs={"type": "date"}),
            "progress_summary": forms.Textarea(attrs={"rows": 3}),
            "recommendations": forms.Textarea(attrs={"rows": 4}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, user, center, **kwargs):
        self.user = user
        self.center = center
        super().__init__(*args, **kwargs)
        enrollment_queryset = enrollments_for_user(user, center)
        if self.instance.pk:
            enrollment_queryset = ServiceEnrollment.objects.filter(
                Q(pk__in=enrollment_queryset) | Q(pk=self.instance.enrollment_id)
            )
        self.fields["enrollment"].queryset = enrollment_queryset
        _apply_legacy_beneficiary_enrollment(self, enrollment_queryset)
        selected_enrollment_id = (
            self.data.get("enrollment")
            if self.is_bound
            else self.instance.enrollment_id or self.initial.get("enrollment")
        )
        selected_enrollment = enrollment_queryset.filter(pk=selected_enrollment_id).first()
        assessment_date = _record_business_date(self, "assessment_date")
        template_queryset = AssessmentTemplateVersion.objects.filter(
            status=AssessmentTemplateVersion.Status.PUBLISHED,
            instrument__is_active=True,
        ).select_related("instrument")
        if selected_enrollment:
            template_queryset = template_queryset.filter(
                Q(applicable_services__isnull=True)
                | Q(applicable_services=selected_enrollment.service)
            )
        if assessment_date:
            template_queryset = template_queryset.filter(
                Q(effective_from__isnull=True) | Q(effective_from__lte=assessment_date),
                Q(effective_to__isnull=True) | Q(effective_to__gt=assessment_date),
            )
        if self.instance.pk:
            template_queryset = AssessmentTemplateVersion.objects.filter(
                Q(pk__in=template_queryset) | Q(pk=self.instance.template_version_id)
            ).select_related("instrument")
        self.fields["template_version"].queryset = template_queryset.distinct()
        selected_template_id = (
            self.data.get("template_version")
            if self.is_bound
            else self.instance.template_version_id or self.initial.get("template_version")
        )
        try:
            selected_template = (
                self.fields["template_version"].queryset.filter(pk=selected_template_id).first()
            )
        except (TypeError, ValueError, ValidationError):
            selected_template = None
        previous_queryset = assessments_for_user(user, center).filter(
            status=Assessment.Status.COMPLETED
        )
        if selected_enrollment:
            previous_queryset = previous_queryset.filter(enrollment=selected_enrollment)
        if selected_template:
            previous_queryset = previous_queryset.filter(
                template_version__instrument__lineage_code=(
                    selected_template.instrument.lineage_code
                )
            )
        if assessment_date:
            previous_queryset = previous_queryset.filter(assessment_date__lte=assessment_date)
        self.fields["previous_assessment"].queryset = previous_queryset.exclude(
            pk=self.instance.pk
        ).distinct()
        if is_system_manager(user) or is_coordinator(user):
            specialist_queryset = _specialists_for_record(
                center=center,
                enrollment=selected_enrollment,
                business_date=assessment_date,
                existing_specialist_id=(self.instance.specialist_id if self.instance.pk else None),
            )
        else:
            profile = specialist_profile_for_user(user)
            specialist_queryset = _specialists_for_record(
                center=center,
                enrollment=selected_enrollment,
                business_date=assessment_date,
                existing_specialist_id=(self.instance.specialist_id if self.instance.pk else None),
            ).filter(
                pk__in={
                    getattr(profile, "pk", None),
                    self.instance.specialist_id if self.instance.pk else None,
                }
            )
            if profile and not self.instance.pk:
                self.initial["specialist"] = profile
        self.fields["specialist"].queryset = specialist_queryset
        self.fields["responsible_specialists"].queryset = specialist_queryset
        self.fields["responsible_specialists"].required = False
        if self.instance.pk and self.instance.status != Assessment.Status.DRAFT:
            for field_name in (
                "enrollment",
                "specialist",
                "assessment_date",
                "assessment_type",
                "previous_assessment",
                "template_version",
                "responsible_specialists",
            ):
                self.fields[field_name].disabled = True

    def clean(self):
        return _validate_actor_assignment(self, super().clean(), "assessment_date")


class AssessmentResponseEntryForm(StyledForm):
    template_field = forms.ModelChoiceField(
        queryset=AssessmentTemplateField.objects.none(),
        widget=forms.HiddenInput,
    )
    state = forms.ChoiceField(choices=AssessmentResponse.State.choices)
    value = forms.CharField(required=False)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, template_field=None, assessment=None, **kwargs):
        self.configured_field = template_field
        self.assessment = assessment
        super().__init__(*args, **kwargs)
        if template_field is None:
            return
        self.fields["template_field"].queryset = AssessmentTemplateField.objects.filter(
            pk=template_field.pk
        )
        self.fields["value"].label = template_field.label
        self.fields["value"].help_text = template_field.help_text
        response_type = template_field.response_type
        if response_type in {
            AssessmentTemplateField.ResponseType.NUMERIC_SCORE,
            AssessmentTemplateField.ResponseType.PERCENTAGE,
        }:
            self.fields["value"] = forms.DecimalField(
                required=False,
                min_value=template_field.minimum_value,
                max_value=template_field.maximum_value,
                step_size=template_field.value_increment,
                label=template_field.label,
                help_text=template_field.help_text,
            )
        elif response_type == AssessmentTemplateField.ResponseType.CHOICE:
            self.fields["value"] = forms.ChoiceField(
                required=False,
                choices=[("", _("Select"))]
                + [(choice, choice) for choice in template_field.allowed_choices],
                label=template_field.label,
                help_text=template_field.help_text,
            )
        elif response_type in {
            AssessmentTemplateField.ResponseType.ASSESSED_NOT_ASSESSED,
            AssessmentTemplateField.ResponseType.NOT_APPLICABLE,
        }:
            self.fields["value"] = forms.CharField(
                required=False,
                widget=forms.HiddenInput,
                label=template_field.label,
            )
        else:
            self.fields["value"] = forms.CharField(
                required=False,
                widget=forms.Textarea(attrs={"rows": 2}),
                label=template_field.label,
                help_text=template_field.help_text,
            )
        state_choices = [(AssessmentResponse.State.ASSESSED, _("Assessed"))]
        if (
            template_field.allow_not_assessed
            or response_type == AssessmentTemplateField.ResponseType.ASSESSED_NOT_ASSESSED
        ):
            state_choices.append((AssessmentResponse.State.NOT_ASSESSED, _("Not assessed")))
        if (
            template_field.allow_not_applicable
            or response_type == AssessmentTemplateField.ResponseType.NOT_APPLICABLE
        ):
            state_choices.append((AssessmentResponse.State.NOT_APPLICABLE, _("Not applicable")))
        self.fields["state"].choices = state_choices
        if response_type == AssessmentTemplateField.ResponseType.NOT_APPLICABLE:
            self.initial["state"] = AssessmentResponse.State.NOT_APPLICABLE
            self.fields["state"].disabled = True
        if assessment and assessment.status != Assessment.Status.DRAFT:
            for field in self.fields.values():
                field.disabled = True

    def clean(self):
        cleaned = super().clean()
        template_field = cleaned.get("template_field")
        state = cleaned.get("state")
        if not template_field or not state:
            return cleaned
        value = cleaned.get("value")
        response = AssessmentResponse(
            template_field=template_field,
            state=state,
            notes=cleaned.get("notes", ""),
        )
        if template_field.response_type in {
            AssessmentTemplateField.ResponseType.NUMERIC_SCORE,
            AssessmentTemplateField.ResponseType.PERCENTAGE,
        }:
            response.numeric_value = value
        elif template_field.response_type == AssessmentTemplateField.ResponseType.CHOICE:
            response.choice_value = value or ""
        elif template_field.response_type == AssessmentTemplateField.ResponseType.TEXT:
            response.text_value = value or ""
        try:
            response.clean()
        except ValidationError as exc:
            field_map = {
                "numeric_value": "value",
                "text_value": "value",
                "choice_value": "value",
                "state": "state",
            }
            if hasattr(exc, "error_dict"):
                for field_name, errors in exc.error_dict.items():
                    target = field_map.get(field_name)
                    for error in errors:
                        self.add_error(target, error)
            else:
                self.add_error(None, exc)
            return cleaned
        if (
            template_field.is_required
            and state == AssessmentResponse.State.ASSESSED
            and template_field.response_type
            in {
                AssessmentTemplateField.ResponseType.CHOICE,
                AssessmentTemplateField.ResponseType.TEXT,
            }
            and not value
        ):
            self.add_error("value", _("A response is required."))
        cleaned["response_payload"] = {
            "template_field": template_field,
            "state": state,
            "numeric_value": response.numeric_value,
            "text_value": response.text_value,
            "choice_value": response.choice_value,
            "notes": response.notes,
        }
        return cleaned


class BaseAssessmentResponseFormSet(BaseFormSet):
    def __init__(self, *args, template_version=None, assessment=None, **kwargs):
        self.template_version = template_version
        self.assessment = assessment
        self.template_fields = list(
            template_version.fields.select_related("section").order_by(
                "section__display_order", "display_order", "created_at"
            )
            if template_version
            else []
        )
        if not args or args[0] is None:
            existing = (
                {response.template_field_id: response for response in assessment.responses.all()}
                if assessment and assessment.pk
                else {}
            )
            initial = []
            for template_field in self.template_fields:
                response = existing.get(template_field.pk)
                value = ""
                state = AssessmentResponse.State.ASSESSED
                notes = ""
                if response:
                    state = response.state
                    notes = response.notes
                    if response.numeric_value is not None:
                        value = response.numeric_value
                    elif response.choice_value:
                        value = response.choice_value
                    else:
                        value = response.text_value
                elif (
                    template_field.response_type
                    == AssessmentTemplateField.ResponseType.NOT_APPLICABLE
                ):
                    state = AssessmentResponse.State.NOT_APPLICABLE
                initial.append(
                    {
                        "template_field": template_field,
                        "state": state,
                        "value": value,
                        "notes": notes,
                    }
                )
            kwargs["initial"] = initial
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        if index is not None and index < len(self.template_fields):
            kwargs["template_field"] = self.template_fields[index]
        kwargs["assessment"] = self.assessment
        return kwargs

    def clean(self):
        if any(self.errors) or not self.template_version:
            return
        expected = [field.pk for field in self.template_fields]
        received = [
            form.cleaned_data["template_field"].pk
            for form in self.forms
            if form.cleaned_data.get("template_field")
        ]
        if received != expected:
            raise ValidationError(_("Responses must match the selected template fields."))

    @property
    def response_payloads(self):
        return [
            form.cleaned_data["response_payload"]
            for form in self.forms
            if form.cleaned_data.get("response_payload")
        ]


AssessmentResponseFormSet = formset_factory(
    AssessmentResponseEntryForm,
    formset=BaseAssessmentResponseFormSet,
    extra=0,
)


class DomainScoreForm(StyledModelForm):
    class Meta:
        model = AssessmentDomainScore
        fields = ("domain", "baseline_score", "current_score", "progress_notes")
        widgets = {"progress_notes": forms.Textarea(attrs={"rows": 2})}


class RequiredDomainScoreFormSet(BaseInlineFormSet):
    def clean(self) -> None:
        super().clean()
        if any(self.errors):
            return
        active = [
            form
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE", False)
        ]
        if not active:
            raise ValidationError(_("At least one domain score is required."))


AssessmentDomainScoreFormSet = inlineformset_factory(
    Assessment,
    AssessmentDomainScore,
    form=DomainScoreForm,
    formset=RequiredDomainScoreFormSet,
    fields=("domain", "baseline_score", "current_score", "progress_notes"),
    extra=3,
    can_delete=True,
)


class IndividualPlanForm(StyledModelForm):
    class Meta:
        model = IndividualPlan
        exclude = ("center", "beneficiary")
        widgets = {
            "plan_start_date": forms.DateInput(attrs={"type": "date"}),
            "plan_end_date": forms.DateInput(attrs={"type": "date"}),
            "review_due_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, user, center, **kwargs):
        self.user = user
        self.center = center
        super().__init__(*args, **kwargs)
        enrollment_queryset = enrollments_for_user(user, center)
        if self.instance.pk:
            enrollment_queryset = ServiceEnrollment.objects.filter(
                Q(pk__in=enrollment_queryset) | Q(pk=self.instance.enrollment_id)
            )
        self.fields["enrollment"].queryset = enrollment_queryset
        _apply_legacy_beneficiary_enrollment(self, enrollment_queryset)
        selected_enrollment_id = (
            self.data.get("enrollment")
            if self.is_bound
            else self.instance.enrollment_id or self.initial.get("enrollment")
        )
        selected_enrollment = enrollment_queryset.filter(pk=selected_enrollment_id).first()
        if is_system_manager(user) or is_coordinator(user):
            self.fields["specialist"].queryset = _specialists_for_record(
                center=center,
                enrollment=selected_enrollment,
                business_date=_record_business_date(self, "plan_start_date"),
                existing_specialist_id=(self.instance.specialist_id if self.instance.pk else None),
            )
        else:
            profile = specialist_profile_for_user(user)
            self.fields["specialist"].queryset = _specialists_for_record(
                center=center,
                enrollment=selected_enrollment,
                business_date=_record_business_date(self, "plan_start_date"),
                existing_specialist_id=(self.instance.specialist_id if self.instance.pk else None),
            ).filter(
                pk__in={
                    getattr(profile, "pk", None),
                    self.instance.specialist_id if self.instance.pk else None,
                }
            )
            if profile and not self.instance.pk:
                self.initial["specialist"] = profile

    def clean(self):
        return _validate_actor_assignment(self, super().clean(), "plan_start_date")


class IndividualPlanGoalForm(StyledModelForm):
    status_change_date = forms.DateField(
        required=False,
        label=_("Status change date"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    status_change_reason = forms.CharField(
        required=False,
        label=_("Status change reason"),
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    class Meta:
        model = IndividualPlanGoal
        fields = (
            "category",
            "goal",
            "baseline",
            "measurable_target",
            "measurement_type",
            "measurement_unit_or_scale",
            "responsible_specialist",
            "target_date",
            "status",
            "achieved_date",
            "evidence",
            "progress_notes",
            "assessment_findings",
        )
        widgets = {
            "goal": forms.Textarea(attrs={"rows": 2}),
            "baseline": forms.Textarea(attrs={"rows": 2}),
            "measurable_target": forms.Textarea(attrs={"rows": 2}),
            "target_date": forms.DateInput(attrs={"type": "date"}),
            "achieved_date": forms.DateInput(attrs={"type": "date"}),
            "evidence": forms.Textarea(attrs={"rows": 2}),
            "progress_notes": forms.Textarea(attrs={"rows": 2}),
            "assessment_findings": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, user=None, center=None, plan=None, **kwargs):
        self.user = user
        self.center = center
        self.plan = plan
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial.setdefault("status_change_date", date.today())
        effective_plan = plan
        if effective_plan is None and self.instance.plan_id:
            effective_plan = self.instance.plan
        service_id = (
            effective_plan.enrollment.service_id
            if effective_plan is not None and effective_plan.enrollment_id
            else None
        )
        categories = GoalCategory.objects.filter(is_active=True)
        if service_id:
            categories = categories.filter(
                Q(applicable_services__isnull=True) | Q(applicable_services=service_id)
            )
        if self.instance.pk:
            categories = GoalCategory.objects.filter(
                Q(pk__in=categories) | Q(pk=self.instance.category_id)
            )
        self.fields["category"].queryset = categories.distinct()

        if center is not None:
            specialists = specialists_for_center(center)
            if effective_plan is not None and effective_plan.enrollment_id:
                specialists = _specialists_for_record(
                    center=center,
                    enrollment=effective_plan.enrollment,
                    business_date=(
                        self.data.get("target_date")
                        if self.is_bound
                        else self.instance.target_date or effective_plan.plan_start_date
                    ),
                    existing_specialist_id=(
                        self.instance.responsible_specialist_id if self.instance.pk else None
                    ),
                )
            self.fields["responsible_specialist"].queryset = specialists
        if effective_plan is not None and not self.instance.pk:
            self.initial.setdefault("responsible_specialist", effective_plan.specialist_id)

        assessments = Assessment.objects.none()
        if user is not None and center is not None:
            assessments = assessments_for_user(user, center)
        elif effective_plan is not None:
            assessments = Assessment.objects.all()
        if effective_plan is not None and effective_plan.enrollment_id:
            assessments = assessments.filter(enrollment=effective_plan.enrollment)
        if self.instance.pk:
            assessments = Assessment.objects.filter(
                Q(pk__in=assessments) | Q(linked_plan_goals=self.instance)
            )
        self.fields["assessment_findings"].queryset = assessments.distinct()

    def clean(self):
        cleaned = super().clean()
        effective_plan = self.plan
        if effective_plan is None and self.instance.plan_id:
            effective_plan = self.instance.plan
        assessments = cleaned.get("assessment_findings")
        if (
            effective_plan is not None
            and effective_plan.enrollment_id
            and assessments
            and assessments.exclude(enrollment=effective_plan.enrollment).exists()
        ):
            self.add_error(
                "assessment_findings",
                _("Every assessment finding must belong to the plan enrollment."),
            )
        old_status = None
        if self.instance.pk:
            old_status = (
                IndividualPlanGoal.objects.filter(pk=self.instance.pk)
                .values_list("status", flat=True)
                .first()
            )
        new_status = cleaned.get("status")
        status_change_date = cleaned.get("status_change_date")
        if (
            status_change_date
            and effective_plan is not None
            and effective_plan.plan_start_date
            and status_change_date < effective_plan.plan_start_date
        ):
            self.add_error(
                "status_change_date",
                _("Status change date cannot be before the plan start date."),
            )
        if (
            old_status != new_status
            and new_status
            in {
                IndividualPlanGoal.Status.DEFERRED,
                IndividualPlanGoal.Status.CANCELLED,
            }
            and not cleaned.get("status_change_reason", "").strip()
        ):
            self.add_error(
                "status_change_reason",
                _("A reason is required for a deferred or cancelled goal."),
            )
        return cleaned


IndividualPlanGoalFormSet = inlineformset_factory(
    IndividualPlan,
    IndividualPlanGoal,
    form=IndividualPlanGoalForm,
    fields=(
        "category",
        "goal",
        "baseline",
        "measurable_target",
        "measurement_type",
        "measurement_unit_or_scale",
        "responsible_specialist",
        "target_date",
        "status",
        "achieved_date",
        "evidence",
        "progress_notes",
        "assessment_findings",
    ),
    extra=3,
    can_delete=False,
)


def validate_plan_goals(form: IndividualPlanForm, formset) -> None:
    if form.cleaned_data.get("status") not in {
        IndividualPlan.Status.ACTIVE,
        IndividualPlan.Status.COMPLETED,
    }:
        return
    active = [
        row
        for row in formset.forms
        if row.cleaned_data and not row.cleaned_data.get("DELETE", False)
    ]
    if not active:
        raise ValidationError(_("At least one goal is required for an active or completed plan."))


class GoalOutcomeMeasurementForm(StyledModelForm):
    class Meta:
        model = GoalOutcomeMeasurement
        exclude = ("goal", "recorded_by")
        widgets = {
            "measurement_date": forms.DateInput(attrs={"type": "date"}),
            "interpretation": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, user, center, goal, **kwargs):
        self.user = user
        self.center = center
        self.goal = goal
        super().__init__(*args, **kwargs)
        self.instance.goal = goal
        self.fields["source_assessment"].queryset = assessments_for_user(user, center).filter(
            enrollment=goal.plan.enrollment
        )

    def clean(self):
        cleaned = super().clean()
        measurement_date = cleaned.get("measurement_date")
        if measurement_date and not can_create_case_record(
            self.user,
            self.center,
            self.goal.plan.enrollment,
            measurement_date,
        ):
            self.add_error(
                "measurement_date",
                _("Your assignment is not effective on the selected record date."),
            )
        return cleaned


class IndividualPlanReviewForm(StyledModelForm):
    class Meta:
        model = IndividualPlanReview
        exclude = ("plan", "recorded_by")
        widgets = {
            "review_date": forms.DateInput(attrs={"type": "date"}),
            "rationale": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user, center, plan, **kwargs):
        self.user = user
        self.center = center
        self.plan = plan
        super().__init__(*args, **kwargs)
        self.instance.plan = plan
        self.fields["source_assessment"].queryset = assessments_for_user(user, center).filter(
            enrollment=plan.enrollment
        )

    def clean(self):
        cleaned = super().clean()
        review_date = cleaned.get("review_date")
        if review_date and not can_create_case_record(
            self.user,
            self.center,
            self.plan.enrollment,
            review_date,
        ):
            self.add_error(
                "review_date",
                _("Your assignment is not effective on the selected record date."),
            )
        return cleaned
