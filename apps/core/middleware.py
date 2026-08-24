from django.shortcuts import redirect


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; object-src 'none'; "
            "frame-ancestors 'none'; form-action 'self'; img-src 'self' data:; "
            "style-src 'self'; script-src 'self'; connect-src 'self'",
        )
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()"
        )
        return response


class RequiredPasswordChangeMiddleware:
    allowed_url_names = {"logout", "password_change_required"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, "user", None)
        if (
            getattr(user, "is_authenticated", False)
            and getattr(user, "must_change_password", False)
            and request.resolver_match.url_name not in self.allowed_url_names
        ):
            return redirect("password_change_required")
        return None
