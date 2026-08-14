from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils.translation import gettext_lazy as _

from apps.accounts.roles import is_coordinator, is_system_manager
from apps.centers.models import SpecialistProfile
from apps.core.authorization import (
    assessments_for_user,
    beneficiaries_for_user,
    specialist_profile_for_user,
    specialists_for_center,
)
from apps.core.forms import StyledModelForm

from .models import (
    Assessment,
    AssessmentDomainScore,
    Beneficiary,
    BeneficiarySpecialistAssignment,
    IndividualPlan,
    IndividualPlanGoal,
    PrivateAttachment,
    ServiceVisit,
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
        exclude = ("center", "specialists")
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "first_assessment_date": forms.DateInput(attrs={"type": "date"}),
            "enrollment_date": forms.DateInput(attrs={"type": "date"}),
            "first_service_date": forms.DateInput(attrs={"type": "date"}),
            "exit_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
            "diagnosis_status": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user, center, **kwargs):
        self.user = user
        self.center = center
        super().__init__(*args, **kwargs)
        if not (is_system_manager(user) or is_coordinator(user)):
            for field in RESTRICTED_BENEFICIARY_FIELDS:
                self.fields.pop(field, None)

    def save(self, commit=True):
        self.instance.center = self.center
        return super().save(commit=commit)


class BeneficiaryAssignmentForm(StyledModelForm):
    class Meta:
        model = BeneficiarySpecialistAssignment
        fields = ("specialist", "assignment_role", "from_date", "to_date")
        widgets = {
            "from_date": forms.DateInput(attrs={"type": "date"}),
            "to_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, center=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["specialist"].queryset = (
            specialists_for_center(center) if center else SpecialistProfile.objects.none()
        )


BeneficiaryAssignmentFormSet = inlineformset_factory(
    Beneficiary,
    BeneficiarySpecialistAssignment,
    form=BeneficiaryAssignmentForm,
    fields=("specialist", "assignment_role", "from_date", "to_date"),
    extra=3,
    can_delete=True,
)


class ServiceVisitForm(StyledModelForm):
    class Meta:
        model = ServiceVisit
        exclude = ("center", "visit_month")
        widgets = {
            "visit_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, user, center, **kwargs):
        self.user = user
        self.center = center
        super().__init__(*args, **kwargs)
        self.fields["beneficiary"].queryset = beneficiaries_for_user(user, center)
        if is_system_manager(user) or is_coordinator(user):
            self.fields["specialist"].queryset = specialists_for_center(center)
        else:
            profile = specialist_profile_for_user(user)
            self.fields["specialist"].queryset = SpecialistProfile.objects.filter(
                pk=getattr(profile, "pk", None)
            )
            if profile and not self.instance.pk:
                self.initial["specialist"] = profile

    def save(self, commit=True):
        self.instance.center = self.center
        return super().save(commit=commit)


class AssessmentForm(StyledModelForm):
    class Meta:
        model = Assessment
        exclude = ("center", "assessment_cycle_number")
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
        self.fields["beneficiary"].queryset = beneficiaries_for_user(user, center)
        self.fields["previous_assessment"].queryset = assessments_for_user(user, center)
        if is_system_manager(user) or is_coordinator(user):
            self.fields["specialist"].queryset = specialists_for_center(center)
        else:
            profile = specialist_profile_for_user(user)
            self.fields["specialist"].queryset = SpecialistProfile.objects.filter(
                pk=getattr(profile, "pk", None)
            )
            if profile and not self.instance.pk:
                self.initial["specialist"] = profile

    def save(self, commit=True):
        self.instance.center = self.center
        return super().save(commit=commit)


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
        exclude = ("center",)
        widgets = {
            "plan_start_date": forms.DateInput(attrs={"type": "date"}),
            "plan_end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, user, center, **kwargs):
        self.user = user
        self.center = center
        super().__init__(*args, **kwargs)
        self.fields["beneficiary"].queryset = beneficiaries_for_user(user, center)
        if is_system_manager(user) or is_coordinator(user):
            self.fields["specialist"].queryset = specialists_for_center(center)
        else:
            profile = specialist_profile_for_user(user)
            self.fields["specialist"].queryset = SpecialistProfile.objects.filter(
                pk=getattr(profile, "pk", None)
            )
            if profile and not self.instance.pk:
                self.initial["specialist"] = profile

    def save(self, commit=True):
        self.instance.center = self.center
        return super().save(commit=commit)


class IndividualPlanGoalForm(StyledModelForm):
    class Meta:
        model = IndividualPlanGoal
        fields = ("goal", "target_date", "status", "progress_notes")
        widgets = {
            "goal": forms.Textarea(attrs={"rows": 2}),
            "target_date": forms.DateInput(attrs={"type": "date"}),
            "progress_notes": forms.Textarea(attrs={"rows": 2}),
        }


IndividualPlanGoalFormSet = inlineformset_factory(
    IndividualPlan,
    IndividualPlanGoal,
    form=IndividualPlanGoalForm,
    fields=("goal", "target_date", "status", "progress_notes"),
    extra=3,
    can_delete=True,
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


class PrivateAttachmentForm(StyledModelForm):
    class Meta:
        model = PrivateAttachment
        fields = ("file",)
