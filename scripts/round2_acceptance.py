"""Round-2 local acceptance checks for KBPrep.

This script creates temporary source files and verifies the user-facing
conversion and routing promises from the second audit closeout.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PYTHONPATH = str(ROOT / "python")
PYTHON = sys.executable if Path(sys.executable).is_file() else (shutil.which("python") or "python")


def main() -> None:
    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="kbprep-round2-") as tmp:
        temp_root = Path(tmp)
        results.append(check_markdown_success_with_local_image(temp_root))
        results.append(check_unknown_suffix_is_unsupported(temp_root))
        results.append(check_content_sniffing_routes(temp_root))
        results.append(check_pdf_text_layer_fallback_record(temp_root))
        results.append(check_missing_local_image_is_explicit(temp_root))
        results.append(check_html_conversion_preserves_knowledge_content(temp_root))

    print(json.dumps({"ok": True, "checks": results}, ensure_ascii=False, indent=2))


def run_worker(command: str, payload: dict, cwd: Path | None = None) -> tuple[int, dict, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = PYTHONPATH + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    completed = subprocess.run(
        [PYTHON, "-m", "kbprep_worker.cli", command, "--json-stdin"],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(cwd or ROOT),
        env=env,
        timeout=90,
        check=False,
    )
    return completed.returncode, parse_envelope(completed.stdout), completed.stderr


def parse_envelope(stdout: str) -> dict:
    for line in reversed([line.strip() for line in stdout.splitlines() if line.strip()]):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise AssertionError(f"Worker did not emit a JSON envelope. stdout={stdout!r}")


def check_markdown_success_with_local_image(root: Path) -> dict:
    source_dir = root / "markdown"
    source_dir.mkdir()
    (source_dir / "images").mkdir()
    (source_dir / "images" / "step.png").write_bytes(b"png")
    source = source_dir / "lesson.md"
    source.write_text(
        "\n".join([
            "# 操作教程",
            "",
            "步骤1：设置 threshold=0.8，并记录参数。",
            "",
            "```python",
            "print('ok')",
            "```",
            "",
            "| 字段 | 值 |",
            "| --- | --- |",
            "| retry_count | 3 |",
            "",
            "![后台截图](images/step.png)",
            "",
        ]),
        encoding="utf-8",
    )
    code, envelope, stderr = run_worker(
        "prepare",
        {"input_path": str(source), "output_root": str(root / "out-md"), "force": True, "profile": "standard"},
    )
    assert code == 0 and envelope.get("ok") is True, stderr
    data = envelope["data"]
    assert data["strict_errors"] == []
    run_dir = Path(data["run_dir"])
    assert (run_dir / "images" / "step.png").exists()
    quality = json.loads(Path(data["latest_outputs"]["quality_report"]).read_text(encoding="utf-8"))
    assert not quality.get("strict_errors")
    final_md = Path(data["latest_outputs"]["final_md"])
    assert final_md.exists() and "threshold=0.8" in final_md.read_text(encoding="utf-8")
    return {"name": "markdown_success_local_image", "ok": True, "run_dir": str(run_dir)}


def check_unknown_suffix_is_unsupported(root: Path) -> dict:
    source = root / "unknown.weird"
    source.write_text("plain text but unsupported suffix", encoding="utf-8")
    code, envelope, _stderr = run_worker(
        "prepare",
        {"input_path": str(source), "output_root": str(root / "out-weird"), "force": True},
    )
    assert code != 0 and envelope.get("ok") is False
    assert envelope["error"]["code"] == "E_UNSUPPORTED_TYPE"
    return {"name": "unknown_suffix_unsupported", "ok": True, "code": envelope["error"]["code"]}


def check_content_sniffing_routes(root: Path) -> dict:
    sys.path.insert(0, PYTHONPATH)
    from kbprep_worker.converter_registry import ConversionRouteKind, file_identity_for_path, select_conversion_route

    pdf_like = root / "extensionless-pdf"
    pdf_like.write_bytes(b"%PDF-1.7\n%fixture")
    pdf_route = select_conversion_route(
        "",
        {"conversion_strategy": "pdf_text_layer"},
        file_identity=file_identity_for_path(pdf_like),
    )
    assert pdf_route.kind == ConversionRouteKind.PDF_TEXT_LAYER

    binary = root / "extensionless-binary"
    binary.write_bytes(b"\x00\x01\x02\x03")
    binary_route = select_conversion_route("", {}, file_identity=file_identity_for_path(binary))
    assert binary_route.kind == ConversionRouteKind.UNSUPPORTED
    assert binary_route.error_code == "E_UNSUPPORTED_TYPE"
    return {
        "name": "content_sniffing_pdf_and_unknown_binary",
        "ok": True,
        "pdf_route": pdf_route.kind.value,
        "binary_route": binary_route.kind.value,
    }


def check_pdf_text_layer_fallback_record(root: Path) -> dict:
    sys.path.insert(0, PYTHONPATH)
    from kbprep_worker.converter_registry import ConversionRoute, ConversionRouteKind
    from kbprep_worker.stages import pipeline_core

    run_dir = root / "pdf-fallback"
    run_dir.mkdir()
    source = run_dir / "bad.pdf"
    source.write_bytes(b"%PDF-")
    converted = run_dir / "converted.md"
    converted.write_text("���" * 80, encoding="utf-8")
    ocr_md = run_dir / "ocr.md"
    ocr_md.write_text("OCR 正文", encoding="utf-8")

    def fake_mineru(*_args, **_kwargs):
        converted.write_text("OCR 正文", encoding="utf-8")
        return {"source_md_path": str(ocr_md), "warnings": []}

    with patch("kbprep_worker.stages.pipeline_core._run_mineru_conversion", side_effect=fake_mineru):
        fallback = pipeline_core._maybe_fallback_pdf_text_layer_to_mineru(
            input_p=source,
            converted_path=converted,
            run_dir=run_dir,
            language="zh",
            text_layer_artifacts={},
        )
    assert fallback is not None
    route = ConversionRoute(
        kind=ConversionRouteKind.PDF_TEXT_LAYER,
        converter="pdf_text_layer",
        conversion_strategy="pdf_text_layer",
        matched_converter="pdf_text_layer",
        match_evidence=("extension:.pdf", "pdf_header"),
    )
    pipeline_core._write_conversion_report(
        run_dir=run_dir,
        input_path=source,
        output_path=converted,
        converter="mineru_after_pdf_text_layer_fallback",
        route=route,
        source_type="pdf",
        mineru_artifacts=fallback,
        runtime={},
        diagnosis={"conversion_strategy": "pdf_text_layer"},
        warnings=fallback.get("warnings", []),
    )
    report = json.loads((run_dir / "conversion_report.json").read_text(encoding="utf-8"))
    decision = report["route_decision"]
    assert decision["fallback_applied"] is True
    assert decision["fallback_from"] == "pdf_text_layer"
    assert decision["fallback_to"] == "mineru_ocr"
    assert Path(fallback["rejected_text_layer_md"]).exists()
    return {"name": "pdf_text_layer_fallback_record", "ok": True, "route_decision": decision}


def check_missing_local_image_is_explicit(root: Path) -> dict:
    source = root / "missing-image.md"
    source.write_text("# 图片测试\n\n步骤1：查看证据。\n\n![缺失](images/missing.png)\n", encoding="utf-8")
    code, envelope, _stderr = run_worker(
        "prepare",
        {"input_path": str(source), "output_root": str(root / "out-missing-image"), "force": True},
    )
    assert code != 0 and envelope.get("ok") is False
    details = envelope["error"].get("details", {})
    text = json.dumps(details, ensure_ascii=False)
    assert "E_IMAGE_FILE_MISSING" in envelope["error"]["code"] or "E_IMAGE_FILE_MISSING" in text
    return {"name": "missing_local_image_explicit", "ok": True, "code": envelope["error"]["code"]}


def check_html_conversion_preserves_knowledge_content(root: Path) -> dict:
    source_dir = root / "html"
    source_dir.mkdir()
    (source_dir / "img.png").write_bytes(b"png")
    html = source_dir / "page.html"
    html.write_text(
        """<!doctype html>
<html><head><title>HTML课程</title><script>bad()</script></head>
<body><main>
<h1>HTML标题</h1>
<p>正文 <a href="https://example.com">链接</a></p>
<table><tr><th>字段</th><th>值</th></tr><tr><td>参数</td><td>1</td></tr></table>
<img src="img.png" alt="图像">
</main></body></html>
""",
        encoding="utf-8",
    )
    code, envelope, stderr = run_worker(
        "prepare",
        {"input_path": str(html), "output_root": str(root / "out-html"), "force": True, "profile": "standard"},
    )
    assert code == 0 and envelope.get("ok") is True, stderr
    converted = Path(envelope["data"]["run_dir"]) / "converted.md"
    text = converted.read_text(encoding="utf-8")
    assert "HTML标题" in text
    assert "[链接](https://example.com)" in text
    assert "字段" in text and "参数" in text
    assert "![图像]" in text
    assert "bad()" not in text
    return {"name": "html_preserves_content_and_removes_script", "ok": True, "converted_md": str(converted)}


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        raise
