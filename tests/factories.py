from __future__ import annotations

import itertools
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from apps.accounts.roles import CENTRAL_HR, COORDINATOR, SPECIALIST, SYSTEM_MANAGER
from apps.casework.assessment_engine import complete_assessment, replace_draft_responses
from apps.casework.models import (
    Assessment,
    AssessmentInstrument,
    AssessmentTemplateField,
    AssessmentTemplateSection,
    AssessmentTemplateVersion,
    Beneficiary,
    BeneficiarySpecialistAssignment,
    CenterServiceOffering,
    EnrollmentSpecialistAssignment,
    GoalCategory,
    IndividualPlan,
    IndividualPlanGoal,
    ServiceActivityDefinition,
    ServiceDefinition,
    ServiceEnrollment,
    ServiceVisit,
    VisitLocationDefinition,
)
from apps.casework.services import create_enrollment
from apps.centers.models import (
    Center,
    SpecialistCenterAssignment,
    SpecialistProfile,
    StaffProfile,
)

User = get_user_model()
counter = itertools.count(1)


def make_center(label: str | None = None) -> Center:
    number = next(counter)
    value = label or f"Center {number}"
    return Center.objects.create(code=f"TST-{number:04d}", name=value)


def ensure_center_offerings(center: Center) -> None:
    definitions = (
        ("HOME-CARE", "Home Care", "შინმოვლა", ServiceDefinition.Family.HOME_CARE, 10),
        (
            "FOOD-DELIVERY",
            "Food Delivery",
            "საკვების მიწოდება",
            ServiceDefinition.Family.FOOD_DELIVERY,
            20,
        ),
        (
            "EARLY-INTERVENTION",
            "Early Intervention",
            "ადრეული ინტერვენცია",
            ServiceDefinition.Family.EARLY_INTERVENTION,
            30,
        ),
        (
            "FUTURE-GENERAL",
            "Future Service",
            "სამომავლო სერვისი",
            ServiceDefinition.Family.FUTURE,
            900,
        ),
        ("LEGACY-OTHER", "Other", "სხვა", ServiceDefinition.Family.LEGACY, 1004),
    )
    for code, name_en, name_ka, family, reporting_order in definitions:
        service, _ = ServiceDefinition.objects.get_or_create(
            code=code,
            defaults={
                "name_en": name_en,
                "name_ka": name_ka,
                "family": family,
                "reporting_order": reporting_order,
                "valid_from": date(2026, 1, 1),
                "source_version": "SYNTHETIC-TEST",
            },
        )
        CenterServiceOffering.objects.create(center=center, service=service)


def ensure_visit_catalogs():
    activity, _ = ServiceActivityDefinition.objects.get_or_create(
        code="INDIVIDUAL-MEETING",
        defaults={
            "name_en": "Individual meeting",
            "name_ka": "ინდივიდუალური შეხვედრა",
            "reporting_order": 10,
            "source_version": "SYNTHETIC-TEST",
        },
    )
    location, _ = VisitLocationDefinition.objects.get_or_create(
        code="CENTER",
        defaults={
            "name_en": "Center",
            "name_ka": "ცენტრი",
            "reporting_order": 10,
            "source_version": "SYNTHETIC-TEST",
        },
    )
    return activity, location


def make_user(role: str, label: str | None = None):
    number = next(counter)
    stem = label or f"user{number}"
    user = User.objects.create_user(
        username=f"{stem}.{number}@example.invalid",
        email=f"{stem}.{number}@example.invalid",
        password="Synthetic-Test-Password-42!",
        first_name="Synthetic",
        last_name=stem.title(),
    )
    group, _ = Group.objects.get_or_create(name=role)
    user.groups.add(group)
    return user


def make_manager(label: str = "manager"):
    return make_user(SYSTEM_MANAGER, label)


def make_central_hr(label: str = "central-hr"):
    return make_user(CENTRAL_HR, label)


def make_coordinator(center: Center, label: str = "coordinator"):
    user = make_user(COORDINATOR, label)
    staff = StaffProfile.objects.create(
        user=user,
        employee_number=f"EMP-{next(counter):05d}",
        job_title="Coordinator",
        primary_center=center,
    )
    staff.centers.add(center)
    return user


def make_specialist(center: Center, label: str = "specialist") -> SpecialistProfile:
    user = make_user(SPECIALIST, label)
    staff = StaffProfile.objects.create(
        user=user,
        employee_number=f"EMP-{next(counter):05d}",
        job_title="Specialist",
        primary_center=center,
    )
    staff.centers.add(center)
    profile = SpecialistProfile.objects.create(
        staff_profile=staff, description="Synthetic specialist profile."
    )
    SpecialistCenterAssignment.objects.create(specialist=profile, center=center, is_primary=True)
    return profile


