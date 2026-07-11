import pytest

from neri_printer_manager.core import (
    CommandRunner,
    PrinterManagerError,
    validate_device_uri,
    validate_job_id,
    validate_queue_name,
)


def test_safe_queue_name() -> None:
    assert validate_queue_name("RECEPCAO-01") == "RECEPCAO-01"


@pytest.mark.parametrize("value", ["", "fila com espaço", "x;rm", "a/b"])
def test_unsafe_queue_names_are_rejected(value: str) -> None:
    with pytest.raises(PrinterManagerError):
        validate_queue_name(value)


@pytest.mark.parametrize(
    "value",
    [
        "ipp://printer.local/ipp/print",
        "socket://10.0.0.5:9100",
        "smb://server/printer",
    ],
)
def test_supported_device_uris(value: str) -> None:
    assert validate_device_uri(value) == value


def test_unknown_device_protocol_is_rejected() -> None:
    with pytest.raises(PrinterManagerError):
        validate_device_uri("file:///tmp/output")


def test_valid_job_id() -> None:
    assert validate_job_id("RECEPCAO-42") == "RECEPCAO-42"


@pytest.mark.parametrize("value", ["", "42", "fila 1", "fila-1;rm"])
def test_invalid_job_id_is_rejected(value: str) -> None:
    with pytest.raises(PrinterManagerError):
        validate_job_id(value)


def test_command_runner_captures_output() -> None:
    result = CommandRunner().run(["python3", "-c", "print('ok')"])
    assert result.stdout == "ok"
    assert result.returncode == 0
