from __future__ import annotations

import secrets

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.accounts.roles import SPECIALIST, ensure_application_groups
from apps.core.forms import StyledForm, StyledModelForm

from .models import Center, SpecialistCenterAssignment, SpecialistProfile, StaffProfile

User = get_user_model()


class CenterForm(StyledModelForm):
    class Meta:
        model = Center
        fields = ("code", "name", "is_active", "phone", "email", "address", "description")
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "description": forms.Textarea(attrs={"rows": 4}),
        }


class SpecialistAssignmentForm(StyledModelForm):
    class Meta:
        model = SpecialistCenterAssignment
        fields = ("specialist", "is_primary")

    def __init__(self, *args, center, **kwargs):
        self.center = center
        super().__init__(*args, **kwargs)
        assigned = SpecialistCenterAssignment.objects.filter(center=center).values("specialist_id")
        self.fields["specialist"].queryset = (
            SpecialistProfile.objects.exclude(pk__in=assigned)
            .select_related("staff_profile__user")
            .order_by("staff_profile__user__last_name", "staff_profile__user__first_name")
        )

    def save(self, commit=True):
        self.instance.center = self.center
        return super().save(commit=commit)


class SpecialistProfileForm(StyledModelForm):
    class Meta:
        model = SpecialistProfile
        fields = ("description",)
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}


class NewSpecialistForm(StyledForm):
    username = forms.CharField(max_length=150, label=_("Username"))
    email = forms.EmailField(label=_("Email"))
    first_name = forms.CharField(max_length=150, label=_("First name"))
    last_name = forms.CharField(max_length=150, label=_("Last name"))
    employee_number = forms.CharField(max_length=40, label=_("Employee number"))
    job_title = forms.CharField(max_length=120, required=False, label=_("Job title"))
    description = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 4}), label=_("Specialist description")
    )
    is_primary = forms.BooleanField(required=False, label=_("Primary center"))

    def __init__(self, *args, center, **kwargs):
        self.center = center
        super().__init__(*args, **kwargs)

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip().lower()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError(_("A user with this username already exists."))
        return username

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(_("A user with this email already exists."))
        return email

    def clean_employee_number(self) -> str:
        number = self.cleaned_data["employee_number"].strip().upper()
        if StaffProfile.objects.filter(employee_number__iexact=number).exists():
            raise ValidationError(_("A staff profile with this employee number already exists."))
        return number

    @transaction.atomic
    def save(self) -> SpecialistProfile:
        ensure_application_groups()
        user = User.objects.create(
            username=self.cleaned_data["username"],
            email=self.cleaned_data["email"],
            first_name=self.cleaned_data["first_name"].strip(),
            last_name=self.cleaned_data["last_name"].strip(),
        )
        user.set_password(secrets.token_urlsafe(32))
        user.save(update_fields=["password"])
        user.groups.add(user.groups.model.objects.get(name=SPECIALIST))
        staff = StaffProfile.objects.create(
            user=user,
            employee_number=self.cleaned_data["employee_number"],
            job_title=self.cleaned_data["job_title"].strip(),
            primary_center=self.center if self.cleaned_data["is_primary"] else None,
        )
        staff.centers.add(self.center)
        profile = SpecialistProfile.objects.create(
            staff_profile=staff, description=self.cleaned_data["description"]
        )
        SpecialistCenterAssignment.objects.create(
            specialist=profile,
            center=self.center,
            is_primary=self.cleaned_data["is_primary"],
        )
        return profile
