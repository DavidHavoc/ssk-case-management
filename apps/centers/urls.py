from django.urls import path

from . import views

urlpatterns = [
    path("", views.center_list, name="center_list"),
    path("select/", views.center_select, name="center_select"),
    path("staff/", views.staff_list, name="staff_list"),
    path("staff/<uuid:pk>/", views.staff_detail, name="staff_detail"),
    path("staff/<uuid:pk>/update/", views.staff_update, name="staff_update"),
    path(
        "staff/<uuid:pk>/reset-access/",
        views.staff_reset_access,
        name="staff_reset_access",
    ),
    path(
        "staff/<uuid:pk>/documents/upload/",
        views.staff_attachment_upload,
        name="staff_attachment_upload",
    ),
    path(
        "staff/documents/<uuid:pk>/download/",
        views.staff_attachment_download,
        name="staff_attachment_download",
    ),
    path(
        "staff/documents/<uuid:pk>/delete/",
        views.staff_attachment_delete,
        name="staff_attachment_delete",
    ),
    path("new/", views.center_create, name="center_create"),
    path("current/", views.center_detail, name="center_detail"),
    path("current/update/", views.center_update, name="center_update"),
    path("current/delete/", views.center_delete, name="center_delete"),
    path("current/specialists/link/", views.specialist_assign, name="specialist_assign"),
    path("current/specialists/new/", views.specialist_create, name="specialist_create"),
    path(
        "current/specialists/<uuid:pk>/update/",
        views.specialist_update,
        name="specialist_update",
    ),
    path(
        "current/assignments/<uuid:pk>/remove/",
        views.specialist_remove,
        name="specialist_remove",
    ),
]
