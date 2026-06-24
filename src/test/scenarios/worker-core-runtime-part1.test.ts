import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { parseEnvelope, runPython } from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - core/runtime part 1", () => {
  it("rejects worker envelopes that are missing the ok discriminator", async () => {
    const result = parseEnvelope(JSON.stringify({ data: { value: 1 } }), []);

    expect(result.ok).toBe(false);
    expect(result.error?.code).toBe("E_WORKER_BAD_JSON");
    expect(result.error?.details?.validation_errors).toBeDefined();
  });

  it("rejects success envelopes that carry a non-array warnings field", async () => {
    const result = parseEnvelope(JSON.stringify({ ok: true, data: {}, warnings: "careful" }), []);

    expect(result.ok).toBe(false);
    expect(result.error?.code).toBe("E_WORKER_BAD_JSON");
    expect(result.error?.details?.validation_errors).toBeDefined();
  });

  it("maps common Chinese language hints to MinerU language codes", () => {
    runPython(
      [
        "from kbprep_worker.mineru_adapter import normalize_mineru_language",
        "assert normalize_mineru_language('zh') == 'ch'",
        "assert normalize_mineru_language('zh-CN') == 'ch'",
        "assert normalize_mineru_language('zh_tw') == 'ch'",
        "assert normalize_mineru_language(None) == 'en'",
        "assert normalize_mineru_language('en') == 'en'",
      ].join("\n"),
      [],
    );
  });

  it("discovers MinerU 3.2 auto output files under the stem directory", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-mineru-discovery-"));
    try {
      runPython(
        [
          "import subprocess, sys",
          "from pathlib import Path",
          "from kbprep_worker import mineru_adapter",
          "root = Path(sys.argv[1])",
          "input_path = root / 'sample.pdf'",
          "input_path.write_bytes(b'%PDF-1.4\\n')",
          "class Proc:",
          "    returncode = 0",
          "    stdout = ''",
          "    stderr = ''",
          "def fake_run(cmd, **kwargs):",
          "    out = Path(cmd[cmd.index('-o') + 1])",
          "    auto = out / input_path.stem / 'auto'",
          "    auto.mkdir(parents=True)",
          "    (auto / f'{input_path.stem}.md').write_text('# OCR\\n', encoding='utf-8')",
          "    (auto / f'{input_path.stem}_content_list.json').write_text('[]', encoding='utf-8')",
          "    (auto / f'{input_path.stem}_content_list_v2.json').write_text('[]', encoding='utf-8')",
          "    (auto / f'{input_path.stem}_middle.json').write_text('{}', encoding='utf-8')",
          "    return Proc()",
          "mineru_adapter.find_mineru = lambda: 'mineru'",
          "subprocess.run = fake_run",
          "result = mineru_adapter.run_mineru(str(input_path), str(root / 'run'), language='zh', mode='auto')",
          "assert result['source_md_path'].endswith('source.md'), result",
          "assert result['content_list_path'].endswith('_content_list.json'), result",
          "assert result['content_list_v2_path'].endswith('_content_list_v2.json'), result",
          "assert result['middle_json_path'].endswith('_middle.json'), result",
          "assert result['warnings'] == [], result",
        ].join("\n"),
        [root],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("does not count common Markdown punctuation as garbled PDF text", () => {
    runPython(
      [
        "from kbprep_worker.diagnose import analyze_text_quality",
        "text = '第一步：打开 A—B 设置页，填写 threshold=0.8，并记录 [retry_count]。'",
        "quality = analyze_text_quality(text)",
        "assert quality['non_common_unicode_ratio'] == 0.0, quality",
        "assert quality['garbled_ratio'] == 0.0, quality",
      ].join("\n"),
      [],
    );
  });

  it("detects readable QR and CTA pollution text during diagnosis", () => {
    runPython(
      [
        "from kbprep_worker.diagnose import analyze_text_quality",
        "quality = analyze_text_quality('扫码进群，长按识别二维码，添加老师免费领取体验卡。')",
        "assert quality['has_qr_text'] is True, quality",
        "assert quality['has_cta_text'] is True, quality",
        "assert any(source.replace('\\\\', '/').endswith('rules/base/obvious_noise.json') for source in quality['cleaning_rule_sources']), quality",
      ].join("\n"),
      [],
    );
  });

  it("uses cleaning dictionaries for diagnosis pollution signals", () => {
    runPython(
      [
        "from kbprep_worker.diagnose import analyze_text_quality",
        "standard = analyze_text_quality('欢迎关注公众号「ExampleAuthor」反馈交流。')",
        "templated = analyze_text_quality('欢迎关注公众号「ExampleAuthor」反馈交流。', rule_templates=['self_media_course'])",
        "assert standard['has_cta_text'] is False, standard",
        "assert templated['has_cta_text'] is True, templated",
        "assert any(source.replace('\\\\', '/').endswith('.kbprep/rules/templates/self_media_course.json') for source in templated['cleaning_rule_sources']), templated",
      ].join("\n"),
      [],
    );
  });

  it("detects Chinese mojibake from broken PDF text layers", () => {
    runPython(
      [
        "from kbprep_worker.diagnose import analyze_text_quality",
        "text = '鐩綍\\nExampleTool 鏄粈涔?\\n閮ㄧ讲鏂规\\nSkills 绯荤粺'",
        "quality = analyze_text_quality(text * 20)",
        "normal = analyze_text_quality('今天讲一下教程步骤、参数和失败经验。' * 20)",
        "assert normal['mojibake_ratio'] == 0.0, normal",
        "assert quality['mojibake_ratio'] > 0.08, quality",
        "assert quality['unreadable_text_ratio'] > 0.08, quality",
      ].join("\n"),
      [],
    );
  });

  it("detects common UTF-8-as-GBK PDF text-layer mojibake", () => {
    runPython(
      [
        "from kbprep_worker.diagnose import analyze_text_quality",
        "broken_pdf_text = 'ExampleTool姗欑毊涔︿粠鍏ラ棬鍒扮簿閫氾紝娑电洊鏋舵瀯鍘熺悊銆侀儴缃叉柟妗堛€佹笭閬撴帴鍏ャ€丼kills绯荤粺'",
        "quality = analyze_text_quality(broken_pdf_text * 10)",
        "normal = analyze_text_quality('今天讲一个教程步骤、参数和失败经验。ExampleTool 可以接入多种渠道。' * 20)",
        "assert normal['mojibake_ratio'] == 0.0, normal",
        "assert quality['mojibake_ratio'] > 0.08, quality",
        "assert quality['unreadable_text_ratio'] > 0.08, quality",
      ].join("\n"),
      [],
    );
  });

  it("installs pinned CUDA torch into the selected plugin Python and re-probes in a fresh process", () => {
    runPython(
      [
        "import json",
        "from kbprep_worker import setup_env",
        "calls = []",
        "state = {'cuda_installed': False}",
        "class Proc:",
        "    def __init__(self, returncode=0, stdout='', stderr=''):",
        "        self.returncode = returncode",
        "        self.stdout = stdout",
        "        self.stderr = stderr",
        "def fake_which(name):",
        "    return 'C:/Windows/System32/nvidia-smi.exe' if name == 'nvidia-smi' else None",
        "def fake_run(cmd, **kwargs):",
        "    calls.append(cmd)",
        "    if cmd[:3] == ['venv-python', '-m', 'pip']:",
        "        state['cuda_installed'] = True",
        "        return Proc()",
        "    if cmd[:2] == ['venv-python', '-c']:",
        "        payload = {'installed': True, 'version': '2.8.0+cpu', 'cuda_available': False, 'cuda_version': 'none', 'device_count': 0, 'device': 'cpu'}",
        "        if state['cuda_installed']:",
        "            payload = {'installed': True, 'version': '2.8.0+cu126', 'cuda_available': True, 'cuda_version': '12.6', 'device_count': 1, 'device': 'cuda', 'device_name': 'RTX Test', 'vram_gb': 16.0}",
        "        return Proc(stdout=json.dumps(payload))",
        "    raise AssertionError(cmd)",
        "setup_env.shutil.which = fake_which",
        "setup_env.subprocess.run = fake_run",
        "result = setup_env.setup_gpu('venv-python')",
        "pip_calls = [cmd for cmd in calls if cmd[:3] == ['venv-python', '-m', 'pip']]",
        "assert len(pip_calls) == 1, calls",
        "assert 'torch==2.8.0' in pip_calls[0], pip_calls",
        "assert 'torchvision==0.23.0' in pip_calls[0], pip_calls",
        "assert '--force-reinstall' in pip_calls[0], pip_calls",
        "assert 'https://download.pytorch.org/whl/cu126' in pip_calls[0], pip_calls",
        "assert calls[-2][2] == setup_env._torch_probe_code(), calls",
        "assert result['torch_cuda'] is True, result",
        "assert result['device'] == 'cuda', result",
        "assert result['gpu']['device_name'] == 'RTX Test', result",
      ].join("\n"),
      [],
    );
  });

  it("does not install CUDA torch when plugin config forces CPU mode", () => {
    runPython(
      [
        "import json",
        "from kbprep_worker import setup_env",
        "calls = []",
        "class Proc:",
        "    def __init__(self, returncode=0, stdout='', stderr=''):",
        "        self.returncode = returncode",
        "        self.stdout = stdout",
        "        self.stderr = stderr",
        "def fake_which(name):",
        "    return 'C:/Windows/System32/nvidia-smi.exe' if name == 'nvidia-smi' else None",
        "def fake_run(cmd, **kwargs):",
        "    calls.append(cmd)",
        "    if cmd[:2] == ['venv-python', '-c']:",
        "        payload = {'installed': True, 'version': '2.8.0+cpu', 'cuda_available': False, 'cuda_version': 'none', 'device_count': 0, 'device': 'cpu'}",
        "        return Proc(stdout=json.dumps(payload))",
        "    raise AssertionError(cmd)",
        "setup_env.shutil.which = fake_which",
        "setup_env.subprocess.run = fake_run",
        "result = setup_env.setup_gpu('venv-python', device_override='cpu')",
        "assert not [cmd for cmd in calls if cmd[:3] == ['venv-python', '-m', 'pip']], calls",
        "assert result['actions_taken'] == ['cuda_install_skipped_device_override_cpu'], result",
        "assert result['device_override'] == 'cpu', result",
      ].join("\n"),
      [],
    );
  });

  it("prefers MinerU installed beside the selected Python executable", () => {
    runPython(
      [
        "from pathlib import Path",
        "import sys, tempfile",
        "from kbprep_worker.mineru_adapter import find_mineru",
        "root = Path(tempfile.mkdtemp())",
        "scripts = root / 'Scripts'",
        "scripts.mkdir()",
        "(scripts / 'python.exe').write_text('', encoding='utf-8')",
        "(scripts / 'mineru.exe').write_text('', encoding='utf-8')",
        "old = sys.executable",
        "try:",
        "    sys.executable = str(scripts / 'python.exe')",
        "    assert find_mineru() == str(scripts / 'mineru.exe')",
        "finally:",
        "    sys.executable = old",
      ].join("\n"),
      [],
    );
  });

  it("does not fall back to a system MinerU outside the selected Python environment", () => {
    runPython(
      [
        "from pathlib import Path",
        "import os, sys, tempfile",
        "from kbprep_worker.mineru_adapter import find_mineru",
        "root = Path(tempfile.mkdtemp())",
        "scripts = root / 'Scripts'",
        "external = root / 'external'",
        "scripts.mkdir()",
        "external.mkdir()",
        "(scripts / 'python.exe').write_text('', encoding='utf-8')",
        "(external / 'mineru.exe').write_text('', encoding='utf-8')",
        "old_executable = sys.executable",
        "old_path = os.environ.get('PATH', '')",
        "try:",
        "    sys.executable = str(scripts / 'python.exe')",
        "    os.environ['PATH'] = str(external)",
        "    try:",
        "        find_mineru()",
        "    except FileNotFoundError as exc:",
        "        assert str(scripts) in str(exc)",
        "    else:",
        "        raise AssertionError('find_mineru unexpectedly used PATH outside selected venv')",
        "finally:",
        "    sys.executable = old_executable",
        "    os.environ['PATH'] = old_path",
      ].join("\n"),
      [],
    );
  });

  it("maps MinerU content_list pages to block and chunk page ranges by line position", () => {
    runPython(
      [
        "import json, tempfile",
        "from pathlib import Path",
        "from kbprep_worker.blockify import blockify",
        "from kbprep_worker.split import split_into_chunks",
        "run_dir = Path(tempfile.mkdtemp(prefix='kbprep-page-map-'))",
        "content_list = run_dir / 'content_list.json'",
        "text = '\\n'.join([",
        "  '# Page One',",
        "  '',",
        "  'First page keeps setup detail and threshold=0.7.',",
        "  '',",
        "  '# Page Two',",
        "  '',",
        "  'Second page keeps retry_count=3 and failure_reason=timeout.',",
        "])",
        "content_list.write_text(json.dumps([",
        "  {'page_idx': 0, 'text': '# Page One\\n\\nFirst page keeps setup detail'},",
        "  {'page_idx': 1, 'text': '# Page Two\\n\\nSecond page keeps retry_count'},",
        "]), encoding='utf-8')",
        "blocks = blockify(text, 'abcdef1234567890', {'content_list_path': str(content_list)}, str(run_dir))",
        "first = next(b for b in blocks if 'First page' in b['text'])",
        "second = next(b for b in blocks if 'Second page' in b['text'])",
        "assert first['page_start'] == 0 and first['page_end'] == 0, first",
        "assert second['page_start'] == 1 and second['page_end'] == 1, second",
        "for block in blocks: block['status'] = 'keep'",
        "split_into_chunks(blocks, str(run_dir), 'pdf_like', 'abcdef1234567890', 'run123')",
        "chunk_text = (run_dir / 'chunks' / 'chunk_0001.md').read_text(encoding='utf-8')",
        "assert 'page_range: \"0-1\"' in chunk_text, chunk_text.split('\\n')[:8]",
      ].join("\n"),
      [],
    );
  });

  it("uses slide/page order split strategy only when diagnosis requests it", () => {
    runPython(
      [
        "import json, tempfile",
        "from pathlib import Path",
        "from kbprep_worker.split import split_into_chunks",
        "def blocks():",
        "    return [",
        "      {'block_id': 'p1h', 'status': 'keep', 'type': 'section_heading', 'text': '# Slide 1', 'heading_path': ['Slide 1'], 'page_start': 0, 'page_end': 0},",
        "      {'block_id': 'p1b', 'status': 'keep', 'type': 'paragraph', 'text': 'Slide 1 keeps threshold=0.8 and setup details.', 'heading_path': ['Slide 1'], 'page_start': 0, 'page_end': 0},",
        "      {'block_id': 'p2h', 'status': 'keep', 'type': 'section_heading', 'text': '# Slide 2', 'heading_path': ['Slide 2'], 'page_start': 1, 'page_end': 1},",
        "      {'block_id': 'p2b', 'status': 'keep', 'type': 'paragraph', 'text': 'Slide 2 keeps retry_count=3 and failure_reason=timeout.', 'heading_path': ['Slide 2'], 'page_start': 1, 'page_end': 1},",
        "    ]",
        "default_dir = Path(tempfile.mkdtemp(prefix='kbprep-default-split-'))",
        "slide_dir = Path(tempfile.mkdtemp(prefix='kbprep-slide-split-'))",
        "split_into_chunks(blocks(), str(default_dir), 'pdf_like', 'abcdef1234567890', 'run-default')",
        "split_into_chunks(blocks(), str(slide_dir), 'pdf_like', 'abcdef1234567890', 'run-slide', split_strategy='preserve_slide_or_page_order')",
        "default_manifest = [json.loads(line) for line in (default_dir / 'chunk_manifest.jsonl').read_text(encoding='utf-8').splitlines()]",
        "slide_manifest = [json.loads(line) for line in (slide_dir / 'chunk_manifest.jsonl').read_text(encoding='utf-8').splitlines()]",
        "assert len(default_manifest) == 1, default_manifest",
        "assert [m['page_start'] for m in slide_manifest] == [0, 1], slide_manifest",
        "assert [m['page_end'] for m in slide_manifest] == [0, 1], slide_manifest",
        "assert all(m['split_strategy'] == 'preserve_slide_or_page_order' for m in slide_manifest), slide_manifest",
        "chunk_text = (slide_dir / 'chunks' / 'chunk_0001.md').read_text(encoding='utf-8')",
        "assert 'split_strategy: preserve_slide_or_page_order' in chunk_text",
      ].join("\n"),
      [],
    );
  });
});
