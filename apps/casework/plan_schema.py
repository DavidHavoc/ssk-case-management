"""Selectable care activities transcribed from the owner's blank plan template."""

from django.core.exceptions import ValidationError
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _

# Stable codes keep stored selections independent of wording and UI language.
ACTIVITY_GROUPS = (
    (
        "nursing",
        "Nursing",
        "საექთნო",
        (
            ("prevention", "Prevention", "პროფილაქტიკები"),
            ("procedures", "Procedures", "პროცედურები"),
            ("vital_signs", "Vital signs monitoring", "სასიცოცხლო მაჩვენებლების კონტროლი"),
            ("teaching", "Teaching", "სწავლება"),
            ("other", "Other", "სხვა"),
        ),
    ),
    (
        "basic_care",
        "Basic care",
        "ძირეული მოვლა",
        (
            ("full_bathing", "Full bathing", "მთლიანი დაბანა"),
            ("partial_bathing", "Partial bathing", "ნაწილობრივი დაბანა"),
            ("face_care", "Face care", "სახის მოვლა"),
            ("nail_care", "Nail care", "ფრჩხილების მოვლა"),
            ("bed_care", "Bed care", "ლოგინის მოვლა"),
            ("mobilization", "Mobilization", "მობილიზაცია"),
            ("elimination", "Elimination", "გამოყოფა"),
            ("feeding", "Feeding", "კვება"),
            ("other", "Other", "სხვა"),
        ),
    ),
    (
        "household",
        "Household support",
        "საყოფაცხოვრებო",
        (
            ("shopping", "Shopping", "საყიდლები"),
            (
                "housework",
                "Cleaning, laundry, meal preparation",
                "დალაგება, გარეცხვა, საკვების მომზადება",
            ),
            ("home_adaptation", "Home adaptation", "ბინის ადაპტაცია"),
            (
                "material_support",
                "Material and technical assistance",
                "მატერიალურ-ტექნიკური დახმარება",
            ),
            ("other", "Other", "სხვა"),
        ),
    ),
    (
        "social",
        "Social support",
        "სოციალური",
        (
            ("psychosocial", "Psychosocial support", "ფსიქოსოციალური მხარდაჭერა"),
            (
                "legal_environment",
                "Legal and community assistance",
                "სამართლებრივი და გარემოში დახმარება",
            ),
            ("information", "Information and education", "საინფორმაციო-საგანმანათლებლო დახმარება"),
            ("other", "Other", "სხვა"),
        ),
    ),
    (
        "technical",
        "Technical assistance",
        "ტექნიკური",
        (
            (
                "equipment",
                "Check assistive equipment and help with its use",
                "დამხმარე ტექნიკური საშუალებების გამართულობის შემოწმება და გამოყენებაში დახმარება",
            ),
            (
                "home_help",
                "Minor technical help at home",
                "საცხოვრებელ გარემოში მცირე ტექნიკური დახმარება",
            ),
            (
                "safe_environment",
                "Help arrange a safe environment",
                "უსაფრთხო გარემოს მოწყობაში დახმარება",
            ),
            ("other", "Other", "სხვა"),
        ),
    ),
    (
        "personal_assistant",
        "Personal assistant",
        "პერსონალური ასისტენტი",
        (
            ("psychological", "Moral and psychological support", "მორალურ-ფსიქოლოგიური მხარდაჭერა"),
            (
                "legal_environment",
                "Legal and community assistance",
                "სამართლებრივი და გარემოში დახმარება",
            ),
            ("information", "Information and education", "საინფორმაციო-საგანმანათლებლო დახმარება"),
            ("other", "Other", "სხვა"),
        ),
    ),
)


def activity_catalog():
    ka = get_language() == "ka"
    return [
        {
            "code": f"{group}.{code}",
            "category": category_ka if ka else category_en,
            "activity": label_ka if ka else label_en,
            "needs_description": code == "other",
        }
        for group, category_en, category_ka, activities in ACTIVITY_GROUPS
        for code, label_en, label_ka in activities
    ]


def validate_interventions(value):
    catalog = {row["code"]: row for row in activity_catalog()}
    if not isinstance(value, list) or not value:
        raise ValidationError(_("Select at least one care activity."))
    seen = set()
    for row in value:
        if (
            not isinstance(row, dict)
            or set(row) != {"code", "notes"}
            or not isinstance(row["code"], str)
            or row["code"] not in catalog
            or row["code"] in seen
            or not isinstance(row["notes"], str)
            or len(row["notes"]) > 2000
        ):
            raise ValidationError(_("Select valid care activities and notes."))
        seen.add(row["code"])
        if catalog[row["code"]]["needs_description"] and not row["notes"].strip():
            raise ValidationError(_("Describe the selected Other activity in Notes."))


def intervention_table(value):
    selected = {row["code"]: row["notes"] for row in value}
    return [
        {**row, "notes": selected[row["code"]]}
        for row in activity_catalog()
        if row["code"] in selected
    ]
