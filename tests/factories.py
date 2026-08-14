from __future__ import annotations

import itertools
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from apps.accounts.roles import COORDINATOR, SPECIALIST, SYSTEM_MANAGER
from apps.casework.models import (
    Assessment,
    AssessmentDomainScore,
    Beneficiary,
    BeneficiarySpecialistAssignment,
    IndividualPlan,
    IndividualPlanGoal,
    ServiceVisit,
)
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
    user.groups.add(Group.objects.get(name=role))
    return user


def make_manager(label: str = "manager"):
    return make_user(SYSTEM_MANAGER, label)


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
    number = next(counter)
    beneficiary = Beneficiary.objects.create(
        beneficiary_code=code or f"BEN-TEST-{number:05d}",
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
    return beneficiary


def make_visit(
    beneficiary: Beneficiary,
    specialist: SpecialistProfile,
    *,
    visit_date: date = date(2026, 1, 15),
    status: str = ServiceVisit.Status.COMPLETED,
) -> ServiceVisit:
    return ServiceVisit.objects.create(
        beneficiary=beneficiary,
        center=beneficiary.center,
        specialist=specialist,
        visit_date=visit_date,
        visit_type=ServiceVisit.VisitType.CENTER,
        status=status,
        service_units=2,
        duration_minutes=60,
        notes="Synthetic visit.",
    )


def make_assessment(
    beneficiary: Beneficiary,
    specialist: SpecialistProfile,
    *,
    assessment_type: str = Assessment.AssessmentType.INITIAL,
    assessment_date: date = date(2026, 1, 10),
    previous: Assessment | None = None,
) -> Assessment:
    assessment = Assessment.objects.create(
        beneficiary=beneficiary,
        center=beneficiary.center,
        specialist=specialist,
        assessment_date=assessment_date,
        assessment_type=assessment_type,
        previous_assessment=previous,
        scoring_tool=Assessment.ScoringTool.OTHER,
        total_score=10,
    )
    AssessmentDomainScore.objects.create(
        assessment=assessment, domain="Synthetic domain", baseline_score=1, current_score=2
    )
    return assessment


def make_plan(
    beneficiary: Beneficiary,
    specialist: SpecialistProfile,
    *,
    status: str = IndividualPlan.Status.ACTIVE,
) -> IndividualPlan:
    plan = IndividualPlan.objects.create(
        beneficiary=beneficiary,
        center=beneficiary.center,
        specialist=specialist,
        status=status,
        plan_start_date=date(2026, 1, 1),
        plan_end_date=date(2026, 6, 1),
        review_frequency=IndividualPlan.ReviewFrequency.MONTHLY,
    )
    IndividualPlanGoal.objects.create(
        plan=plan,
        goal="Synthetic goal",
        target_date=date(2026, 3, 1),
        status=IndividualPlanGoal.Status.IN_PROGRESS,
    )
    return plan


def set_active_center(client, center: Center) -> None:
    session = client.session
    session["ssk_active_center"] = str(center.pk)
    session.save()
