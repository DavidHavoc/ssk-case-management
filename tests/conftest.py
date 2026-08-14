import pytest

from .factories import (
    make_beneficiary,
    make_center,
    make_coordinator,
    make_manager,
    make_specialist,
)


@pytest.fixture
def center_a(db):
    return make_center("Synthetic Center A")


@pytest.fixture
def center_b(db):
    return make_center("Synthetic Center B")


@pytest.fixture
def manager(db):
    return make_manager()


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
