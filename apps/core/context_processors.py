from apps.accounts.roles import is_central_hr, is_coordinator, is_specialist, is_system_manager

from .authorization import (
    accessible_centers,
    active_center_for_request,
    can_view_staff_directory,
    casework_home_route,
)


def navigation_context(request) -> dict:
    if not getattr(request.user, "is_authenticated", False):
        return {}
    centers = accessible_centers(request.user, active_only=True)
    has_casework_access = is_system_manager(request.user) or centers.exists()
    return {
        "navigation_centers": centers,
        "active_center": active_center_for_request(request, required=False),
        "can_view_staff_directory": can_view_staff_directory(request.user),
        "has_casework_access": has_casework_access,
        "navigation_home_route": (
            casework_home_route(request.user) if has_casework_access else "staff_list"
        ),
        "is_system_manager": is_system_manager(request.user),
        "is_central_hr": is_central_hr(request.user),
        "is_coordinator": is_coordinator(request.user),
        "is_specialist": is_specialist(request.user),
        "is_specialist_only": is_specialist(request.user)
        and not (is_coordinator(request.user) or is_system_manager(request.user)),
    }
