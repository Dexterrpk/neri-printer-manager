from pathlib import Path
import zipfile

from neri_printer_manager.reports import ReportService


def test_html_report_is_written(monkeypatch, tmp_path: Path) -> None:
    service = ReportService()
    monkeypatch.setattr(
        service,
        "collect",
        lambda: {"generated_at": "now", "system": {"hostname": "mint-test"}},
    )
    target = service.write_html(tmp_path / "report.html")
    content = target.read_text(encoding="utf-8")
    assert "Relatório Técnico" in content
    assert "mint-test" in content


def test_json_report_is_written(monkeypatch, tmp_path: Path) -> None:
    service = ReportService()
    monkeypatch.setattr(service, "collect", lambda: {"ok": True})
    target = service.write_json(tmp_path / "report.json")
    assert '"ok": true' in target.read_text(encoding="utf-8")


def test_support_bundle_contains_reports(monkeypatch, tmp_path: Path) -> None:
    service = ReportService()
    monkeypatch.setattr(service, "collect", lambda: {"ok": True})
    archive = service.create_support_bundle(tmp_path)
    assert archive.is_file()
    with zipfile.ZipFile(archive) as bundle:
        assert {"report.json", "report.html"}.issubset(set(bundle.namelist()))
