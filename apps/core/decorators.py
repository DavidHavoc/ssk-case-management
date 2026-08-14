from functools import wraps
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from .authorization import CenterSelectionRequired, active_center_for_request


def active_center_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        try:
            request.ssk_center = active_center_for_request(request)
        except CenterSelectionRequired:
            query = urlencode({"next": request.get_full_path()})
            return redirect(f"/centers/select/?{query}")
        except PermissionDenied:
            raise
        return view_func(request, *args, **kwargs)

    return wrapped
