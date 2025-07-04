from unittest.mock import MagicMock, patch

from app.services.openai_helper import format_price_msg, get_price_url


def test_get_price_url_returns_stripped_url() -> None:
    url = "https://example.com/product"
    mock_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = f"  {url}\n"
    mock_resp.choices = [mock_choice]
    client_mock = MagicMock()
    client_mock.chat.completions.create.return_value = mock_resp

    with patch("app.services.openai_helper.client", client_mock):
        result = get_price_url("PlayStation")

    assert result == url
    client_mock.chat.completions.create.assert_called_once()


def test_format_price_msg_splits_lines() -> None:
    message = "Precio: 100\nRecomendado.\n"
    mock_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = message
    mock_resp.choices = [mock_choice]
    client_mock = MagicMock()
    client_mock.chat.completions.create.return_value = mock_resp

    with patch("app.services.openai_helper.client", client_mock):
        result = format_price_msg("PlayStation", {"price": 100})

    assert result == ["Precio: 100", "Recomendado."]
    client_mock.chat.completions.create.assert_called_once()
