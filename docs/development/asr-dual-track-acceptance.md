# ASR 双链路 Manual Acceptance（Phase B）

> 定位：**manual acceptance evidence**（人工验收），不是 version-controlled verified golden fixture——两者是不同证据层，本文件记录前者。能力状态 `media_local_transcript` 现已 `verified`：本 manual acceptance（双链路 GPU 跑通）+ F1 version-controlled fixture（transcript 入库 + sha256 hash 锁定，见下文）+ 第二 agent 复核 + owner 批准（AGENTS.md + subagent-worktree-discipline §4）共同支撑。

## 架构（双链路，共用 GPU venv）

| 链路 | 引擎 | 模型 | 触发 | 配置 |
|---|---|---|---|---|
| 中文 | Qwen3-ASR（transformers 后端，Python import） | `Qwen/Qwen3-ASR-1.7B` | `KBPREP_ASR_LANGUAGE=zh`（默认） | `device_map="cuda:0"` + `dtype=bfloat16` + `max_new_tokens=8192` |
| 英文 | Whisper（openai-whisper CLI） | `large-v3` | `KBPREP_ASR_LANGUAGE=en` | whisper CLI `--model large-v3`（自动 CUDA） |

- **路由**：`transcribe_media` 按 `KBPREP_ASR_LANGUAGE` 分发（`converters/asr.py`）。subtitle-first 不变（YouTube 有字幕先字幕，本路由只管无字幕 media fallback）。
- **两层 venv（关键口径，manual acceptance 必须认对环境）**：项目有两层 venv，本验收在**完整 GPU venv** 跑，不是 dev venv：
  - **dev venv**（`node scripts/python-venv.mjs` / `npm run python:test` 自动建）：轻量（editable-no-deps + PyMuPDF/yt-dlp/mypy/ruff），**无 torch/GPU**，跑 538 mock 测试——`asr.py` 懒加载 torch，无 GPU 也能跑 mock 测试，但跑不了真实推理。在 dev venv 里 `import torch` 会 `ModuleNotFoundError`，这是设计如此（不是 torch 被破坏）。
  - **完整 GPU venv**（手动 `pip install -e '.[cuda,asr]'`）：`torch==2.8.0+cu126` + CUDA True + `qwen_asr` + `whisper` + mineru + lmdeploy。双链路 ASR 装进这个 venv 的 `.[asr]` extra，复用 cuda extra 的 cu126 torch——dry-run + 实测验证装 qwen-asr/openai-whisper **不动 cu126 torch**（`torch.cuda.is_available()==True`，不重蹈 e18cf9a torch 被降级 CPU）。
- **配置出处**：参考 MediaCrawler `postcrawl/processors/transcript.py` 已验证的 Qwen3-ASR GPU 配置（device cuda:0 / bfloat16 / 长 max_new_tokens / Chinese）。

## Manual Acceptance 结果（2026-06-26，4060 Ti 16GB，完整 GPU venv）

| 样本 | 语言 | 链路 | 耗时 | 结果 |
|---|---|---|---|---|
| YouTube `_L2Filt7l-s`（中文，前 90s） | zh | Qwen3-ASR 1.7B | 27s | 转录完整准确（CodeX/AIGC/个人IP 等术语准） |
| YouTube `FBHhmqBs894`（英文，前 90s） | en | Whisper large-v3 | 438s（含首次下 3GB 模型；后续缓存秒级） | 转录准确（copywriting/philosophy 等） |

验证项（均在**完整 GPU venv** 跑；dev venv 无 torch，跑不了这些）：
- `torch.cuda.is_available()==True`，版本 `2.8.0+cu126`（装 qwen-asr/openai-whisper 前后一致）。
- `import lmdeploy` / `import mineru` 正常（accelerate 1.14→1.12 兼容，没坏 mineru）。
- 真实样本（非 TTS 合成），GPU 推理（非 CPU）。

## F1 Reproducible Fixture（2026-07-01，version-controlled）

> 与上方 manual acceptance 不同：这里是**版本控制 fixture**（transcript 文本入库 `python/tests/golden/formats/media/transcript_zh_90s.txt`），由 `test_media_asr_fixture.py` 的 `FIXTURE_SHA256` content-hash 锁定，CI 守静默漂移。fixture 是 evidence snapshot（ASR 输出会随模型版本变化），不作 deterministic re-run target——hash 锁定让"输出会变"成为可检测漂移而非隐藏风险，这是 `media_local_transcript` 升 `verified` 的决定性证据。

