from datetime import date

from django.db import migrations

SERVICE_DEFINITIONS = (
    ("HOME-CARE", "Home Care", "შინმოვლა", "home_care", 10),
    ("FOOD-DELIVERY", "Food Delivery", "საკვების მიწოდება", "food_delivery", 20),
    (
        "EARLY-INTERVENTION",
        "Early Intervention",
        "ადრეული ინტერვენცია",
        "early_intervention",
        30,
    ),
    ("FUTURE-GENERAL", "Future Service", "სამომავლო სერვისი", "future", 900),
)

LEGACY_SERVICES = {
    "disability_support": ("Disability Support", "შშმ პირთა მხარდაჭერა"),
    "child_protection": ("Child Protection", "ბავშვთა დაცვა"),
    "social_protection": ("Social Protection", "სოციალური დაცვა"),
    "rehabilitation": ("Rehabilitation", "რეაბილიტაცია"),
    "other": ("Other", "სხვა"),
}

REGIONS = (
    ("GEO-TB", "Tbilisi", "თბილისი"),
    ("GEO-AJ", "Autonomous Republic of Adjara", "აჭარის ავტონომიური რესპუბლიკა"),
    ("GEO-GU", "Guria", "გურია"),
    ("GEO-IM", "Imereti", "იმერეთი"),
    ("GEO-KA", "Kakheti", "კახეთი"),
    ("GEO-MM", "Mtskheta-Mtianeti", "მცხეთა-მთიანეთი"),
    ("GEO-RL", "Racha-Lechkhumi and Kvemo Svaneti", "რაჭა-ლეჩხუმი და ქვემო სვანეთი"),
    ("GEO-SZ", "Samegrelo-Zemo Svaneti", "სამეგრელო-ზემო სვანეთი"),
    ("GEO-SJ", "Samtskhe-Javakheti", "სამცხე-ჯავახეთი"),
    ("GEO-KK", "Kvemo Kartli", "ქვემო ქართლი"),
    ("GEO-SK", "Shida Kartli", "შიდა ქართლი"),
)

