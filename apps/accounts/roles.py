from __future__ import annotations

from django.contrib.auth.models import Group
from django.db.models import QuerySet

SYSTEM_MANAGER = "System Manager"
COORDINATOR = "SSK Center Coordinator"
SPECIALIST = "SSK Specialist"
APPLICATION_ROLES = (SYSTEM_MANAGER, COORDINATOR, SPECIALIST)


def has_role(user, role: str) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser and role == SYSTEM_MANAGER:
        return True
    cached = getattr(user, "_ssk_role_names", None)
    if cached is None:
        cached = set(user.groups.values_list("name", flat=True))
        user._ssk_role_names = cached
    return role in cached


def is_system_manager(user) -> bool:
    return has_role(user, SYSTEM_MANAGER)


def is_coordinator(user) -> bool:
    return has_role(user, COORDINATOR)


def is_specialist(user) -> bool:
    return has_role(user, SPECIALIST)


def ensure_application_groups() -> QuerySet[Group]:
    for role in APPLICATION_ROLES:
        Group.objects.get_or_create(name=role)
    return Group.objects.filter(name__in=APPLICATION_ROLES)
