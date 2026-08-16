from apps.accounts.roles import is_coordinator, is_specialist, is_system_manager

from .authorization import (
    accessible_centers,
    active_center_for_request,
    can_view_staff_directory,
)


def navigation_context(request) -> dict:
    if not getattr(request.user, "is_authenticated", False):
        return {}
    centers = accessible_centers(request.user, active_only=True)
    return {
        "navigation_centers": centers,
        "active_center": active_center_for_request(request, required=False),
        "can_view_staff_directory": can_view_staff_directory(request.user),
        "is_system_manager": is_system_manager(request.user),
        "is_coordinator": is_coordinator(request.user),
        "is_specialist": is_specialist(request.user),
    }
