from enum import Enum

from neri_printer_manager.security import redact_data, redact_text


class ExampleState(str, Enum):
    READY = "ready"


def test_uri_credentials_are_redacted() -> None:
    message = "Falha em smb://DOMINIO%5Cuser:segredo@server/HP"
    sanitized = redact_text(message)
    assert "segredo" not in sanitized
    assert "DOMINIO" not in sanitized
    assert "smb://***@server/HP" in sanitized


def test_secret_mapping_values_are_redacted_recursively() -> None:
    payload = {
        "username": "same",
        "password": "nao-vazar",
        "nested": {"access_token": "nao-vazar-tambem"},
        "state": ExampleState.READY,
    }
    sanitized = redact_data(payload)
    assert sanitized["username"] == "same"
    assert sanitized["password"] == "***"
    assert sanitized["nested"]["access_token"] == "***"
    assert sanitized["state"] == "ready"


def test_assignment_and_authorization_headers_are_redacted() -> None:
    text = "password = segredo\ntoken=abcdef\nAuthorization: Basic abcdef\x1b[31m"
    sanitized = redact_text(text)
    assert "segredo" not in sanitized
    assert "abcdef" not in sanitized
    assert "\x1b" not in sanitized
