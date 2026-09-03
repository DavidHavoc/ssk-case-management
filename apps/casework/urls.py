from django.urls import path

from . import views

urlpatterns = [
    path("my-beneficiaries/", views.specialist_workspace, name="specialist_workspace"),
    path("beneficiaries/", views.beneficiary_list, name="beneficiary_list"),
    path("beneficiaries/new/", views.beneficiary_create, name="beneficiary_create"),
    path("beneficiaries/<uuid:pk>/", views.beneficiary_detail, name="beneficiary_detail"),
    path(
        "beneficiaries/<uuid:pk>/update/",
        views.beneficiary_update,
        name="beneficiary_update",
    ),
    path("beneficiaries/<uuid:pk>/delete/", views.beneficiary_delete, name="beneficiary_delete"),
    path(
        "beneficiaries/<uuid:beneficiary_pk>/enrollments/new/",
        views.enrollment_create,
        name="enrollment_create",
    ),
    path("enrollments/<uuid:pk>/update/", views.enrollment_update, name="enrollment_update"),
    path(
        "enrollments/<uuid:pk>/transition/<str:action>/",
        views.enrollment_transition,
        name="enrollment_transition",
    ),
    path(
        "enrollments/<uuid:pk>/transfer/",
        views.enrollment_transfer,
        name="enrollment_transfer",
    ),
    path(
        "enrollments/<uuid:pk>/re-enroll/",
        views.enrollment_reenroll,
        name="enrollment_reenroll",
    ),
    path("visits/", views.visit_list, name="visit_list"),
    path("visits/new/", views.visit_create, name="visit_create"),
    path("visits/<uuid:pk>/", views.visit_detail, name="visit_detail"),
    path("visits/<uuid:pk>/update/", views.visit_update, name="visit_update"),
    path("visits/<uuid:pk>/delete/", views.visit_delete, name="visit_delete"),
    path("schedules/", views.schedule_list, name="schedule_list"),
    path("schedules/new/", views.schedule_create, name="schedule_create"),
    path("schedules/<uuid:pk>/update/", views.schedule_update, name="schedule_update"),
    path(
        "enrollments/<uuid:enrollment_pk>/schedules/new/",
        views.schedule_create,
        name="enrollment_schedule_create",
    ),
    path("assessments/", views.assessment_list, name="assessment_list"),
    path("assessments/new/", views.assessment_create, name="assessment_create"),
    path("assessments/<uuid:pk>/", views.assessment_detail, name="assessment_detail"),
    path(
        "assessments/<uuid:pk>/update/",
        views.assessment_update,
        name="assessment_update",
    ),
    path("assessments/<uuid:pk>/delete/", views.assessment_delete, name="assessment_delete"),
    path("plans/", views.plan_list, name="plan_list"),
    path("plans/new/", views.plan_create, name="plan_create"),
    path(
        "plans/<uuid:plan_pk>/goals/new/",
        views.plan_goal_create,
        name="plan_goal_create",
    ),
    path(
        "plans/<uuid:plan_pk>/goals/<uuid:pk>/update/",
        views.plan_goal_update,
        name="plan_goal_update",
    ),
    path(
        "plans/<uuid:plan_pk>/goals/<uuid:goal_pk>/measurements/new/",
        views.plan_goal_measurement_create,
        name="plan_goal_measurement_create",
    ),
    path(
        "plans/<uuid:plan_pk>/reviews/new/",
        views.plan_review_create,
        name="plan_review_create",
    ),
    path("plans/<uuid:pk>/", views.plan_detail, name="plan_detail"),
    path("plans/<uuid:pk>/update/", views.plan_update, name="plan_update"),
    path("plans/<uuid:pk>/delete/", views.plan_delete, name="plan_delete"),
    path("summaries/", views.summary_list, name="summary_list"),
    path(
        "attachments/<str:parent_type>/<uuid:parent_id>/upload/",
        views.attachment_upload,
        name="attachment_upload",
    ),
    path("attachments/<uuid:pk>/download/", views.attachment_download, name="attachment_download"),
    path("attachments/<uuid:pk>/delete/", views.attachment_delete, name="attachment_delete"),
]