def add_specialist_center(specialist: SpecialistProfile, center: Center) -> None:
    SpecialistCenterAssignment.objects.create(
        specialist=specialist, center=center, is_primary=False
    )


def make_beneficiary(
    center: Center,
    specialist: SpecialistProfile,
    *,
    name: str = "Synthetic Beneficiary",
    code: str | None = None,
) -> Beneficiary:
    if not CenterServiceOffering.objects.filter(center=center).exists():
        ensure_center_offerings(center)
    number = next(counter)
    beneficiary = Beneficiary.objects.create(
        beneficiary_code=code or "",
        service_type=Beneficiary.ServiceType.OTHER,
        service_status=Beneficiary.ServiceStatus.ACTIVE,
        center=center,
        full_name=name,
        personal_id=f"SYNTHETIC-PID-{number}",
        birth_date=date(2000, 1, 1),
        address="Synthetic address",
        guardian_parent="Synthetic guardian",
        phone="+995 555 000 000",
        email=f"beneficiary.{number}@example.invalid",
        application_contract_number=f"SYNTHETIC-CONTRACT-{number}",
        enrollment_date=date(2026, 1, 1),
        notes="Synthetic case note.",
    )
    BeneficiarySpecialistAssignment.objects.create(
        beneficiary=beneficiary,
        specialist=specialist,
        assignment_role=BeneficiarySpecialistAssignment.Role.PRIMARY,
    )
    offering = CenterServiceOffering.objects.get(
        center=center,
        service__code="LEGACY-OTHER",
    )
    enrollment = create_enrollment(
        beneficiary=beneficiary,
        offering=offering,
        start_date=date(2026, 1, 1),
        status=ServiceEnrollment.Status.ACTIVE,
        application_contract_number=beneficiary.application_contract_number,
        notes="Synthetic enrollment note.",
        actor=specialist.staff_profile.user,
    )
    assignment = EnrollmentSpecialistAssignment.objects.create(
        enrollment=enrollment,
        specialist=specialist,
        assignment_role=EnrollmentSpecialistAssignment.Role.PRIMARY,
        valid_from=date(2026, 1, 1),
    )
    capture_legacy_assignment(assignment)
    return beneficiary


def make_visit(
    beneficiary: Beneficiary,
    specialist: SpecialistProfile,
    *,
    visit_date: date = date(2026, 1, 15),
    status: str = ServiceVisit.Status.COMPLETED,
    enrollment: ServiceEnrollment | None = None,
) -> ServiceVisit:
    enrollment = enrollment or beneficiary.enrollments.order_by("created_at").first()
    activity, location = ensure_visit_catalogs()
    return ServiceVisit.objects.create(
        enrollment=enrollment,
        beneficiary=beneficiary,
        center=enrollment.placement_on(visit_date).center,
        specialist=specialist,
        visit_date=visit_date,
        activity=activity,
        delivery_location=location,
        participation_format="individual",
        status=status,
        service_units=2,
        duration_minutes=60,
        cancellation_reason=(
            "Synthetic cancellation." if status == ServiceVisit.Status.CANCELLED else ""
        ),
        notes="Synthetic visit.",
    )


def make_assessment(
    beneficiary: Beneficiary,
    specialist: SpecialistProfile,
    *,
    assessment_type: str = Assessment.AssessmentType.INITIAL,
    assessment_date: date = date(2026, 1, 10),
    previous: Assessment | None = None,
    enrollment: ServiceEnrollment | None = None,
    template_version: AssessmentTemplateVersion | None = None,
) -> Assessment:
    enrollment = enrollment or beneficiary.enrollments.order_by("created_at").first()
    if template_version is None:
        template_version = make_assessment_template()
    assessment = Assessment.objects.create(
        enrollment=enrollment,
        beneficiary=beneficiary,
        center=enrollment.placement_on(assessment_date).center,
        specialist=specialist,
        assessment_date=assessment_date,
        assessment_type=assessment_type,
        previous_assessment=previous,
        scoring_tool=template_version.instrument.identifier,
        template_version=template_version,
    )
    response_field = template_version.fields.get(code="SYNTHETIC_SCORE")
    replace_draft_responses(
        assessment,
        [
            {
                "template_field": response_field,
                "numeric_value": 10,
            }
        ],
    )
    assessment = complete_assessment(assessment)
    return assessment


