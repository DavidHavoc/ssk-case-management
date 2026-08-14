from __future__ import annotations

import os
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.roles import COORDINATOR, SPECIALIST, SYSTEM_MANAGER, ensure_application_groups
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


class Command(BaseCommand):
    help = "Create an idempotent synthetic dataset for local demonstration."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo data can be seeded only when DJANGO_DEBUG is enabled.")
        with transaction.atomic():
            ensure_application_groups()
            alpha, _ = Center.objects.update_or_create(
                code="DEMO-ALPHA",
                defaults={
                    "name": "SSK Synthetic Center Alpha",
                    "is_active": True,
                    "email": "alpha.center@example.invalid",
                    "phone": "+995 555 000 101",
                    "address": "Synthetic Alpha Address",
                },
            )
            beta, _ = Center.objects.update_or_create(
                code="DEMO-BETA",
                defaults={
                    "name": "SSK Synthetic Center Beta",
                    "is_active": True,
                    "email": "beta.center@example.invalid",
                    "phone": "+995 555 000 102",
                    "address": "Synthetic Beta Address",
                },
            )

            self._user("synthetic.manager@example.invalid", "Synthetic", "Manager", SYSTEM_MANAGER)
            self._staff_user(
                "synthetic.coordinator.alpha@example.invalid",
                "Synthetic",
                "Coordinator Alpha",
                COORDINATOR,
                "DEMO-COORD-A",
                alpha,
            )
            self._staff_user(
                "synthetic.coordinator.beta@example.invalid",
                "Synthetic",
                "Coordinator Beta",
                COORDINATOR,
                "DEMO-COORD-B",
                beta,
            )
            specialist_a = self._specialist(
                "synthetic.specialist.alpha@example.invalid",
                "Synthetic",
                "Specialist Alpha",
                "DEMO-SPEC-A",
                [(alpha, True)],
                "Provides synthetic occupational therapy services.",
            )
            specialist_multi = self._specialist(
                "synthetic.specialist.multi@example.invalid",
                "Synthetic",
                "Specialist Multi Center",
                "DEMO-SPEC-M",
                [(alpha, True), (beta, False)],
                "Demonstrates authorized work across two synthetic centers.",
            )
            specialist_b = self._specialist(
                "synthetic.specialist.beta@example.invalid",
                "Synthetic",
                "Specialist Beta",
                "DEMO-SPEC-B",
                [(beta, True)],
                "Provides synthetic social support services.",
            )

            beneficiary_a = self._beneficiary(
                "BEN-DEMO-0001", "Synthetic Beneficiary Alpha", alpha, specialist_a
            )
            beneficiary_multi = self._beneficiary(
                "BEN-DEMO-0002", "Synthetic Beneficiary Multi", alpha, specialist_multi
            )
            beneficiary_b = self._beneficiary(
                "BEN-DEMO-0003", "Synthetic Beneficiary Beta", beta, specialist_b
            )
            self._workflows(beneficiary_a, specialist_a)
            self._workflows(beneficiary_multi, specialist_multi)
            self._workflows(beneficiary_b, specialist_b)

        self.stdout.write(self.style.SUCCESS("Synthetic demo data is ready."))
        if not os.getenv("SSK_DEMO_PASSWORD"):
            self.stdout.write(
                "Demo accounts have unusable passwords. "
                "Use manage.py changepassword for local access."
            )

    def _user(self, username: str, first: str, last: str, role: str):
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={"email": username, "first_name": first, "last_name": last},
        )
        user.email = username
        user.first_name = first
        user.last_name = last
        password = os.getenv("SSK_DEMO_PASSWORD")
        if password:
            user.set_password(password)
        elif not user.password:
            user.set_unusable_password()
        user.save()
        user.groups.add(Group.objects.get(name=role))
        return user

    def _staff_user(
        self,
        username: str,
        first: str,
        last: str,
        role: str,
        employee_number: str,
        center: Center,
    ) -> StaffProfile:
        user = self._user(username, first, last, role)
        staff, _ = StaffProfile.objects.update_or_create(
            user=user,
            defaults={
                "employee_number": employee_number,
                "job_title": role,
                "primary_center": center,
                "status": StaffProfile.Status.ACTIVE,
            },
        )
        staff.centers.add(center)
        return staff

    def _specialist(
        self,
        username: str,
        first: str,
        last: str,
        employee_number: str,
        centers: list[tuple[Center, bool]],
        description: str,
    ) -> SpecialistProfile:
        staff = self._staff_user(username, first, last, SPECIALIST, employee_number, centers[0][0])
        profile, _ = SpecialistProfile.objects.update_or_create(
            staff_profile=staff, defaults={"description": description}
        )
        for center, is_primary in centers:
            assignment, created = SpecialistCenterAssignment.objects.get_or_create(
                specialist=profile,
                center=center,
                defaults={"is_primary": is_primary},
            )
            if created:
                staff.centers.add(center)
        return profile

    def _beneficiary(
        self, code: str, name: str, center: Center, specialist: SpecialistProfile
    ) -> Beneficiary:
        beneficiary, _ = Beneficiary.objects.update_or_create(
            beneficiary_code=code,
            defaults={
                "full_name": name,
                "center": center,
                "service_type": Beneficiary.ServiceType.OTHER,
                "service_status": Beneficiary.ServiceStatus.ACTIVE,
                "personal_id": f"SYNTHETIC-{code}",
                "birth_date": date(2000, 1, 1),
                "email": f"{code.lower()}@example.invalid",
                "phone": "+995 555 000 000",
                "address": "Synthetic address only",
                "guardian_parent": "Synthetic Guardian",
                "application_contract_number": f"DEMO-CONTRACT-{code[-4:]}",
                "diagnosis_status": "Synthetic demonstration status",
                "enrollment_date": date.today() - timedelta(days=60),
                "notes": "Synthetic demonstration note.",
            },
        )
        BeneficiarySpecialistAssignment.objects.get_or_create(
            beneficiary=beneficiary,
            specialist=specialist,
            defaults={
                "assignment_role": BeneficiarySpecialistAssignment.Role.PRIMARY,
                "from_date": beneficiary.enrollment_date,
            },
        )
        return beneficiary

    def _workflows(self, beneficiary: Beneficiary, specialist: SpecialistProfile) -> None:
        visit, _ = ServiceVisit.objects.update_or_create(
            beneficiary=beneficiary,
            specialist=specialist,
            visit_date=date.today() - timedelta(days=2),
            defaults={
                "center": beneficiary.center,
                "visit_type": ServiceVisit.VisitType.CENTER,
                "status": ServiceVisit.Status.COMPLETED,
                "service_units": 1,
                "duration_minutes": 60,
                "notes": "Synthetic completed visit.",
            },
        )
        assessment, _ = Assessment.objects.update_or_create(
            beneficiary=beneficiary,
            specialist=specialist,
            assessment_date=date.today() - timedelta(days=30),
            assessment_type=Assessment.AssessmentType.INITIAL,
            defaults={
                "center": beneficiary.center,
                "scoring_tool": Assessment.ScoringTool.OTHER,
                "total_score": 10,
                "progress_summary": "Synthetic baseline summary.",
            },
        )
        AssessmentDomainScore.objects.update_or_create(
            assessment=assessment,
            domain="Synthetic daily living domain",
            defaults={"baseline_score": 4, "current_score": 6},
        )
        plan, _ = IndividualPlan.objects.update_or_create(
            beneficiary=beneficiary,
            specialist=specialist,
            plan_start_date=date.today() - timedelta(days=20),
            defaults={
                "center": beneficiary.center,
                "status": IndividualPlan.Status.ACTIVE,
                "plan_end_date": date.today() + timedelta(days=70),
                "review_frequency": IndividualPlan.ReviewFrequency.MONTHLY,
                "notes": "Synthetic active plan.",
            },
        )
        IndividualPlanGoal.objects.update_or_create(
            plan=plan,
            goal="Complete a synthetic daily living activity independently.",
            defaults={
                "target_date": date.today() + timedelta(days=30),
                "status": IndividualPlanGoal.Status.IN_PROGRESS,
            },
        )
