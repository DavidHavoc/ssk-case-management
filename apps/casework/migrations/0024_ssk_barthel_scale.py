"""SSK supplied activities and owner-confirmed dependency/care bands, 2026-10-14."""

from django.db import migrations
from django.utils import timezone

VERSION = "ssk-20261014-1"
# Concise bilingual descriptions of the supplied Georgian scale. Scores are immutable.
ITEMS = (
    ("FEEDING", "Feeding", (
        (10, "Eats independently, including cutting food and using necessary aids.", "დამოუკიდებლად ჭამს, ჭრის საკვებს და იყენებს საჭირო დამხმარე საშუალებებს."),
        (5, "Needs some help with eating or preparing food on the plate.", "კვებისას საჭიროებს გარკვეულ დახმარებას."),
        (0, "Unable to eat independently.", "დამოუკიდებლად ვერ ჭამს."),
    )),
    ("BATHING", "Bathing", (
        (5, "Bathes or showers, or washes the whole body, without help.", "დახმარების გარეშე იყენებს აბაზანას ან შხაპს, ან იბანს მთელ სხეულს."),
        (0, "Needs help with bathing.", "დაბანისას საჭიროებს დახმარებას."),
    )),
    ("GROOMING", "Personal hygiene", (
        (5, "Washes hands and face, combs hair, brushes teeth, and shaves independently.", "დამოუკიდებლად იბანს ხელებსა და სახეს, ივარცხნის თმას, იხეხავს კბილებს და იპარსავს."),
        (0, "Needs help with personal hygiene.", "პირადი ჰიგიენისას საჭიროებს დახმარებას."),
    )),
    ("DRESSING", "Dressing and undressing", (
        (10, "Puts on, removes, and fastens clothing and necessary aids independently.", "დამოუკიდებლად იცვამს, იხდის და იკრავს ტანსაცმელსა და საჭირო დამხმარე საშუალებებს."),
        (5, "Needs help but completes at least half of dressing independently.", "ჩაცმისა და გახდისას საჭიროებს დახმარებას, თუმცა სამუშაოს ნახევარს თვითონ ასრულებს."),
        (0, "Unable to dress independently.", "დამოუკიდებლად ვერ იცვამს."),
    )),
    ("BOWELS", "Bowel control", (
        (10, "Controls bowels with no accidents.", "აკონტროლებს კუჭის მოქმედებას და არ აქვს შეუკავებლობის შემთხვევები."),
        (5, "Has occasional accidents or needs help managing bowel care.", "აქვს იშვიათი შეუკავებლობის შემთხვევები ან საჭიროებს დახმარებას."),
        (0, "Cannot control bowels and needs help.", "ვერ აკონტროლებს კუჭის მოქმედებას და საჭიროებს დახმარებას."),
    )),
    ("BLADDER", "Bladder control", (
        (10, "Controls bladder day and night and manages any urinary device independently.", "აკონტროლებს შარდვას დღისით და ღამით; საჭირო მოწყობილობას დამოუკიდებლად იყენებს და უვლის."),
        (5, "Has occasional accidents or needs help with urinary devices.", "აქვს იშვიათი შეუკავებლობის შემთხვევები ან საჭიროებს დახმარებას შარდვის მოწყობილობის გამოყენებისას."),
        (0, "Cannot control bladder or manage a catheter independently.", "ვერ აკონტროლებს შარდვას ან ვერ უვლის კათეტერს დამოუკიდებლად."),
    )),
    ("TOILET", "Toilet use", (
        (10, "Uses the toilet, handles clothing, and cleans up independently.", "დამოუკიდებლად იყენებს ტუალეტს, იხდის და იკრავს ტანსაცმელს და იცავს ჰიგიენას."),
        (5, "Needs help with balance, clothing, or hygiene but does part independently.", "სჭირდება დახმარება წონასწორობის შენარჩუნებაში, ტანსაცმელში ან ჰიგიენაში; ნაწილს თვითონ ასრულებს."),
        (0, "Unable to use the toilet independently.", "დამოუკიდებლად ვერ სარგებლობს ტუალეტით."),
    )),
    ("TRANSFER", "Bed and chair transfers", (
        (15, "Transfers safely between bed and chair, sits, and lies down independently.", "დამოუკიდებლად და უსაფრთხოდ გადადის ეტლიდან საწოლში და უკან, ჯდება და წვება."),
        (10, "Needs minimal physical help, reminders, or supervision during transfer.", "გადაადგილებისას სჭირდება მინიმალური ფიზიკური დახმარება, შეხსენება ან ზედამხედველობა."),
        (5, "Sits independently but needs substantial help to transfer.", "დამოუკიდებლად ჯდება, მაგრამ გადაადგილებისთვის სჭირდება მნიშვნელოვანი დახმარება."),
        (0, "Unable to transfer independently.", "დამოუკიდებლად ვერ გადაადგილდება საწოლსა და ეტლს შორის."),
    )),
    ("MOBILITY", "Walking or wheelchair mobility", (
        (15, "Walks at least 50 metres without help or supervision, with permitted aids if needed.", "დახმარებისა და ზედამხედველობის გარეშე გადის სულ მცირე 50 მეტრს, საჭიროებისას დასაშვები დამხმარე საშუალებით."),
        (10, "Walks at least 50 metres with another person's help or supervision.", "სხვისი დახმარებით ან ზედამხედველობით გადის სულ მცირე 50 მეტრს."),
        (5, "Cannot walk, but propels and manoeuvres a wheelchair independently for at least 50 metres.", "ვერ დადის, თუმცა დამოუკიდებლად მართავს ეტლს, უხვევს და გადის სულ მცირე 50 მეტრს."),
        (0, "Unable to walk or propel a wheelchair independently.", "დამოუკიდებლად ვერ დადის და ვერ მართავს ეტლს."),
    )),
    ("STAIRS", "Going up and down stairs", (
        (10, "Uses stairs safely without help or supervision, carrying necessary aids.", "უსაფრთხოდ ადის და ჩამოდის კიბეზე დახმარებისა და ზედამხედველობის გარეშე და თან ატარებს საჭირო დამხმარე საშუალებებს."),
        (5, "Needs physical or verbal help or supervision on stairs.", "კიბეზე ასვლისა და ჩამოსვლისას სჭირდება ფიზიკური ან ვერბალური დახმარება ან ზედამხედველობა."),
        (0, "Unable to use stairs.", "ვერ ადის და ვერ ჩამოდის კიბეზე."),
    )),
)
BANDS = (
    ("TOTAL", "Total dependency", 0, 20, "total", "very_high"),
    ("SEVERE", "Severe dependency", 21, 60, "severe", "high"),
    ("MODERATE", "Moderate dependency", 61, 90, "moderate", "moderate"),
    ("SLIGHT", "Slight dependency", 91, 99, "slight", "low"),
    ("INDEPENDENT", "Independent", 100, 100, "independent", "minimal"),
)


