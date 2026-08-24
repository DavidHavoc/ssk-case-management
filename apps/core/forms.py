from django import forms
from django.utils.translation import gettext_lazy as _

DAY_FIRST_DATE_FORMAT = "%d/%m/%Y"
DAY_FIRST_DATE_INPUT_FORMATS = (DAY_FIRST_DATE_FORMAT, "%Y-%m-%d")

FORM_FIELD_LABELS = {
    "achieved_date": _("Achieved date"),
    "activity": _("Activity"),
    "address": _("Address"),
    "application_contract_number": _("Application contract number"),
    "assessment_date": _("Assessment date"),
    "assessment_type": _("Assessment type"),
    "assessment_findings": _("Assessment findings"),
    "assignment_role": _("Assignment role"),
    "baseline_score": _("Baseline score"),
    "baseline": _("Baseline"),
    "beneficiary_code": _("Beneficiary code"),
    "birth_date": _("Birth date"),
    "cancellation_reason": _("Cancellation reason"),
    "category": _("Category"),
    "code": _("Code"),
    "contact_number": _("Contact number"),
    "condition_outcome": _("Child condition outcome"),
    "contract_signed_on": _("Contract signing date"),
    "contract_valid_until": _("Contract valid until"),
    "current_score": _("Current score"),
    "definition": _("Definition"),
    "delivery_location": _("Delivery location"),
    "description": _("Description"),
    "destination_offering": _("Destination service and center"),
    "domain": _("Domain"),
    "duration_minutes": _("Duration minutes"),
    "effective_date": _("Effective from"),
    "email": _("Email"),
    "evidence": _("Evidence"),
    "employee_number": _("Employee number"),
    "enrollment": _("Enrollment"),
    "episode_code": _("Enrollment code"),
    "expected_participants": _("Expected participants"),
    "family_status": _("Family status"),
    "first_name": _("First name"),
    "first_service_date": _("First service date"),
    "full_name": _("Full name"),
    "goal": _("Goal"),
    "goals_worked_on": _("Goals worked on"),
    "guardian_parent": _("Guardian or parent"),
    "is_active": _("Active"),
    "is_primary": _("Primary center"),
    "interpretation": _("Interpretation"),
    "job_title": _("Position"),
    "last_name": _("Last name"),
    "municipality_ref": _("Municipality"),
    "measurable_target": _("Measurable target"),
    "measurement_date": _("Measurement date"),
    "measurement_type": _("Measurement type"),
    "measurement_unit_or_scale": _("Measurement unit or scale"),
    "name": _("Name"),
    "next_review_date": _("Next review date"),
    "notes": _("Notes"),
    "numeric_value": _("Numeric value"),
    "offering": _("Service and center offering"),
    "participants": _("Participants"),
    "participation_format": _("Participation format"),
    "personal_id": _("Personal ID"),
    "phone": _("Phone"),
    "plan_end_date": _("Plan end date"),
    "plan_start_date": _("Plan start date"),
    "planned_units": _("Planned units"),
    "planned_visits": _("Planned visits"),
    "previous_assessment": _("Previous assessment"),
    "progress_notes": _("Progress notes"),
    "progress_summary": _("Progress summary"),
    "project_program": _("Project or program"),
    "reason": _("Reason"),
    "rating": _("Rating"),
    "rationale": _("Rationale"),
    "recommendations": _("Recommendations"),
    "recorded_on": _("Recorded on"),
    "region_ref": _("Region"),
    "review_frequency": _("Review frequency"),
    "review_date": _("Review date"),
    "review_due_date": _("Review due date"),
    "schedule_month": _("Schedule month"),
    "scoring_tool": _("Scoring tool"),
    "service_schedule_count": _("Service schedule count"),
    "service_units": _("Service units"),
    "sex": _("Sex"),
    "specialist": _("Specialist"),
    "responsible_specialist": _("Responsible specialist"),
    "source_assessment": _("Source assessment"),
    "start_date": _("Start date"),
    "status": _("Status"),
    "target_date": _("Target date"),
    "total_score": _("Total score"),
    "unit_or_scale": _("Unit or scale"),
    "username": _("Username"),
    "valid_from": _("Valid from"),
    "valid_to": _("Valid to"),
    "verification_status": _("Verification status"),
    "visible_to_specialists": _("Visible to specialists"),
    "visit_date": _("Visit date"),
}


class DayFirstDateInput(forms.DateInput):
    input_type = "text"

    def __init__(self, attrs=None, format=DAY_FIRST_DATE_FORMAT):
        attrs = {**(attrs or {})}
        attrs.pop("type", None)
        attrs.setdefault("placeholder", "DD/MM/YYYY")
        attrs.setdefault("inputmode", "numeric")
        super().__init__(attrs=attrs, format=format)


class StyledFormMixin:
    def apply_styles(self) -> None:
        for name, field in self.fields.items():
            if name in FORM_FIELD_LABELS and (field.label is None or isinstance(field.label, str)):
                field.label = FORM_FIELD_LABELS[name]
            if isinstance(field, forms.DateField) and isinstance(field.widget, forms.DateInput):
                if field.widget.input_type != "month":
                    field.input_formats = DAY_FIRST_DATE_INPUT_FORMATS
                    field.widget = DayFirstDateInput(attrs=field.widget.attrs)
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect)):
                css_class = "form-check-input"
            elif isinstance(widget, forms.Select):
                css_class = "form-select"
            else:
                css_class = "form-control"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css_class}".strip()
            if field.required:
                widget.attrs["aria-required"] = "true"
            bound_field = self[name]
            described_by = []
            if field.help_text and bound_field.id_for_label:
                described_by.append(f"{bound_field.id_for_label}-help")
            if described_by:
                widget.attrs["aria-describedby"] = " ".join(described_by)


class StyledModelForm(StyledFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()


class StyledForm(StyledFormMixin, forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()
