from datetime import date, datetime

import pytest
from django import forms
from django.utils import formats, translation

from apps.core.forms import StyledForm
from apps.core.reporting import safe_csv_value
from apps.core.views import _parse_report_date


class ExampleDateForm(StyledForm):
    event_date = forms.DateField()


@pytest.mark.parametrize("language", ["en", "ka"])
def test_dates_are_displayed_day_first(language):
    with translation.override(language):
        assert formats.date_format(date(2026, 8, 20), "SHORT_DATE_FORMAT") == "20/08/2026"
        assert (
            formats.date_format(datetime(2026, 8, 20, 14, 5), "SHORT_DATETIME_FORMAT")
            == "20/08/2026 14:05"
        )


def test_date_fields_display_and_accept_day_first_dates():
    form = ExampleDateForm(initial={"event_date": date(2026, 8, 20)})

    assert 'value="20/08/2026"' in str(form["event_date"])
    assert 'placeholder="DD/MM/YYYY"' in str(form["event_date"])
    assert ExampleDateForm({"event_date": "20/08/2026"}).is_valid()


def test_iso_date_input_remains_accepted_for_integrations():
    assert ExampleDateForm({"event_date": "2026-08-20"}).is_valid()


def test_report_dates_use_and_parse_day_first_format():
    assert safe_csv_value(date(2026, 8, 20)) == "20/08/2026"
    assert _parse_report_date("20/08/2026") == date(2026, 8, 20)
    assert _parse_report_date("2026-08-20") == date(2026, 8, 20)
