from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health_view, name="health"),
    path("", views.dashboard, name="dashboard"),
    path("reports/", views.report_view, name="reports"),
    path("reports/export.csv", views.report_export, name="report_export"),
    path("reminders/", views.reminder_list, name="reminders"),
    path("audit/", views.audit_log, name="audit_log"),
]
