import pytest

from neri_printer_manager.core import PrinterManagerError
from neri_printer_manager.cups_filters import CupsFilterService, RepairAction
from neri_printer_manager.dependencies import DependencyService


def test_install_request_accepts_known_packages() -> None:
    assert DependencyService.build_install_request(["cups", "ghostscript", "cups"]) == [
        "cups",
        "ghostscript",
    ]


def test_install_request_rejects_unknown_package() -> None:
    with pytest.raises(PrinterManagerError):
        DependencyService.build_install_request(["cups", "unexpected-package"])


def test_filter_failed_signature_generates_repair_plan() -> None:
    findings = CupsFilterService.analyze_text(
        "E [10/Jul/2026:10:00:00] [Job 20] Filter failed"
    )
    assert len(findings) == 1
    assert findings[0].code == "filter_failed"
    assert RepairAction.REINSTALL_FILTERS in findings[0].actions
    assert RepairAction.REINSTALL_GHOSTSCRIPT in findings[0].actions


def test_duplicate_signatures_are_collapsed() -> None:
    findings = CupsFilterService.analyze_text("Filter failed\nFilter failed")
    assert [item.code for item in findings] == ["filter_failed"]


def test_packages_for_filter_repair() -> None:
    packages = CupsFilterService.packages_for(
        (RepairAction.REINSTALL_FILTERS, RepairAction.REINSTALL_GHOSTSCRIPT)
    )
    assert packages == ["cups", "cups-client", "cups-filters", "ghostscript"]