MUNICIPALITIES = (
    ("GEO-MUN-TBILISI", "GEO-TB", "Tbilisi", "თბილისი"),
    ("GEO-MUN-BATUMI", "GEO-AJ", "Batumi", "ბათუმი"),
    ("GEO-MUN-KEDA", "GEO-AJ", "Keda", "ქედა"),
    ("GEO-MUN-KOBULETI", "GEO-AJ", "Kobuleti", "ქობულეთი"),
    ("GEO-MUN-SHUAKHEVI", "GEO-AJ", "Shuakhevi", "შუახევი"),
    ("GEO-MUN-KHELVACHAURI", "GEO-AJ", "Khelvachauri", "ხელვაჩაური"),
    ("GEO-MUN-KHULO", "GEO-AJ", "Khulo", "ხულო"),
    ("GEO-MUN-LANCHKHUTI", "GEO-GU", "Lanchkhuti", "ლანჩხუთი"),
    ("GEO-MUN-OZURGETI", "GEO-GU", "Ozurgeti", "ოზურგეთი"),
    ("GEO-MUN-CHOKHATAURI", "GEO-GU", "Chokhatauri", "ჩოხატაური"),
    ("GEO-MUN-BAGHDATI", "GEO-IM", "Baghdati", "ბაღდათი"),
    ("GEO-MUN-VANI", "GEO-IM", "Vani", "ვანი"),
    ("GEO-MUN-ZESTAFONI", "GEO-IM", "Zestafoni", "ზესტაფონი"),
    ("GEO-MUN-TERJOLA", "GEO-IM", "Terjola", "თერჯოლა"),
    ("GEO-MUN-SAMTREDIA", "GEO-IM", "Samtredia", "სამტრედია"),
    ("GEO-MUN-SACHKHERE", "GEO-IM", "Sachkhere", "საჩხერე"),
    ("GEO-MUN-TKIBULI", "GEO-IM", "Tkibuli", "ტყიბული"),
    ("GEO-MUN-TSKALTUBO", "GEO-IM", "Tskaltubo", "წყალტუბო"),
    ("GEO-MUN-CHIATURA", "GEO-IM", "Chiatura", "ჭიათურა"),
    ("GEO-MUN-KHARAGAULI", "GEO-IM", "Kharagauli", "ხარაგაული"),
    ("GEO-MUN-KHONI", "GEO-IM", "Khoni", "ხონი"),
    ("GEO-MUN-KUTAISI", "GEO-IM", "Kutaisi", "ქუთაისი"),
    ("GEO-MUN-AKHMETA", "GEO-KA", "Akhmeta", "ახმეტა"),
    ("GEO-MUN-GURJAANI", "GEO-KA", "Gurjaani", "გურჯაანი"),
    ("GEO-MUN-DEDOPLISTSKARO", "GEO-KA", "Dedoplistskaro", "დედოფლისწყარო"),
    ("GEO-MUN-TELAVI", "GEO-KA", "Telavi", "თელავი"),
    ("GEO-MUN-LAGODEKHI", "GEO-KA", "Lagodekhi", "ლაგოდეხი"),
    ("GEO-MUN-SAGAREJO", "GEO-KA", "Sagarejo", "საგარეჯო"),
    ("GEO-MUN-SIGHNAGHI", "GEO-KA", "Sighnaghi", "სიღნაღი"),
    ("GEO-MUN-KVARELI", "GEO-KA", "Kvareli", "ყვარელი"),
    ("GEO-MUN-DUSHETI", "GEO-MM", "Dusheti", "დუშეთი"),
    ("GEO-MUN-TIANETI", "GEO-MM", "Tianeti", "თიანეთი"),
    ("GEO-MUN-MTSKHETA", "GEO-MM", "Mtskheta", "მცხეთა"),
    ("GEO-MUN-KAZBEGI", "GEO-MM", "Kazbegi", "ყაზბეგი"),
    ("GEO-MUN-AMBROLAURI", "GEO-RL", "Ambrolauri", "ამბროლაური"),
    ("GEO-MUN-LENTEKHI", "GEO-RL", "Lentekhi", "ლენტეხი"),
    ("GEO-MUN-ONI", "GEO-RL", "Oni", "ონი"),
    ("GEO-MUN-TSAGERI", "GEO-RL", "Tsageri", "ცაგერი"),
    ("GEO-MUN-ABASHA", "GEO-SZ", "Abasha", "აბაშა"),
    ("GEO-MUN-ZUGDIDI", "GEO-SZ", "Zugdidi", "ზუგდიდი"),
    ("GEO-MUN-MARTVILI", "GEO-SZ", "Martvili", "მარტვილი"),
    ("GEO-MUN-MESTIA", "GEO-SZ", "Mestia", "მესტია"),
    ("GEO-MUN-SENAKI", "GEO-SZ", "Senaki", "სენაკი"),
    ("GEO-MUN-CHKHOROTSKU", "GEO-SZ", "Chkhorotsku", "ჩხოროწყუ"),
    ("GEO-MUN-TSALENJIKHA", "GEO-SZ", "Tsalenjikha", "წალენჯიხა"),
    ("GEO-MUN-KHOBI", "GEO-SZ", "Khobi", "ხობი"),
    ("GEO-MUN-POTI", "GEO-SZ", "Poti", "ფოთი"),
    ("GEO-MUN-ADIGENI", "GEO-SJ", "Adigeni", "ადიგენი"),
    ("GEO-MUN-ASPINDZA", "GEO-SJ", "Aspindza", "ასპინძა"),
    ("GEO-MUN-AKHALKALAKI", "GEO-SJ", "Akhalkalaki", "ახალქალაქი"),
    ("GEO-MUN-AKHALTSIKHE", "GEO-SJ", "Akhaltsikhe", "ახალციხე"),
    ("GEO-MUN-BORJOMI", "GEO-SJ", "Borjomi", "ბორჯომი"),
    ("GEO-MUN-NINOTSMINDA", "GEO-SJ", "Ninotsminda", "ნინოწმინდა"),
    ("GEO-MUN-BOLNISI", "GEO-KK", "Bolnisi", "ბოლნისი"),
    ("GEO-MUN-GARDABANI", "GEO-KK", "Gardabani", "გარდაბანი"),
    ("GEO-MUN-DMANISI", "GEO-KK", "Dmanisi", "დმანისი"),
    ("GEO-MUN-TETRITSKARO", "GEO-KK", "Tetritskaro", "თეთრიწყარო"),
    ("GEO-MUN-MARNEULI", "GEO-KK", "Marneuli", "მარნეული"),
    ("GEO-MUN-RUSTAVI", "GEO-KK", "Rustavi", "რუსთავი"),
    ("GEO-MUN-TSALKA", "GEO-KK", "Tsalka", "წალკა"),
    ("GEO-MUN-GORI", "GEO-SK", "Gori", "გორი"),
    ("GEO-MUN-KASPI", "GEO-SK", "Kaspi", "კასპი"),
    ("GEO-MUN-KARELI", "GEO-SK", "Kareli", "ქარელი"),
    ("GEO-MUN-KHASHURI", "GEO-SK", "Khashuri", "ხაშური"),
)


