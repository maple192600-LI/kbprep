import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, it } from "vitest";
import { makeImageOnlyPdf, runPython } from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - PDF routing", () => {
  it("routes image-only scanned PDFs through MinerU OCR and records the actual route", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-scanned-pdf-route-"));
    try {
      const inputPath = path.join(root, "scan.pdf");
      const imagePath = path.join(root, "scan.png");
      const outputRoot = path.join(root, "output");
      makeImageOnlyPdf(inputPath, imagePath);

      runPython(
        [
          "import io, json, sys",
          "from pathlib import Path",
          "from kbprep_worker import mineru_adapter, prepare",
          "input_path = Path(sys.argv[1])",
          "output_root = Path(sys.argv[2])",
          "calls = []",
          "def fake_mineru(**kwargs):",
          "    calls.append(kwargs.get('mode'))",
          "    out = Path(kwargs['output_dir']) / 'mineru_scanned.md'",
          "    out.write_text('# OCR Scan Result\\n\\nStep 1: keep threshold=0.8 from the scanned page.\\n\\nRecord retry_count=3.\\n', encoding='utf-8')",
          "    return {",
          "        'source_md_path': str(out),",
          "        'content_list_path': None,",
          "        'content_list_v2_path': None,",
          "        'middle_json_path': None,",
          "        'assets_dir': None,",
          "        'converter': 'mineru',",
          "        'warnings': ['fake scanned pdf OCR'],",
          "    }",
          "mineru_adapter.run_mineru = fake_mineru",
          "stdout = io.StringIO()",
          "old_stdout = sys.stdout",
          "try:",
          "    sys.stdout = stdout",
          "    try:",
          "        prepare.run({",
          "            'input_path': str(input_path),",
          "            'output_root': str(output_root),",
          "            'profile': 'standard',",
          "            'mode': 'rules_only',",
          "            'language': 'zh',",
          "            'source_type': 'auto',",
          "            'splitter': 'auto',",
          "            'force': True,",
          "        })",
          "    except SystemExit:",
          "        pass",
          "finally:",
          "    sys.stdout = old_stdout",
          "payload = json.loads(stdout.getvalue())",
          "assert payload['ok'] is True, payload",
          "assert calls == ['ocr'], calls",
          "cleaned = Path(payload['data']['latest_outputs']['cleaned_md']).read_text(encoding='utf-8')",
          "diagnosis = json.loads(Path(payload['data']['latest_outputs']['diagnosis_report']).read_text(encoding='utf-8'))",
          "report = json.loads(Path(payload['data']['latest_outputs']['conversion_report']).read_text(encoding='utf-8'))",
          "assert diagnosis['pdf_subtype'] == 'image_only_or_scanned', diagnosis",
          "assert diagnosis['text_layer_health'] == 'no_text_layer', diagnosis",
          "assert diagnosis['conversion_strategy'] == 'mineru_ocr', diagnosis",
          "assert 'threshold=0.8' in cleaned, cleaned",
          "assert report['converter'] == 'mineru', report",
          "decision = report['route_decision']",
          "assert decision['declared_route'] == 'pdf_diagnosis_selected', decision",
          "assert decision['diagnosed_strategy'] == 'mineru_ocr', decision",
          "assert decision['actual_converter'] == 'mineru', decision",
          "assert decision['actual_route'] == 'mineru_ocr', decision",
          "assert decision['fallback_applied'] is False, decision",
          "assert decision['selected_pdf_tier'] == 'tier_3', decision",
          "assert decision['pdf_route_diagnostics_schema'] == 'kbprep.pdf_route_diagnostics.v1', decision",
          "assert 'Tier 3' in decision['pdf_route_reason'], decision",
          "assert report['mineru_artifacts']['mineru_mode'] == 'ocr', report",
          "assert report['pdf_route_diagnostics']['recommended_tier'] == 'tier_3', report",
          "assert report['pdf_route_diagnostics']['recommended_route'] == 'mineru_ocr', report",
        ].join("\n"),
        [inputPath, outputRoot],
        true,
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 10_000);

  it("copies MinerU image assets next to converted Markdown", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-mineru-assets-"));
    try {
      runPython(
        [
          "from pathlib import Path",
          "from kbprep_worker import mineru_adapter, prepare",
          "run_dir = Path(__import__('sys').argv[1])",
          "input_path = run_dir / 'sample.pdf'",
          "input_path.write_bytes(b'%PDF-1.4\\n')",
          "def fake_mineru(**kwargs):",
          "    raw = Path(kwargs['output_dir']) / 'mineru_raw' / 'sample' / 'auto'",
          "    images = raw / 'images'",
          "    images.mkdir(parents=True)",
          "    (images / 'kept.jpg').write_bytes(b'jpg')",
          "    source = raw / 'source.md'",
          "    source.write_text('![](images/kept.jpg)\\n', encoding='utf-8')",
          "    return {'source_md_path': str(source), 'converter': 'mineru', 'warnings': []}",
          "mineru_adapter.run_mineru = fake_mineru",
          "converted = run_dir / 'converted.md'",
          "prepare._run_mineru_conversion(input_path, converted, run_dir, 'zh', 'auto')",
          "assert converted.read_text(encoding='utf-8') == '![](images/kept.jpg)\\n'",
          "assert (run_dir / 'images' / 'kept.jpg').read_bytes() == b'jpg'",
        ].join("\n"),
        [root],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("classifies Chinese QR images, proof screenshots, and tutorial screenshots", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-image-classify-"));
    try {
      runPython(
        [
          "from pathlib import Path",
          "from kbprep_worker import images",
          "run_dir = Path(__import__('sys').argv[1])",
          "(run_dir / 'converted.md').write_text('placeholder', encoding='utf-8')",
          "blocks = [",
          "    {",
          "        'block_id': 'qr',",
          "        'type': 'unknown_review',",
          "        'text': '扫码加入社群，免费领取体验卡。\\n![](images/qr.png)',",
          "        'images': [{'src': 'images/qr.png'}],",
          "        'heading_path': [],",
          "        'status': 'unclassified',",
          "    },",
          "    {",
          "        'block_id': 'proof',",
          "        'type': 'unknown_review',",
          "        'text': '这是案例收入数据截图，用来说明变现结果。\\n![](images/proof.png)',",
          "        'images': [{'src': 'images/proof.png'}],",
          "        'heading_path': [],",
          "        'status': 'unclassified',",
          "    },",
          "    {",
          "        'block_id': 'step',",
          "        'type': 'unknown_review',",
          "        'text': '步骤 1：打开后台设置页面，点击保存。\\n![](images/step.png)',",
          "        'images': [{'src': 'images/step.png'}],",
          "        'heading_path': ['实操教程'],",
          "        'status': 'unclassified',",
          "    },",
          "]",
          "classified = {block['block_id']: block for block in images.classify_images(blocks, str(run_dir))}",
          "assert classified['qr']['image_type'] == 'qr_image', classified",
          "assert classified['qr']['status'] == 'discard', classified",
          "assert classified['proof']['image_type'] == 'proof_screenshot', classified",
          "assert classified['proof']['status'] == 'evidence', classified",
          "assert classified['step']['image_type'] == 'operation_screenshot', classified",
          "assert classified['step']['status'] == 'keep', classified",
        ].join("\n"),
        [root],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("loads platform image cleanup only through the optional self-media template", () => {
    runPython(
      [
        "from pathlib import Path",
        "from tempfile import TemporaryDirectory",
        "from kbprep_worker import images",
        "with TemporaryDirectory() as tmp:",
        "    run_dir = Path(tmp)",
        "    (run_dir / 'converted.md').write_text('欢迎关注公众号「ExampleAuthor」反馈交流。\\n![](images/follow.png)', encoding='utf-8')",
        "    block = {",
        "        'block_id': 'follow-image',",
        "        'type': 'image_evidence',",
        "        'status': 'review',",
        "        'text': '欢迎关注公众号「ExampleAuthor」反馈交流。\\n![](images/follow.png)',",
        "        'images': [{'src': 'images/follow.png'}],",
        "        'heading_path': [],",
        "    }",
        "    generic = images.classify_images([dict(block)], str(run_dir))[0]",
        "    templated = images.classify_images([dict(block)], str(run_dir), rule_templates=['self_media_course'])[0]",
        "    assert generic['image_type'] != 'qr_image', generic",
        "    assert generic['status'] == 'review', generic",
        "    assert templated['image_type'] == 'qr_image', templated",
        "    assert templated['status'] == 'discard', templated",
      ].join("\n"),
      [],
    );
  });
});
