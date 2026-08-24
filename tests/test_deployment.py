from __future__ import annotations

import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import translation

from apps.casework.models import Beneficiary, ServiceEnrollment, ServiceVisit
from apps.core.reporting import report_headers

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def _production_settings_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "DJANGO_DEBUG": "0",
            "DJANGO_SECRET_KEY": (
                "synthetic-production-test-secret-with-more-than-fifty-characters-12345"
            ),
            "DJANGO_ALLOWED_HOSTS": "cases.example.invalid",
            "DATABASE_URL": "postgresql://synthetic:synthetic@database.invalid:5432/synthetic",
        }
    )
    environment.pop("SSK_USE_SQLITE", None)
    return environment


def _import_settings(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_production_settings_fail_closed_for_missing_or_unsafe_values():
    valid = _production_settings_environment()
    assert _import_settings(valid).returncode == 0

    missing_database = valid.copy()
    missing_database.pop("DATABASE_URL")
    result = _import_settings(missing_database)
    assert result.returncode != 0
    assert "DATABASE_URL" in result.stderr

    wildcard_host = valid.copy()
    wildcard_host["DJANGO_ALLOWED_HOSTS"] = "*"
    result = _import_settings(wildcard_host)
    assert result.returncode != 0
    assert "explicit production hosts" in result.stderr


def test_access_log_formats_omit_query_strings():
    gunicorn_config = runpy.run_path(REPOSITORY_ROOT / "config/gunicorn.conf.py")

    assert "%(U)s" in gunicorn_config["access_log_format"]
    assert "%(r)s" not in gunicorn_config["access_log_format"]
    assert "%(q)s" not in gunicorn_config["access_log_format"]

    nginx = (REPOSITORY_ROOT / "deploy/nginx.conf").read_text()
    assert '"$request_method $uri $server_protocol"' in nginx
    log_format = nginx.split("server {", 1)[0]
    assert "$request " not in log_format
    assert "$request_uri" not in log_format


def test_secret_and_generated_file_patterns_are_ignored():
    gitignore = set((REPOSITORY_ROOT / ".gitignore").read_text().splitlines())
    assert {".env*", "deploy/tls/", "backups/", "*.sqlite3"} <= gitignore

    dockerignore = set((REPOSITORY_ROOT / ".dockerignore").read_text().splitlines())
    assert {".env*", "deploy/tls", "backups", "*.sqlite3"} <= dockerignore


def test_georgian_catalog_has_no_empty_or_fuzzy_application_messages():
    catalog = (REPOSITORY_ROOT / "locale/ka/LC_MESSAGES/django.po").read_text()
    assert catalog.count('\nmsgstr ""\n') == 1
    assert "#, fuzzy" not in catalog


def test_report_exports_have_georgian_headers():
    with translation.override("ka"):
        assert report_headers("visits") == [
            "ბენეფიციარის კოდი",
            "ბენეფიციარი",
            "ჩარიცხვის კოდი",
            "მომსახურება",
            "სპეციალისტი",
            "ვიზიტის თარიღი",
            "აქტივობა",
            "მომსახურების ადგილი",
            "ფორმატი",
            "სტატუსი",
            "ერთეულები",
            "ხანგრძლივობა წუთებში",
            "მონაწილეები",
            "გაუქმების მიზეზი",
        ]


@override_settings(DEBUG=False)
def test_demo_seed_refuses_to_run_outside_debug_mode():
    with pytest.raises(CommandError, match="only when DJANGO_DEBUG is enabled"):
        call_command("seed_demo_data")


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_demo_seed_is_idempotent_and_includes_multiple_service_enrollments():
    call_command("seed_demo_data", verbosity=0)
    call_command("seed_demo_data", verbosity=0)

    beneficiary = Beneficiary.objects.get(beneficiary_code="BEN-DEMO-0002")
    assert beneficiary.enrollments.count() == 2
    assert (
        ServiceEnrollment.objects.filter(
            beneficiary__beneficiary_code__startswith="BEN-DEMO-"
        ).count()
        == 4
    )
    assert not ServiceVisit.objects.filter(
        beneficiary__beneficiary_code__startswith="BEN-DEMO-", enrollment__isnull=True
    ).exists()