def seed_catalogs(apps):
    ServiceDefinition = apps.get_model("casework", "ServiceDefinition")
    Region = apps.get_model("casework", "Region")
    Municipality = apps.get_model("casework", "Municipality")

    for code, name_en, name_ka, family, order in SERVICE_DEFINITIONS:
        ServiceDefinition.objects.update_or_create(
            code=code,
            defaults={
                "name_en": name_en,
                "name_ka": name_ka,
                "family": family,
                "reporting_order": order,
                "valid_from": date(2026, 1, 1),
                "is_active": True,
                "source_version": "SSK-TASK-1-2026-08",
            },
        )

    for legacy_value, (label_en, label_ka) in LEGACY_SERVICES.items():
        ServiceDefinition.objects.update_or_create(
            code=f"LEGACY-{legacy_value.replace('_', '-').upper()}",
            defaults={
                "name_en": f"Legacy: {label_en}",
                "name_ka": f"ძველი მონაცემი: {label_ka}",
                "family": "legacy",
                "reporting_order": 1000,
                "is_active": True,
                "source_version": "SSK-MVP-LEGACY",
            },
        )

    source_version = "GEOSTAT-REGIONAL-CATALOG-VERIFIED-2026-08-20"
    region_by_code = {}
    for code, name_en, name_ka in REGIONS:
        region, _ = Region.objects.update_or_create(
            code=code,
            defaults={
                "name_en": name_en,
                "name_ka": name_ka,
                "valid_from": date(2024, 1, 1),
                "is_active": True,
                "source_version": source_version,
            },
        )
        region_by_code[code] = region
    for code, region_code, name_en, name_ka in MUNICIPALITIES:
        Municipality.objects.update_or_create(
            code=code.upper(),
            defaults={
                "region": region_by_code[region_code],
                "name_en": name_en,
                "name_ka": name_ka,
                "valid_from": date(2024, 1, 1),
                "is_active": True,
                "source_version": source_version,
            },
        )


