from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class CompletedAge:
    years: int
    months: int
    total_months: int


def _anniversary_day(birth_date: date, year: int, month: int) -> int:
    """Return the monthly anniversary day, using the month's last day when needed."""
    return min(birth_date.day, calendar.monthrange(year, month)[1])


def calculate_completed_age(birth_date: date, reference_date: date) -> CompletedAge:
    """Calculate completed years and remaining months at an explicit reference date.

    A 29 February birth reaches its anniversary on 28 February in a non-leap year.
    The same last-day rule makes monthly calculations deterministic for every birth
    date near the end of a month.
    """
    if reference_date < birth_date:
        raise ValueError("Reference date cannot be before birth date.")

    total_months = (
        (reference_date.year - birth_date.year) * 12 + reference_date.month - birth_date.month
    )
    anniversary_day = _anniversary_day(
        birth_date,
        reference_date.year,
        reference_date.month,
    )
    if reference_date.day < anniversary_day:
        total_months -= 1

    return CompletedAge(
        years=total_months // 12,
        months=total_months % 12,
        total_months=total_months,
    )


def ssk_age_band(total_months: int) -> str | None:
    """Return the SSK early-intervention band for a completed-month age."""
    if 0 <= total_months <= 35:
        return "0-3"
    if total_months <= 59:
        return "3-5"
    if total_months <= 83:
        return "5-7"
    return None
