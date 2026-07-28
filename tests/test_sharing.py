from neri_printer_manager.core import CommandResult
from neri_printer_manager.sharing import SharingService, SharingState


class CupsctlRunner:
    def __init__(self, output: str) -> None:
        self.output = output

    def run(self, args, **_kwargs):
        return CommandResult(tuple(args), 0, self.output, "")


def test_cups_sharing_is_healthy_when_limited_to_local_policy() -> None:
    check = SharingService(
        CupsctlRunner("_share_printers=1\n_remote_any=0\n_remote_admin=0")  # type: ignore[arg-type]
    ).cups_status()
    assert check.state is SharingState.ENABLED


def test_cups_remote_any_is_reported_as_misconfigured() -> None:
    check = SharingService(
        CupsctlRunner("_share_printers=1\n_remote_any=1\n_remote_admin=0")  # type: ignore[arg-type]
    ).cups_status()
    assert check.state is SharingState.MISCONFIGURED
    assert check.remediation
