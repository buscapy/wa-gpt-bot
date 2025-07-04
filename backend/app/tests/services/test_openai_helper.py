import pytest

from app.services.openai_helper import get_price_url


def test_get_price_url_electrodomestic() -> None:
    url = get_price_url("lavadora whirlpool")
    assert "tupy.com.py" in url


def test_get_price_url_default() -> None:
    url = get_price_url("iphone 13")
    assert "mercadolibre" in url