def backfill_legacy_records(apps):
    Beneficiary = apps.get_model("casework", "Beneficiary")
    BeneficiarySpecialistAssignment = apps.get_model(
        "casework", "BeneficiarySpecialistAssignment"
    )
    CenterServiceOffering = apps.get_model("casework", "CenterServiceOffering")
    EnrollmentCenterPlacement = apps.get_model("casework", "EnrollmentCenterPlacement")
    EnrollmentSpecialistAssignment = apps.get_model(
        "casework", "EnrollmentSpecialistAssignment"
    )
    EnrollmentStateEvent = apps.get_model("casework", "EnrollmentStateEvent")
    ServiceDefinition = apps.get_model("casework", "ServiceDefinition")
    ServiceEnrollment = apps.get_model("casework", "ServiceEnrollment")
    Assessment = apps.get_model("casework", "Assessment")
    IndividualPlan = apps.get_model("casework", "IndividualPlan")
    ServiceVisit = apps.get_model("casework", "ServiceVisit")

    state_mapping = {
        "applied": "pending",
        "active": "active",
        "on_hold": "suspended",
        "exited": "exited",
    }
    for beneficiary in Beneficiary.objects.all().iterator():
        legacy_service = beneficiary.service_type or "other"
        service_code = f"LEGACY-{legacy_service.replace('_', '-').upper()}"
        service = ServiceDefinition.objects.get(code=service_code)
        offering, _ = CenterServiceOffering.objects.get_or_create(
            center_id=beneficiary.center_id,
            service=service,
            valid_from=None,
            defaults={"is_active": True},
        )
        mapped_status = state_mapping.get(beneficiary.service_status, "pending")
        terminal = mapped_status in {"completed", "exited", "cancelled"}
        end_date = beneficiary.exit_date if terminal else None
        dates_incomplete = (
            beneficiary.enrollment_date is None
            or (terminal and end_date is None)
            or (
                beneficiary.enrollment_date is not None
                and end_date is not None
                and beneficiary.enrollment_date == end_date
            )
        )
        enrollment, _ = ServiceEnrollment.objects.get_or_create(
            legacy_source_id=beneficiary.pk,
            defaults={
                "beneficiary_id": beneficiary.pk,
                "service": service,
                "episode_code": f"{beneficiary.beneficiary_code}-E01",
                "status": mapped_status,
                "start_date": beneficiary.enrollment_date,
                "end_date": end_date,
                "first_service_date": beneficiary.first_service_date,
                "application_contract_number": beneficiary.application_contract_number,
                "exit_reason": beneficiary.exit_reason,
                "notes": beneficiary.notes,
                "legacy_service_value": beneficiary.service_type,
                "legacy_status_value": beneficiary.service_status,
                "legacy_dates_incomplete": dates_incomplete,
            },
        )
        EnrollmentCenterPlacement.objects.get_or_create(
            enrollment=enrollment,
            defaults={
                "center_id": beneficiary.center_id,
                "offering": offering,
                "valid_from": beneficiary.enrollment_date,
                "valid_to": end_date,
                "transfer_reason": beneficiary.exit_reason if terminal else "",
                "legacy_dates_incomplete": dates_incomplete,
            },
        )
        EnrollmentStateEvent.objects.get_or_create(
            enrollment=enrollment,
            kind="legacy_import",
            defaults={
                "previous_state": "",
                "new_state": mapped_status,
                "effective_date": end_date or beneficiary.enrollment_date,
                "reason": beneficiary.exit_reason if terminal else "",
            },
        )
        for assignment in BeneficiarySpecialistAssignment.objects.filter(
            beneficiary_id=beneficiary.pk
        ):
            EnrollmentSpecialistAssignment.objects.get_or_create(
                enrollment=enrollment,
                specialist_id=assignment.specialist_id,
                valid_from=assignment.from_date,
                defaults={
                    "assignment_role": assignment.assignment_role,
                    "valid_to": assignment.to_date,
                    "legacy_dates_incomplete": assignment.from_date is None,
                },
            )
        ServiceVisit.objects.filter(beneficiary_id=beneficiary.pk).update(
            enrollment_id=enrollment.pk
        )
        Assessment.objects.filter(beneficiary_id=beneficiary.pk).update(
            enrollment_id=enrollment.pk
        )
        IndividualPlan.objects.filter(beneficiary_id=beneficiary.pk).update(
            enrollment_id=enrollment.pk
        )


def forwards(apps, schema_editor):
    seed_catalogs(apps)
    backfill_legacy_records(apps)


class Migration(migrations.Migration):
    dependencies = [("casework", "0005_allow_exact_legacy_intervals")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
