from urllib.parse import urlsplit

from django.conf import settings
from django.urls import translate_url
from django.utils import translation
from django.views.i18n import set_language as django_set_language


def set_language(request):
    """Translate Django's validated redirect using the language in its URL."""
    response = django_set_language(request)
    language_cookie = response.cookies.get(settings.LANGUAGE_COOKIE_NAME)
    if response.status_code == 302 and language_cookie is not None:
        source_language = translation.get_language_from_path(urlsplit(response.url).path)
        if source_language:
            with translation.override(source_language):
                response.headers["Location"] = translate_url(response.url, language_cookie.value)
    return response
