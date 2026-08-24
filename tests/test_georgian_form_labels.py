import pytest
from django.utils import translation

from apps.casework.forms import (
    AssessmentForm,
    BeneficiaryForm,
    EnrollmentIntakeForm,
    EnrollmentServiceScheduleForm,
    IndividualPlanForm,
    IndividualPlanGoalForm,
    ServiceVisitForm,
)


@pytest.mark.django_db
def test_casework_forms_have_georgian_labels(coordinator_a, center_a):
    with translation.override("ka"):
        beneficiary_form = BeneficiaryForm(user=coordinator_a, center=center_a)
        intake_form = EnrollmentIntakeForm(center=center_a)
        visit_form = ServiceVisitForm(user=coordinator_a, center=center_a)
        schedule_form = EnrollmentServiceScheduleForm(user=coordinator_a, center=center_a)
        assessment_form = AssessmentForm(user=coordinator_a, center=center_a)
        plan_form = IndividualPlanForm(user=coordinator_a, center=center_a)
        goal_form = IndividualPlanGoalForm()

        assert str(beneficiary_form.fields["beneficiary_code"].label) == "ბენეფიციარის კოდი"
        assert str(beneficiary_form.fields["notes"].label) == "შენიშვნები"
        assert str(intake_form.fields["status"].label) == "სტატუსი"
        assert str(intake_form.fields["first_service_date"].label) == "მომსახურების პირველი თარიღი"
        assert str(visit_form.fields["enrollment"].label) == "ჩარიცხვა"
        assert str(visit_form.fields["specialist"].label) == "სპეციალისტი"
        assert str(visit_form.fields["activity"].label) == "აქტივობა"
        assert str(schedule_form.fields["planned_visits"].label) == "დაგეგმილი ვიზიტები"
        assert str(assessment_form.fields["assessment_date"].label) == "შეფასების თარიღი"
        assert str(plan_form.fields["plan_start_date"].label) == "გეგმის დაწყების თარიღი"
        assert str(plan_form.fields["review_due_date"].label) == "განხილვის ვადა"
        assert str(goal_form.fields["goal"].label) == "მიზანი"
        assert str(goal_form.fields["category"].label) == "კატეგორია"
        assert str(goal_form.fields["baseline"].label) == "საწყისი მაჩვენებელი"
        assert str(goal_form.fields["measurable_target"].label) == "გაზომვადი სამიზნე"
        assert str(goal_form.fields["responsible_specialist"].label) == "პასუხისმგებელი სპეციალისტი"
        assert str(goal_form.fields["progress_notes"].label) == "პროგრესის შენიშვნები"
        assert dict(visit_form.fields["status"].choices)["planned"] == "დაგეგმილი"
        assert dict(plan_form.fields["status"].choices)["active"] == "აქტიური"
        assert dict(goal_form.fields["status"].choices)["achieved"] == "მიღწეული"
        assert dict(goal_form.fields["status"].choices)["cancelled"] == "გაუქმებული"
