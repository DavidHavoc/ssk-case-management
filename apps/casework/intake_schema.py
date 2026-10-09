"""Stable reported intake choices, independent of language and clinical catalogs."""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

MULTI_CHOICES = {
    "general_conditions": (
        ("stable", _("Stable")),
        ("moderate", _("Moderate severity")),
        ("severe", _("Severe")),
        ("monitoring", _("Requires ongoing monitoring")),
        ("acute", _("Acute/deteriorating condition")),
    ),
    "health_problems": (
        ("chronic", _("Chronic disease")),
        ("cardiovascular", _("Cardiovascular problem")),
        ("diabetes", _("Diabetes")),
        ("respiratory", _("Respiratory/lung problem")),
        ("mobility", _("Movement/mobility limitation")),
        ("vision", _("Vision problem")),
        ("hearing", _("Hearing problem")),
        ("neurological", _("Neurological problem")),
        ("mental_cognitive", _("Mental/cognitive condition")),
        ("dementia", _("Signs/diagnosis of dementia")),
        ("depression_anxiety", _("Depression/anxiety")),
        ("other", _("Other")),
    ),
    "functional_conditions": (
        ("independent", _("Moves independently")),
        ("mobility_assistance", _("Needs assistance with mobility")),
        ("assistive_devices", _("Uses assistive devices (cane, wheelchair, walker, etc.)")),
        ("bedbound", _("Bedbound")),
        ("daily_assistance", _("Needs assistance with daily activities")),
        ("fully_dependent", _("Fully dependent on another person's assistance")),
    ),
    "cognitive_conditions": (
        ("oriented", _("Oriented and responsive")),
        ("confusion", _("Intermittent confusion")),
        ("memory", _("Memory impairment")),
        ("impairment", _("Significant cognitive impairment")),
        ("dementia", _("Dementia diagnosis")),
        ("other", _("Other")),
    ),
    "initial_care_services": (
        ("medical_nursing", _("Medical and nursing services")),
        ("basic_care", _("Basic care")),
        ("family_assistance", _("Assistance to the beneficiary and family")),
        ("social_support", _("Social support")),
        ("technical_assistance", _("Technical assistance")),
        ("household_assistance", _("Household assistance")),
        ("specialist_involvement", _("Specialist involvement")),
        ("food_service", _("Food service")),
    ),
}

YES_NO = (("", _("Unanswered")), ("yes", _("Yes")), ("no", _("No")))
ALLERGY_CHOICES = (
    ("", _("Unanswered")),
    ("yes", pgettext_lazy("allergies", "Yes")),
    ("no", _("No")),
)

LIVING_CHOICES = (
    ("", _("Unanswered")),
    ("alone", _("Lives alone")),
    ("family", _("Lives with family")),
    ("other", _("Other")),
)
MEDIA_CHOICES = (("", _("Unanswered")), ("agree", _("I agree")), ("decline", _("I do not agree")))

HEALTH_FIELDS = (
    "health_condition",
    "general_conditions",
    "health_problems",
    "health_problems_other",
    "functional_conditions",
    "cognitive_conditions",
    "cognitive_other",
    "allergies",
    "allergies_description",
    "current_medications",
    "treating_doctor_name",
    "treating_doctor_contact",
)
SOCIAL_FIELDS = (
    "other_services",
    "other_services_details",
    "living_situation",
    "living_situation_notes",
)
CONSENT_FIELDS = (
    "service_consent",
    "care_sharing_consent",
    "confidentiality_consent",
    "media_consent",
)
MEDIA_DECLARATION = (
    _("I, the undersigned, give my consent for the organization to:"),
    _("photograph and record video of me during events/services;"),
    _(
        "use this material for informational, educational, and public purposes, for example "
        "in reports, presentations, websites, social media, and other non-commercial platforms;"
    ),
    _("protect my personal data and confidentiality in accordance with applicable law."),
)
CARE_FIELDS = ("initial_care_services",)
INTAKE_FIELDS = HEALTH_FIELDS + SOCIAL_FIELDS + CONSENT_FIELDS + CARE_FIELDS


def validate_intake_values(values):
    errors = {}
    for name, choices in MULTI_CHOICES.items():
        if name not in values:
            continue
        selected = values[name]
        allowed = {code for code, label in choices}
        if not isinstance(selected, list) or any(
            not isinstance(code, str) or code not in allowed for code in selected
        ):
            errors[name] = _("Select valid intake options.")
        elif len(selected) != len(set(selected)):
            errors[name] = _("Select valid intake options.")
    for choice, detail, expected in (
        ("health_problems", "health_problems_other", "other"),
        ("cognitive_conditions", "cognitive_other", "other"),
        ("allergies", "allergies_description", "yes"),
        ("other_services", "other_services_details", "yes"),
    ):
        if choice not in values or choice in errors:
            continue
        answer = values[choice]
        selected = expected in answer if isinstance(answer, list) else answer == expected
        if selected and not values.get(detail, "").strip():
            errors[detail] = _("Please provide details for this answer.")
        elif not selected:
            values[detail] = ""
    if (
        values.get("living_situation") == "other"
        and not values.get("living_situation_notes", "").strip()
    ):
        errors["living_situation_notes"] = _("Please provide details for this answer.")
    if errors:
        raise ValidationError(errors)
