import pytest

from .factories import (
    ensure_center_offerings,
    make_beneficiary,
    make_center,
    make_central_hr,
    make_coordinator,
    make_manager,
    make_specialist,
)


@pytest.fixture
def center_a(db):
    center = make_center("Synthetic Center A")
    ensure_center_offerings(center)
    return center


@pytest.fixture
def center_b(db):
    center = make_center("Synthetic Center B")
    ensure_center_offerings(center)
    return center


@pytest.fixture
def manager(db):
    return make_manager()


@pytest.fixture
def central_hr(db):
    return make_central_hr()


@pytest.fixture
def coordinator_a(center_a):
    return make_coordinator(center_a, "coordinator-a")


@pytest.fixture
def specialist_a(center_a):
    return make_specialist(center_a, "specialist-a")


@pytest.fixture
def specialist_b(center_b):
    return make_specialist(center_b, "specialist-b")


@pytest.fixture
def beneficiary_a(center_a, specialist_a):
    return make_beneficiary(center_a, specialist_a, name="Synthetic Beneficiary A")


@pytest.fixture
def beneficiary_b(center_b, specialist_b):
    return make_beneficiary(center_b, specialist_b, name="Synthetic Beneficiary B")