def install(apps, schema_editor):
    alias = schema_editor.connection.alias
    instrument, _ = apps.get_model("casework", "AssessmentInstrument").objects.using(alias).get_or_create(
        code="BARTHEL", defaults={"name": "Barthel", "identifier": "barthel", "lineage_code": "BARTHEL"}
    )
    template = apps.get_model("casework", "AssessmentTemplateVersion").objects.using(alias).create(
        instrument=instrument, version=VERSION, name="Barthel scale", status="published",
        scoring_method="sum", score_minimum=0, score_maximum=100, score_increment=1,
        comparison_group="SSK-BARTHEL-20261014", published_at=timezone.now(),
        publication_notes=(
            "Owner supplied Georgian activities and approved five bands on 2026-10-14: "
            "0-20 Total/Very High, 21-60 Severe/High, 61-90 Moderate/Moderate, "
            "91-99 Slight/Low, 100 Independent/Minimal. These supersede the screenshot categories. "
            "Item scores are multiples of five. A complete score is not a home-care intensity rule."
        ),
    )
    section = apps.get_model("casework", "AssessmentTemplateSection").objects.using(alias).create(
        template_version=template, code="ADL", name="Daily activities", display_order=1,
    )
    Field = apps.get_model("casework", "AssessmentTemplateField")
    for order, (code, label, choices) in enumerate(ITEMS, start=1):
        Field.objects.using(alias).create(
            section=section, code=code, label=label, response_type="scored_choice",
            display_order=order, is_required=True, minimum_value=0,
            maximum_value=max(score for score, _, _ in choices), value_increment=5,
            include_in_total=True,
            allowed_choices=[
                {"value": str(score), "score": score, "label": en, "label_ka": ka}
                for score, en, ka in choices
            ],
        )
    Band = apps.get_model("casework", "AssessmentScoreBand")
    for order, (code, label, lower, upper, dependency, need) in enumerate(BANDS, start=1):
        Band.objects.using(alias).create(
            template_version=template, code=code, label=label, lower_bound=lower,
            upper_bound=upper, display_order=order, functional_dependency_level=dependency,
            care_need_level=need,
        )


def uninstall(apps, schema_editor):
    templates = apps.get_model("casework", "AssessmentTemplateVersion").objects.using(
        schema_editor.connection.alias
    ).filter(instrument__code="BARTHEL", version=VERSION)
    if apps.get_model("casework", "Assessment").objects.using(
        schema_editor.connection.alias
    ).filter(template_version__in=templates).exists():
        raise RuntimeError("Barthel assessments exist. Preserve their template before rollback.")
    templates.delete()


class Migration(migrations.Migration):
    dependencies = [("casework", "0023_barthel_scored_choices_and_signatures")]
    operations = [migrations.RunPython(install, uninstall)]
