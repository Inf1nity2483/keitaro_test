import pytest

from app.naming import parse_geos, with_prefix


def test_parse_geos_list_and_dedupe():
    assert parse_geos("mx, AU, ro, au") == ["MX", "AU", "RO"]


def test_parse_geos_rejects_uk_alias():
    with pytest.raises(ValueError, match="GB"):
        parse_geos("UK")


def test_prefix_is_added_once():
    assert with_prefix("campaign1", "test_ivanov_") == "test_ivanov_campaign1"
    assert with_prefix("test_ivanov_campaign1", "test_ivanov_") == "test_ivanov_campaign1"


def test_placeholder_prefix_is_rejected():
    with pytest.raises(ValueError):
        with_prefix("campaign1", "test_фамилия_")
