from urllib.parse import urlsplit

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import translation

from .factories import set_active_center

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("source,target", [("en", "ka"), ("ka", "en")])
@pytest.mark.parametrize("cookie_language", [None, "en", "ka"])
@pytest.mark.parametrize("browser_language", ["en", "ka"])
def test_switch_uses_page_language_despite_cookie_and_browser_preferences(
    client, source, target, cookie_language, browser_language
):
    if cookie_language:
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = cookie_language
    next_url = f"/{source}/accounts/login/?next=%2F{source}%2F#login-title"

    response = client.post(
        reverse("set_language"),
        {"language": target, "next": next_url},
        HTTP_ACCEPT_LANGUAGE=browser_language,
    )

    assert response.status_code == 302
    assert response.url == next_url.replace(f"/{source}/accounts", f"/{target}/accounts")
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == target
    page = client.get(response.url)
    assert page.status_code == 200
    assert page["Content-Language"] == target
    assert f'<html lang="{target}">' in page.content.decode()


@pytest.mark.parametrize("source,target", [("en", "ka"), ("ka", "en")])
def test_authenticated_switch_preserves_current_page_filters_and_center(
    client, manager, center_a, source, target
):
    client.force_login(manager)
    set_active_center(client, center_a)
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = target
    with translation.override(source):
        next_url = reverse("beneficiary_list") + "?q=SYNTHETIC&status=active"
    page = client.get(next_url)
    assert 'class="language-form"' in page.content.decode()

    response = client.post(reverse("set_language"), {"language": target, "next": next_url})

    assert response.url == next_url.replace(f"/{source}/", f"/{target}/", 1)
    page = client.get(response.url)
    assert page.status_code == 200
    assert page["Content-Language"] == target
    assert page.context["active_center"] == center_a


@pytest.mark.parametrize("source,target", [("en", "ka"), ("ka", "en")])
def test_switch_works_while_required_password_change_still_blocks_casework(
    client, specialist_a, source, target
):
    user = specialist_a.staff_profile.user
    user.must_change_password = True
    user.save(update_fields=["must_change_password"])
    client.force_login(user)
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = target
    next_url = f"/{source}/accounts/password/change/"

    response = client.post(reverse("set_language"), {"language": target, "next": next_url})

    assert response.url == f"/{target}/accounts/password/change/"
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == target
    page = client.get(response.url)
    assert page.status_code == 200
    assert page["Content-Language"] == target
    denied = client.get(f"/{target}/casework/beneficiaries/")
    assert denied.status_code == 302
    assert denied.url == response.url
    user.refresh_from_db()
    assert user.must_change_password


@pytest.mark.parametrize("next_url", ["https://outside.invalid/ka/", "//outside.invalid/ka/"])
def test_switch_rejects_external_redirect_and_translates_safe_referer(client, next_url):
    response = client.post(
        reverse("set_language"),
        {"language": "en", "next": next_url},
        HTTP_REFERER="http://testserver/ka/accounts/login/?next=%2Fka%2F",
        HTTP_ACCEPT_LANGUAGE="en",
    )

    assert response.url == "http://testserver/en/accounts/login/?next=%2Fka%2F"
    assert urlsplit(response.url).hostname == "testserver"


def test_switch_requires_csrf_and_does_not_change_language_on_get_or_invalid_language(client):
    csrf_client = Client(enforce_csrf_checks=True)
    denied = csrf_client.post(
        reverse("set_language"), {"language": "ka", "next": "/en/accounts/login/"}
    )
    assert denied.status_code == 403
    assert settings.LANGUAGE_COOKIE_NAME not in denied.cookies

    unchanged = client.get(
        reverse("set_language"), {"language": "ka", "next": "/en/accounts/login/"}
    )
    assert settings.LANGUAGE_COOKIE_NAME not in unchanged.cookies
    invalid = client.post(
        reverse("set_language"), {"language": "invalid", "next": "/en/accounts/login/"}
    )
    assert invalid.url == "/en/accounts/login/"
    assert settings.LANGUAGE_COOKIE_NAME not in invalid.cookies
