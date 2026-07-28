import zipfile
from pathlib import Path

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


def test_copied_support_log_does_not_contain_credentials(tmp_path: Path) -> None:
    source = tmp_path / "source.log"
    target = tmp_path / "redacted.log"
    source.write_text(
        "backend smb://DOMINIO%5Cuser:senha-secreta@server/HP failed\n",
        encoding="utf-8",
    )
    ReportService._copy_redacted_log(source, target)
    content = target.read_text(encoding="utf-8")
    assert "senha-secreta" not in content
    assert "smb://***@server/HP" in content
