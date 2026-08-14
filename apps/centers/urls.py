from django.urls import path

from . import views

urlpatterns = [
    path("", views.center_list, name="center_list"),
    path("select/", views.center_select, name="center_select"),
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