def make_assessment_template() -> AssessmentTemplateVersion:
    instrument = AssessmentInstrument.objects.get(code="OTHER")
    template_version = AssessmentTemplateVersion.objects.filter(
        instrument=instrument,
        version="synthetic-test-1",
    ).first()
    if template_version is not None:
        return template_version
    template_version = AssessmentTemplateVersion.objects.create(
        instrument=instrument,
        version="synthetic-test-1",
        name="Synthetic test assessment",
        comparison_group="SYNTHETIC-TEST",
    )
    section = AssessmentTemplateSection.objects.create(
        template_version=template_version,
        code="SYNTHETIC",
        name="Synthetic structure",
    )
    AssessmentTemplateField.objects.create(
        section=section,
        code="SYNTHETIC_SCORE",
        label="Synthetic score",
        response_type=AssessmentTemplateField.ResponseType.NUMERIC_SCORE,
        minimum_value=0,
        maximum_value=100,
        include_in_total=True,
    )
    template_version.publish()
    return template_version


def make_plan(
    beneficiary: Beneficiary,
    specialist: SpecialistProfile,
    *,
    status: str = IndividualPlan.Status.ACTIVE,
    enrollment: ServiceEnrollment | None = None,
) -> IndividualPlan:
    enrollment = enrollment or beneficiary.enrollments.order_by("created_at").first()
    plan = IndividualPlan.objects.create(
        enrollment=enrollment,
        beneficiary=beneficiary,
        center=enrollment.placement_on(date(2026, 1, 1)).center,
        specialist=specialist,
        status=status,
        plan_start_date=date(2026, 1, 1),
        plan_end_date=date(2026, 6, 1),
        review_frequency=IndividualPlan.ReviewFrequency.MONTHLY,
    )
    IndividualPlanGoal.objects.create(
        plan=plan,
        category=GoalCategory.objects.get(code="LEGACY-UNCLASSIFIED"),
        goal="Synthetic goal",
        baseline="Synthetic baseline",
        measurable_target="Synthetic measurable target",
        responsible_specialist=specialist,
        target_date=date(2026, 3, 1),
        status=IndividualPlanGoal.Status.IN_PROGRESS,
    )
    return plan


def set_active_center(client, center: Center) -> None:
    session = client.session
    session["ssk_active_center"] = str(center.pk)
    session.save()


def capture_legacy_assignment(assignment):
    """Build a pre-release snapshot fixture, then restore the frozen bridge guard.

    Ordinary application writers cannot create these grants. Historical fixtures
    deliberately use migration models with the insertion guard temporarily removed.
    """
    from datetime import timedelta

    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    from django.utils import timezone

    if assignment.valid_from is None:
        return assignment
    today = timezone.localdate()
    if assignment.valid_from > today or (assignment.valid_to and assignment.valid_to <= today):
        return assignment
    Grant = (
        MigrationExecutor(connection)
        .loader.project_state([("casework", "0016_beneficiary_staffing_periods")])
        .apps.get_model("casework", "LegacyStaffingGrant")
    )
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute(
                "ALTER TABLE casework_legacystaffinggrant DISABLE TRIGGER legacy_grant_guard"
            )
        else:
            cursor.execute("DROP TRIGGER legacy_grant_insert")
        try:
            Grant.objects.get_or_create(
                assignment_id=assignment.pk,
                defaults={
                    "center_id": assignment.enrollment.placement_on(today).center_id,
                    "placement_id": assignment.enrollment.placement_on(today).pk,
                    "enrollment_id": assignment.enrollment_id,
                    "specialist_id": assignment.specialist_id,
                    "valid_from": assignment.valid_from,
                    "valid_to": assignment.valid_to,
                    "captured_on": today,
                    "expires_on": today + timedelta(days=90),
                },
            )
        finally:
            if connection.vendor == "postgresql":
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                cursor.execute(
                    "ALTER TABLE casework_legacystaffinggrant ENABLE TRIGGER legacy_grant_guard"
                )
                cursor.execute("SET CONSTRAINTS ALL DEFERRED")
            else:
                cursor.execute("""CREATE TRIGGER legacy_grant_insert BEFORE INSERT
                    ON casework_legacystaffinggrant BEGIN SELECT RAISE(ABORT,
                    'Legacy staffing access is a frozen migration snapshot'); END;""")
    return assignment


def remove_legacy_assignments(queryset):
    """Synthetic pre-release fixture editing, never an operational staffing API."""
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    Assignment = (
        MigrationExecutor(connection)
        .loader.project_state([("casework", "0016_beneficiary_staffing_periods")])
        .apps.get_model("casework", "EnrollmentSpecialistAssignment")
    )
    return Assignment.objects.filter(pk__in=queryset.values("pk")).delete()