| 样本 | 语言 | 链路 | 耗时 | 结果 |
|---|---|---|---|---|
| YouTube `3DlXq9nsQOE`（中文，前 90s） | zh | Qwen3-ASR 1.7B | ~20s（4060 Ti，完整 GPU venv） | 689 字符（zh transcript），harness engineering 主题，transcript 入库为 fixture |

注：`3DlXq9nsQOE` 与上方 manual acceptance 的 `_L2Filt7l-s` 是**不同的真实样本**——前者是 F1 version-controlled fixture，后者是 manual acceptance 证据。两者独立，不混淆。

## 复现命令

样本放在本地 `.kbprep/phase-b-test-media/`（gitignored，不入仓库）。

> **环境分层**：下载样本用 **dev venv**（`node scripts/python-venv.mjs`，跨平台，自带 yt-dlp）；torch 自检 + 转写用**完整 GPU venv**（装了 `.[cuda,asr]` extra 的 venv，有 torch）。`node scripts/python-venv.mjs` 是项目封装的跨平台 venv 入口（自动按平台选 `Scripts/python.exe` / `bin/python`），Windows / macOS / Linux 通用——不写死平台路径。

```bash
# 1. 下载短片段（dev venv 即可，自带 yt-dlp）
#    中文样本 → Qwen3-ASR
node scripts/python-venv.mjs -m yt_dlp --download-sections "*0-90" --force-keyframes-at-cuts \
  -f ba -x --audio-format wav --no-playlist --postprocessor-args "-ar 16000 -ac 1" \
  -o ".kbprep/phase-b-test-media/yt-zh.%(ext)s" "https://www.youtube.com/watch?v=_L2Filt7l-s"

#    英文样本 → Whisper
node scripts/python-venv.mjs -m yt_dlp --download-sections "*0-90" --force-keyframes-at-cuts \
  -f ba -x --audio-format wav --no-playlist --postprocessor-args "-ar 16000 -ac 1" \
  -o ".kbprep/phase-b-test-media/yt-en.%(ext)s" "https://www.youtube.com/watch?v=FBHhmqBs894"

#    F1 version-controlled fixture 样本（3DlXq9nsQOE，transcript 入库 python/tests/golden/formats/media/）
node scripts/python-venv.mjs -m yt_dlp --download-sections "*0-90" --force-keyframes-at-cuts \
  -f ba -x --audio-format wav --no-playlist --postprocessor-args "-ar 16000 -ac 1" \
  -o ".kbprep/phase-b-test-media/yt-f1.%(ext)s" "https://www.youtube.com/watch?v=3DlXq9nsQOE"

# 2. torch 环境自检（必须在完整 GPU venv，不是 dev venv）
#    先进入装了 .[cuda,asr] 的 venv，再跑：
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
#    预期输出：2.8.0+cu126 True
```

转写（用 kbprep provider，在**完整 GPU venv** 跑）：调 `transcribe_media(audio, run_dir, env={"KBPREP_ASR_LANGUAGE": "zh"|"en"})`，或走 kbprep CLI `kbprep-prepare` 媒体路由。

## 状态与边界

- `media_local_transcript` 状态已升 **`verified`**：manual acceptance（双链路 GPU 跑通）+ F1 version-controlled fixture（transcript 入库 + sha256 hash 锁定）+ 第二 agent 复核 + owner 批准，四项齐备。verified 守的是 fixture 内容稳定（hash 未变），不是 ASR 输出确定性（ASR 输出会随模型版本变化，hash 漂移即触发重固化）。
- 不把视频内容/音频 commit 进仓库——入库的是 transcript 衍生文本（非第三方版权原始内容）；manual acceptance 的音频样本仍只在本地（gitignored，依赖外网样本可访问）。
- 不重蹈 e18cf9a：GPU（非 CPU）、真实样本（非 TTS）、复用 GPU venv（torch 不降级）、状态诚实（verified 由 hash 锁定 + 独立复核 + owner 批准支撑，非自我声称）、依赖声明（pyproject `.[asr]`）。
