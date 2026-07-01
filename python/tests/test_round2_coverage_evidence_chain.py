import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from kbprep_worker import audit, normalize, pdf_text
from kbprep_worker.diagnose import runtime as diagnose_runtime
from kbprep_worker.envelope import EnvelopeExit
from kbprep_worker.feedback import proposals


def _capture_envelope(fn, payload):
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            fn(payload)
    except EnvelopeExit as exc:
        return exc.code, json.loads(out.getvalue())
    raise AssertionError("expected JSON envelope")


class EvidenceChainRound2CoverageTests(unittest.TestCase):
    class _Page:
        def __init__(self, text: str):
            self._text = text

        def get_text(self, kind: str):
            if kind == "blocks":
                # Mirror PyMuPDF get_text("blocks") shape: (x0, y0, x1, y1, text, block_no, block_type).
                return [(0.0, 0.0, 100.0, 20.0, self._text, 0, 0)]
            return self._text

    class _Doc:
        def __init__(self, pages):
            self.pages = pages
            self.closed = False

        def __iter__(self):
            return iter(self.pages)

        def close(self):
            self.closed = True

    def test_pdf_text_layer_conversion_and_merge_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "text.pdf"
            source.write_bytes(b"%PDF-")
            output = root / "converted.md"
            doc = self._Doc([
                self._Page("这是一个超过二十个字的长段落用于测试\n继续合并\n\n1. 保留步骤"),
                self._Page(""),
                self._Page("第二页正文"),
            ])
            fake_fitz = types.SimpleNamespace(open=lambda path: doc)
            with patch.dict(sys.modules, {"fitz": fake_fitz}):
                result = pdf_text.convert_text_layer_pdf(source, output, root)

            self.assertTrue(doc.closed)
            self.assertIn("<!-- page: 1 -->", output.read_text(encoding="utf-8"))
            self.assertTrue(Path(result["content_list_path"]).exists())
            self.assertFalse(pdf_text._should_merge_hard_wrap("短句", "短行"))
            self.assertTrue(pdf_text._should_merge_hard_wrap(
                "This English paragraph is long enough to be a hard wrapped line",
                "that continues on the next extracted PDF line",
            ))
            self.assertEqual(pdf_text._merge_wrapped_lines("abc", "def"), "abc def")

            empty_doc = self._Doc([self._Page("")])
            with patch.dict(sys.modules, {"fitz": types.SimpleNamespace(open=lambda path: empty_doc)}):
                with self.assertRaises(RuntimeError):
                    pdf_text.convert_text_layer_pdf(source, root / "empty.md", root)
            with patch.dict(sys.modules, {"fitz": None}):
                with self.assertRaises(RuntimeError):
                    pdf_text.convert_text_layer_pdf(source, root / "missing.md", root)

    def test_pdf_text_layer_emits_native_bbox_evidence(self):
        # get_text("blocks") returns block-level (bbox, text) tuples; the route
        # normalizes each block's text and feeds it through attach_pdf_native_source_spans
        # so the same pdf_bbox channel MinerU uses also covers trusted text layers.
        # Blocks whose text cannot be located in the converted Markdown are skipped
        # rather than fabricating coordinates.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "text.pdf"
            source.write_bytes(b"%PDF-")
            output = root / "converted.md"
            doc = self._Doc([self._Page("PDF paragraph one\nsecond line\n\n1. item")])
            fake_fitz = types.SimpleNamespace(open=lambda path: doc)
            with patch.dict(sys.modules, {"fitz": fake_fitz}):
                result = pdf_text.convert_text_layer_pdf(source, output, root)
        self.assertIn("native_source_spans", result)
        spans = result["native_source_spans"]
        self.assertIsInstance(spans, list)
        # The mock block text is the full normalized page text; extract finds it
        # at the start of the converted Markdown and emits one pdf_bbox span.
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["precision"], "pdf_bbox")

    def test_normalize_reports_tables_code_images_and_ocr_fixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_rules = ([(__import__("re").compile("Al工具"), "AI工具", "ai_context_fix", 0.9, "W_OCR_AI_CONFUSION")], [])
            text = "\n".join([
                "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>",
                "Al工具",
                "```python",
                "print(1)",
                "![图](images\\a.png)",
            ])
            with patch("kbprep_worker.normalize.load_ocr_normalization_rules", return_value=fake_rules):
                result = normalize.normalize(text, str(root), {})
            normalized = result["normalized_text"]
            self.assertIn("| A | B |", normalized)
            self.assertIn("AI工具", normalized)
            self.assertTrue(normalized.rstrip().endswith("```"))
            self.assertIn("images/a.png", normalized)
            self.assertTrue((root / "normalization_report.json").exists())
            self.assertTrue((root / "ocr_fixes.jsonl").exists())
            self.assertTrue((root / "table_fixes.jsonl").exists())
            self.assertIsNone(normalize._html_table_to_markdown("<table></table>"))
            with self.assertRaises(ValueError):
                normalize._compile_ocr_rules([{"pattern": "(", "replacement": "", "rule": "bad", "confidence": 1}], root / "rules.json")
            with self.assertRaises(ValueError):
                normalize._compile_ocr_rules("bad", root / "rules.json")

    def test_diagnose_runtime_success_failure_and_command_envelopes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            md = root / "source.md"
            md.write_text("# 标题\n正文", encoding="utf-8")
            result, warnings = diagnose_runtime.diagnose_file({"input_path": str(md), "output_root": str(root), "source_type": "manual"})
            self.assertEqual(result["source_type"], "manual")
            self.assertEqual(warnings, result["warnings"])

            png = root / "image.png"
            png.write_bytes(b"png")
            image_result, _ = diagnose_runtime.diagnose_file({"input_path": str(png)})
            self.assertTrue(image_result["needs_ocr"])
            with self.assertRaises(diagnose_runtime.DiagnoseError) as missing:
                diagnose_runtime.diagnose_file({"input_path": str(root / "missing.weird")})
            self.assertEqual(missing.exception.code, "E_INPUT_NOT_FOUND")
            unknown = root / "unknown.zzz"
            unknown.write_text("x", encoding="utf-8")
            with self.assertRaises(diagnose_runtime.DiagnoseError) as unsupported:
                diagnose_runtime.diagnose_file({"input_path": str(unknown)})
            self.assertEqual(unsupported.exception.code, "E_UNSUPPORTED_TYPE")

            code, envelope = _capture_envelope(diagnose_runtime.run, {"input_path": str(md)})
            self.assertEqual(code, 0)
            self.assertTrue(envelope["ok"])
            code, envelope = _capture_envelope(diagnose_runtime.run, {"input_path": str(root / "none.md")})
            self.assertEqual(code, 1)
            self.assertEqual(envelope["error"]["code"], "E_INPUT_NOT_FOUND")

    def test_audit_report_lists_deleted_evidence_risk_review_and_errors(self):
        context = audit.AuditContext(
            input_name="source.pdf",
            file_hash="hash",
            plugin_version="v",
            mineru_version="m",
            python_version="3",
            runtime={
                "python_executable": "py",
                "mineru_path": "mineru",
                "torch": "2",
                "torch_cuda_available": False,
                "torch_cuda_version": "none",
                "mineru_device": "cpu",
            },
            diagnosis={
                "detected_format": "pdf",
                "text_layer_health": "degraded",
                "text_quality": {"garbled_ratio": 0.2},
                "needs_ocr": True,
            },
            blocks=[
                {"block_id": "d", "status": "discard", "type": "cta", "reason": "ad"},
                {"block_id": "e", "status": "evidence", "type": "revenue_claim"},
                {"block_id": "k", "status": "keep", "risk_tags": ["risk"], "reason": "check"},
                {"block_id": "r", "status": "review", "type": "paragraph", "reason": "ambiguous"},
            ],
            quality_report={},
            warnings=["warn"],
            strict_errors=["E_TEST"],
        )
        md = audit.generate_audit_md(context)
        self.assertIn("## Deleted Content", md)
        self.assertIn("## Evidence", md)
        self.assertIn("## High-Risk Kept Content", md)
        self.assertIn("## Strict Errors", md)

    def test_feedback_accept_reject_and_narrowing_paths(self):
        base = {
            "schema": "kbprep.rule_proposal.v1",
            "id": "p1",
            "status": "proposed",
            "action": "discard",
            "scope": "user",
            "document_type": "course",
            "match": "literal",
            "pattern": "扫码",
            "examples": ["扫码关注", "扫码入群"],
            "counterexamples": ["案例：扫码动作是参数说明"],
            "reason": "test",
            "risk_note": "Fixture proposal may be too broad without review.",
            "created_from_run": "run",
            "artifact_context": {"document_type": "course", "source_name": "source.md"},
            "confidence": "needs_review",
            "owner_confirmation_status": "pending",
            "requires_confirmation": True,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        validation = proposals._validate_proposal_acceptance(base)
        self.assertFalse(validation["ok"])
        narrowed = proposals._suggest_narrowed_proposal(base, validation)
        self.assertIsNone(narrowed)
        scoped = proposals._narrowed_scope_from_artifacts(base)
        self.assertEqual(scoped["scope"], "document_type")
        self.assertEqual(proposals._reason({"reason": "because"}, "fallback"), "because")
        self.assertEqual(proposals._confidence({"confidence": 0.7}), 0.7)
        self.assertEqual(proposals._confidence({"confidence": "manual"}), "manual")
        self.assertEqual(proposals._proposal_string_list([1, " a "]), ["a"])

        with tempfile.TemporaryDirectory() as tmp:
            rules_dir = Path(tmp)
            proposed = rules_dir / "proposed_rules.jsonl"
            proposed.write_text(
                json.dumps({**base, "counterexamples": ["正文案例：渠道字段"]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            code, envelope = _capture_envelope(
                proposals._accept_proposal,
                {"rules_dir": str(rules_dir), "accept_proposal": "latest", "confirm_rule_acceptance": True},
            )
            self.assertEqual(code, 0)
            self.assertTrue((rules_dir / "accepted_rules.jsonl").exists())
            code, envelope = _capture_envelope(
                proposals._accept_proposal,
                {"rules_dir": str(rules_dir), "accept_proposal": "latest"},
            )
            self.assertTrue(envelope["data"]["already_accepted"])

            proposed.write_text(
                json.dumps({**base, "id": "p2", "counterexamples": ["正文案例：渠道字段"]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            code, envelope = _capture_envelope(
                proposals._reject_proposal,
                {"rules_dir": str(rules_dir), "reject_proposal": "latest", "reject_reason": "too broad"},
            )
            self.assertEqual(code, 0)
            self.assertTrue((rules_dir / "rejected_rules.jsonl").exists())
            code, envelope = _capture_envelope(
                proposals._reject_proposal,
                {"rules_dir": str(rules_dir), "reject_proposal": "latest"},
            )
            self.assertTrue(envelope["data"]["already_rejected"])


if __name__ == "__main__":
    unittest.main()
