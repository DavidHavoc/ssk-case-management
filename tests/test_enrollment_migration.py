from datetime import date

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_existing_synthetic_records_are_backfilled_without_reinterpretation():
    executor = MigrationExecutor(connection)
    old_target = [
        ("accounts", "0004_central_hr_group"),
        ("casework", "0003_privateattachment_document_type"),
    ]
    executor.migrate(old_target)
    old_apps = executor.loader.project_state(old_target).apps

    Center = old_apps.get_model("centers", "Center")
    StaffProfile = old_apps.get_model("centers", "StaffProfile")
    SpecialistProfile = old_apps.get_model("centers", "SpecialistProfile")
    User = old_apps.get_model("accounts", "User")
    Beneficiary = old_apps.get_model("casework", "Beneficiary")
    BeneficiarySpecialistAssignment = old_apps.get_model(
        "casework", "BeneficiarySpecialistAssignment"
    )
    ServiceVisit = old_apps.get_model("casework", "ServiceVisit")
    Assessment = old_apps.get_model("casework", "Assessment")
    AssessmentDomainScore = old_apps.get_model("casework", "AssessmentDomainScore")
    IndividualPlan = old_apps.get_model("casework", "IndividualPlan")

    center = Center.objects.create(code="MIG-SYN", name="Synthetic Migration Center")
    user = User.objects.create(username="migration.synthetic@example.invalid")
    staff = StaffProfile.objects.create(
        user=user,
        employee_number="MIG-SYN-EMP",
        primary_center=center,
    )
    specialist = SpecialistProfile.objects.create(staff_profile=staff)
    beneficiary = Beneficiary.objects.create(
        beneficiary_code="MIG-SYN-BEN",
        service_type="rehabilitation",
        service_status="on_hold",
        center=center,
        full_name="Synthetic Migrated Beneficiary",
        birth_date=date(2020, 2, 29),
        region="Exact Legacy Region Text",
        municipality="Exact Legacy Municipality Text",
        diagnosis_status="Exact restricted legacy diagnosis narrative",
        enrollment_date=date(2025, 1, 10),
        application_contract_number="MIG-SYN-CONTRACT",
        notes="Exact synthetic legacy note",
    )
    BeneficiarySpecialistAssignment.objects.create(
        beneficiary=beneficiary,
        specialist=specialist,
        assignment_role="primary",
        from_date=None,
    )
    visit = ServiceVisit.objects.create(
        beneficiary=beneficiary,
        center=center,
        specialist=specialist,
        visit_date=date(2025, 2, 1),
        visit_month=date(2025, 2, 1),
        visit_type="home_visit",
        status="completed",
        service_units=1,
        duration_minutes=30,
    )
    assessment = Assessment.objects.create(
        beneficiary=beneficiary,
        center=center,
        specialist=specialist,
        assessment_date=date(2025, 2, 2),
        assessment_type="initial",
        scoring_tool="other",
        total_score=17,
    )
    domain_score = AssessmentDomainScore.objects.create(
        assessment=assessment,
        domain="Exact synthetic legacy domain",
        baseline_score=3,
        current_score=5,
        progress_notes="Exact synthetic legacy domain note",
    )
    plan = IndividualPlan.objects.create(
        beneficiary=beneficiary,
        center=center,
        specialist=specialist,
        status="draft",
        plan_start_date=date(2025, 2, 3),
    )

    leaf_targets = executor.loader.graph.leaf_nodes()
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        apps = executor.loader.project_state(executor.loader.graph.leaf_nodes()).apps
        NewBeneficiary = apps.get_model("casework", "Beneficiary")
        ServiceEnrollment = apps.get_model("casework", "ServiceEnrollment")
        ServiceDefinition = apps.get_model("casework", "ServiceDefinition")
        BeneficiaryDiagnosis = apps.get_model("casework", "BeneficiaryDiagnosis")
        NewVisit = apps.get_model("casework", "ServiceVisit")
        NewAssessment = apps.get_model("casework", "Assessment")
        NewAssessmentDomainScore = apps.get_model("casework", "AssessmentDomainScore")
        AssessmentResponse = apps.get_model("casework", "AssessmentResponse")
        NewPlan = apps.get_model("casework", "IndividualPlan")

        migrated_person = NewBeneficiary.objects.get(pk=beneficiary.pk)
        enrollment = ServiceEnrollment.objects.get(legacy_source_id=beneficiary.pk)
        migrated_visit = NewVisit.objects.get(pk=visit.pk)
        migrated_assessment = NewAssessment.objects.get(pk=assessment.pk)
        migrated_domain = NewAssessmentDomainScore.objects.get(pk=domain_score.pk)
        migrated_response = AssessmentResponse.objects.get(assessment_id=assessment.pk)
        results = {
            "person_code": migrated_person.beneficiary_code,
            "region": migrated_person.region,
            "municipality": migrated_person.municipality,
            "diagnosis_narrative": migrated_person.diagnosis_status,
            "region_ref": migrated_person.region_ref_id,
            "municipality_ref": migrated_person.municipality_ref_id,
            "episode_code": enrollment.episode_code,
            "legacy_service": enrollment.legacy_service_value,
            "legacy_status": enrollment.legacy_status_value,
            "mapped_status": enrollment.status,
            "placement_center": enrollment.center_placements.get().center_id,
            "assignment_count": enrollment.specialist_assignments.count(),
            "coded_diagnosis_count": BeneficiaryDiagnosis.objects.filter(
                beneficiary_id=beneficiary.pk
            ).count(),
            "visit_enrollment": migrated_visit.enrollment_id,
            "visit_legacy_type": migrated_visit.legacy_visit_type,
            "visit_activity": migrated_visit.activity.code,
            "visit_location": migrated_visit.delivery_location.code,
            "visit_format": migrated_visit.participation_format,
            "assessment_enrollment": migrated_assessment.enrollment_id,
            "assessment_template_version": migrated_assessment.template_version.version,
            "assessment_template_legacy": migrated_assessment.template_version.is_legacy,
            "assessment_status": migrated_assessment.status,
            "assessment_total": migrated_assessment.total_score,
            "response_total": migrated_response.numeric_value,
            "domain_text": migrated_domain.domain,
            "domain_baseline": migrated_domain.baseline_score,
            "domain_current": migrated_domain.current_score,
            "domain_notes": migrated_domain.progress_notes,
            "domain_mapping": migrated_domain.mapping_status,
            "plan_enrollment": NewPlan.objects.get(pk=plan.pk).enrollment_id,
            "enrollment_id": enrollment.pk,
            "legacy_service_name_ka": ServiceDefinition.objects.get(
                code="LEGACY-REHABILITATION"
            ).name_ka,
        }
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(leaf_targets)

    assert results == {
        "person_code": "MIG-SYN-BEN",
        "region": "Exact Legacy Region Text",
        "municipality": "Exact Legacy Municipality Text",
        "diagnosis_narrative": "Exact restricted legacy diagnosis narrative",
        "region_ref": None,
        "municipality_ref": None,
        "episode_code": "MIG-SYN-BEN-E01",
        "legacy_service": "rehabilitation",
        "legacy_status": "on_hold",
        "mapped_status": "suspended",
        "placement_center": center.pk,
        "assignment_count": 1,
        "coded_diagnosis_count": 0,
        "visit_enrollment": results["enrollment_id"],
        "visit_legacy_type": "home_visit",
        "visit_activity": "INDIVIDUAL-MEETING",
        "visit_location": "HOME",
        "visit_format": "individual",
        "assessment_enrollment": results["enrollment_id"],
        "assessment_template_version": "legacy-1",
        "assessment_template_legacy": True,
        "assessment_status": "completed",
        "assessment_total": 17,
        "response_total": 17,
        "domain_text": "Exact synthetic legacy domain",
        "domain_baseline": 3,
        "domain_current": 5,
        "domain_notes": "Exact synthetic legacy domain note",
        "domain_mapping": "review_required",
        "plan_enrollment": results["enrollment_id"],
        "enrollment_id": results["enrollment_id"],
        "legacy_service_name_ka": "ძველი მონაცემი: რეაბილიტაცია",
    }
