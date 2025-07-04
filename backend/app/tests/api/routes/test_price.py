from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings


def test_price_returns_messages(client: TestClient) -> None:
    fake_msgs = ["Precio 1", "Compra ya"]
    fake_data = [{"price": "1", "date": "2024-01-01", "shop": "Shop", "city": "Asu"}]
    with (
        patch("app.services.openai_helper.get_price_url", return_value="http://example.com"),
        patch("app.services.openai_helper.format_price_msg", return_value=fake_msgs),
        patch("app.scrapers.basic.scrape", return_value=fake_data),
        patch("app.scrapers.basic.requests.get"),
    ):
        r = client.post(f"{settings.API_V1_STR}/price", json={"product": "phone"})
    assert r.status_code == 200
    assert r.json() == {"messages": fake_msgs}


def test_price_no_data(client: TestClient) -> None:
    with (
        patch("app.services.openai_helper.get_price_url", return_value="http://example.com"),
        patch("app.scrapers.basic.scrape", return_value={"price": "#"}),
        patch("app.scrapers.basic.requests.get"),
    ):
        r = client.post(f"{settings.API_V1_STR}/price", json={"product": "phone"})
    assert r.status_code == 200
    assert r.json() == {"messages": [], "error": "no_data"}
