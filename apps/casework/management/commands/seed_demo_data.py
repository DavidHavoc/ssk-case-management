from __future__ import annotations

import os
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.roles import COORDINATOR, SPECIALIST, SYSTEM_MANAGER, ensure_application_groups
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
    EnrollmentCenterPlacement,
    EnrollmentServiceSchedule,
    EnrollmentSpecialistAssignment,
    EnrollmentStateEvent,
    GoalCategory,
    GoalOutcomeMeasurement,
    GoalStatusTransition,
    IndividualPlan,
    IndividualPlanGoal,
    IndividualPlanReview,
    ServiceActivityDefinition,
    ServiceDefinition,
    ServiceEnrollment,
    ServiceVisit,
    VisitLocationDefinition,
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
            offerings = self._offerings(alpha, beta)

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

            beneficiary_a, enrollment_a = self._beneficiary(
                "BEN-DEMO-0001",
                "Synthetic Beneficiary Alpha",
                alpha,
                specialist_a,
                offerings[(alpha.pk, "HOME-CARE")],
            )
            beneficiary_multi, enrollment_multi = self._beneficiary(
                "BEN-DEMO-0002",
                "Synthetic Beneficiary Multi",
                alpha,
                specialist_multi,
                offerings[(alpha.pk, "EARLY-INTERVENTION")],
            )
            self._enrollment(
                beneficiary_multi,
                specialist_multi,
                offerings[(alpha.pk, "FOOD-DELIVERY")],
                "BEN-DEMO-0002-E02",
            )
            beneficiary_b, enrollment_b = self._beneficiary(
                "BEN-DEMO-0003",
                "Synthetic Beneficiary Beta",
                beta,
                specialist_b,
                offerings[(beta.pk, "HOME-CARE")],
            )
            self._workflows(beneficiary_a, specialist_a, enrollment_a)
            self._workflows(beneficiary_multi, specialist_multi, enrollment_multi)
            self._workflows(beneficiary_b, specialist_b, enrollment_b)

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

    def _offerings(self, alpha: Center, beta: Center):
        offerings = {}
        for center in (alpha, beta):
            for service in ServiceDefinition.objects.filter(
                code__in=("HOME-CARE", "FOOD-DELIVERY", "EARLY-INTERVENTION")
            ):
                offering, _ = CenterServiceOffering.objects.get_or_create(
                    center=center,
                    service=service,
                    valid_from=date(2026, 1, 1),
                )
                offerings[(center.pk, service.code)] = offering
        return offerings

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
                "project_program": "Synthetic SSK Demonstration Program",
                "job_title": role,
                "contact_number": "+995 555 000 100",
                "contract_signed_on": date(2026, 1, 1),
                "contract_valid_until": date(2026, 12, 31),
                "notes": "Synthetic staff note for local demonstration only.",
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
        self,
        code: str,
        name: str,
        center: Center,
        specialist: SpecialistProfile,
        offering: CenterServiceOffering,
    ) -> tuple[Beneficiary, ServiceEnrollment]:
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
        enrollment = self._enrollment(
            beneficiary,
            specialist,
            offering,
            f"{code}-E01",
        )
        return beneficiary, enrollment

    def _enrollment(
        self,
        beneficiary: Beneficiary,
        specialist: SpecialistProfile,
        offering: CenterServiceOffering,
        episode_code: str,
    ) -> ServiceEnrollment:
        start_date = date.today() - timedelta(days=60)
        enrollment, _ = ServiceEnrollment.objects.update_or_create(
            episode_code=episode_code,
            defaults={
                "beneficiary": beneficiary,
                "service": offering.service,
                "status": ServiceEnrollment.Status.ACTIVE,
                "start_date": start_date,
                "notes": "Synthetic service enrollment.",
            },
        )
        EnrollmentCenterPlacement.objects.get_or_create(
            enrollment=enrollment,
            defaults={
                "center": offering.center,
                "offering": offering,
                "valid_from": start_date,
            },
        )
        EnrollmentSpecialistAssignment.objects.get_or_create(
            enrollment=enrollment,
            specialist=specialist,
            valid_from=start_date,
            defaults={"assignment_role": EnrollmentSpecialistAssignment.Role.PRIMARY},
        )
        EnrollmentStateEvent.objects.get_or_create(
            enrollment=enrollment,
            kind=EnrollmentStateEvent.Kind.ADMISSION,
            effective_date=start_date,
            defaults={
                "previous_state": "",
                "new_state": ServiceEnrollment.Status.ACTIVE,
                "actor": specialist.staff_profile.user,
            },
        )
        return enrollment

    def _workflows(
        self,
        beneficiary: Beneficiary,
        specialist: SpecialistProfile,
        enrollment: ServiceEnrollment,
    ) -> None:
        activity = ServiceActivityDefinition.objects.get(code="INDIVIDUAL-MEETING")
        location = VisitLocationDefinition.objects.get(code="CENTER")
        visit, _ = ServiceVisit.objects.update_or_create(
            beneficiary=beneficiary,
            specialist=specialist,
            visit_date=date.today() - timedelta(days=2),
            defaults={
                "enrollment": enrollment,
                "center": beneficiary.center,
                "activity": activity,
                "delivery_location": location,
                "participation_format": "individual",
                "status": ServiceVisit.Status.COMPLETED,
                "service_units": 1,
                "duration_minutes": 60,
                "notes": "Synthetic completed visit.",
            },
        )
        EnrollmentServiceSchedule.objects.update_or_create(
            enrollment=enrollment,
            schedule_month=date.today().replace(day=1),
            activity=activity,
            delivery_location=location,
            participation_format="individual",
            defaults={
                "planned_visits": 4,
                "planned_units": 4,
                "expected_participants": 1,
                "notes": "Synthetic monthly service schedule.",
            },
        )
        instrument = AssessmentInstrument.objects.get(code="OTHER")
        template = AssessmentTemplateVersion.objects.filter(
            instrument=instrument,
            version="synthetic-demo-1",
        ).first()
        if template is None:
            template = AssessmentTemplateVersion.objects.create(
                instrument=instrument,
                version="synthetic-demo-1",
                name="Synthetic demonstration assessment",
                comparison_group="SYNTHETIC-DEMO",
                publication_notes="Synthetic structural example with no licensed questions.",
            )
            section = AssessmentTemplateSection.objects.create(
                template_version=template,
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
            template.publish()
        assessment, _ = Assessment.objects.update_or_create(
            beneficiary=beneficiary,
            specialist=specialist,
            assessment_date=date.today() - timedelta(days=30),
            assessment_type=Assessment.AssessmentType.INITIAL,
            defaults={
                "enrollment": enrollment,
                "center": beneficiary.center,
                "scoring_tool": template.instrument.identifier,
                "template_version": template,
                "progress_summary": "Synthetic baseline summary.",
            },
        )
        if assessment.status == Assessment.Status.DRAFT:
            replace_draft_responses(
                assessment,
                [
                    {
                        "template_field": template.fields.get(code="SYNTHETIC_SCORE"),
                        "numeric_value": 10,
                    }
                ],
            )
            assessment = complete_assessment(assessment)
        plan, _ = IndividualPlan.objects.update_or_create(
            beneficiary=beneficiary,
            specialist=specialist,
            plan_start_date=date.today() - timedelta(days=20),
            defaults={
                "enrollment": enrollment,
                "center": beneficiary.center,
                "status": IndividualPlan.Status.ACTIVE,
                "plan_end_date": date.today() + timedelta(days=70),
                "review_frequency": IndividualPlan.ReviewFrequency.MONTHLY,
                "notes": "Synthetic active plan.",
            },
        )
        goal, _ = IndividualPlanGoal.objects.update_or_create(
            plan=plan,
            goal="Complete a synthetic daily living activity independently.",
            defaults={
                "category": GoalCategory.objects.get(code="LEGACY-UNCLASSIFIED"),
                "baseline": "Requires specialist prompting for the synthetic activity.",
                "measurable_target": "Completes the synthetic activity without prompting.",
                "measurement_type": IndividualPlanGoal.MeasurementType.RATING_SCALE,
                "measurement_unit_or_scale": "Independent, prompted, not completed",
                "responsible_specialist": specialist,
                "target_date": date.today() + timedelta(days=30),
                "status": IndividualPlanGoal.Status.IN_PROGRESS,
                "progress_notes": "Synthetic progress is recorded for demonstration only.",
                "requires_review": False,
            },
        )
        goal.assessment_findings.add(assessment)
        visit.goals_worked_on.add(goal)
        GoalStatusTransition.objects.get_or_create(
            goal=goal,
            from_status="",
            to_status=IndividualPlanGoal.Status.IN_PROGRESS,
            defaults={
                "transition_date": plan.plan_start_date,
                "actor": specialist.staff_profile.user,
                "reason": "Synthetic initial goal state.",
            },
        )
        GoalOutcomeMeasurement.objects.get_or_create(
            goal=goal,
            measurement_date=date.today() - timedelta(days=2),
            defaults={
                "rating": "Prompted",
                "unit_or_scale": goal.measurement_unit_or_scale,
                "interpretation": "Synthetic improvement from the baseline.",
                "notes": "Synthetic measurement for local demonstration.",
                "recorded_by": specialist.staff_profile.user,
                "source_assessment": assessment,
            },
        )
        IndividualPlanReview.objects.get_or_create(
            plan=plan,
            review_date=date.today() - timedelta(days=1),
            defaults={
                "condition_outcome": IndividualPlanReview.ConditionOutcome.IMPROVED,
                "rationale": "Synthetic review based on recorded goal progress.",
                "recorded_by": specialist.staff_profile.user,
                "source_assessment": assessment,
            },
        )
