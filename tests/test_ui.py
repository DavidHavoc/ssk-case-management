import pytest
from django.urls import reverse
from django.utils import translation

from .factories import set_active_center

pytestmark = pytest.mark.django_db


def test_login_uses_public_shell_and_accessible_form_structure(client):
    response = client.get(reverse("login"))

    assert response.status_code == 200
    body = response.content.decode()
    assert 'class="has-auth-shell"' in body
    assert 'id="main-content"' in body
    assert 'aria-labelledby="login-title"' in body
    assert 'href="#main-content"' in body
    assert 'src="/static/js/app.js"' in body
    assert 'src="/static/img/ssk-logo.png"' in body
    assert 'class="brand-mark"' not in body
    assert 'id="primary-sidebar"' not in body


def test_authenticated_shell_marks_active_page_and_exposes_mobile_navigation(
    client, manager, center_a, beneficiary_a
):
    client.force_login(manager)
    set_active_center(client, center_a)

    response = client.get(reverse("beneficiary_list"))

    assert response.status_code == 200
    body = response.content.decode()
    assert 'class="has-app-shell"' in body
    assert 'id="primary-sidebar"' in body
    assert 'src="/static/img/ssk-logo.png"' in body
    assert 'aria-controls="primary-sidebar" aria-expanded="false"' in body
    assert (
        'class="nav-item is-active" href="'
        f'{reverse("beneficiary_list")}" aria-current="page"' in body
    )
    assert f'href="{reverse("audit_log")}"' in body
    assert 'class="table-wrap" tabindex="0" role="region"' in body
    assert 'class="status status-active"' in body


def test_specialist_shell_does_not_expose_manager_navigation(
    client, specialist_a, center_a, beneficiary_a
):
    client.force_login(specialist_a.staff_profile.user)
    set_active_center(client, center_a)

    response = client.get(reverse("dashboard"))

    assert response.status_code == 200
    body = response.content.decode()
    assert f'href="{reverse("center_list")}"' not in body
    assert f'href="{reverse("audit_log")}"' not in body
    assert f'href="{reverse("summary_list")}"' in body


def test_long_form_validation_has_linked_error_summary(client, manager, center_a):
    client.force_login(manager)
    set_active_center(client, center_a)

    response = client.post(reverse("center_create"), {"is_active": "on"})

    assert response.status_code == 200
    body = response.content.decode()
    assert 'class="alert alert-error validation-summary" role="alert"' in body
    assert 'href="#id_code"' in body
    assert 'id="id_code-error" role="alert"' in body


def test_georgian_shell_renders_new_navigation_labels(client, manager, center_a):
    client.force_login(manager)
    set_active_center(client, center_a)

    with translation.override("ka"):
        response = client.get(reverse("dashboard"))

    assert response.status_code == 200
    body = response.content.decode()
    assert "სამუშაო სივრცე" in body
    assert "ოპერაციები" in body
    assert "სისტემის მენეჯერი" in body
