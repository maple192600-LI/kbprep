# ASR 双链路 Manual Acceptance（Phase B）

> 定位：**manual acceptance evidence**（人工验收），不是 version-controlled verified golden fixture。能力状态 `media_local_transcript` 保持 `partial`。提升 `verified` 需可复现 fixture + 第二 agent 复核 + owner 批准（AGENTS.md + subagent-worktree-discipline §4）。

## 架构（双链路，单 venv）

| 链路 | 引擎 | 模型 | 触发 | 配置 |
|---|---|---|---|---|
| 中文 | Qwen3-ASR（transformers 后端，Python import） | `Qwen/Qwen3-ASR-1.7B` | `KBPREP_ASR_LANGUAGE=zh`（默认） | `device_map="cuda:0"` + `dtype=bfloat16` + `max_new_tokens=8192` |
| 英文 | Whisper（openai-whisper CLI） | `large-v3` | `KBPREP_ASR_LANGUAGE=en` | whisper CLI `--model large-v3`（自动 CUDA） |

- **路由**：`transcribe_media` 按 `KBPREP_ASR_LANGUAGE` 分发（`external_tools.py`）。subtitle-first 不变（YouTube 有字幕先字幕，本路由只管无字幕 media fallback）。
- **单 venv**：`qwen-asr` + `openai-whisper` 装进 kbprep 主 venv（`.[asr]` extra），复用 cuda extra 的 `torch==2.8.0+cu126`。dry-run + 实测验证装这两个包**不动 cu126 torch**（不重蹈 e18cf9a torch 被降级 CPU）。
- **配置出处**：参考 MediaCrawler `postcrawl/processors/transcript.py` 已验证的 Qwen3-ASR GPU 配置（device cuda:0 / bfloat16 / 长 max_new_tokens / Chinese）。

## Manual Acceptance 结果（2026-06-26，4060 Ti 16GB）

| 样本 | 语言 | 链路 | 耗时 | 结果 |
|---|---|---|---|---|
| YouTube `_L2Filt7l-s`（中文，前 90s） | zh | Qwen3-ASR 1.7B | 27s | 转录完整准确（CodeX/AIGC/个人IP 等术语准） |
| YouTube `FBHhmqBs894`（英文，前 90s） | en | Whisper large-v3 | 438s（含首次下 3GB 模型；后续缓存秒级） | 转录准确（copywriting/philosophy 等） |

验证项：
- `torch.cuda.is_available()==True`，版本 `2.8.0+cu126`（装 qwen-asr/openai-whisper 前后一致）。
- `import lmdeploy` / `import mineru` 正常（accelerate 1.14→1.12 兼容，没坏 mineru）。
- 真实样本（非 TTS 合成），GPU 推理（非 CPU）。

## 复现命令

样本放在本地 `.kbprep/phase-b-test-media/`（gitignored，不入仓库）。下载短片段 + 转写：

```bash
# 中文样本 → Qwen3-ASR
.kbprep/venv/Scripts/python.exe -m yt_dlp --download-sections "*0-90" --force-keyframes-at-cuts \
  -f ba -x --audio-format wav --no-playlist --postprocessor-args "-ar 16000 -ac 1" \
  -o ".kbprep/phase-b-test-media/yt-zh.%(ext)s" "https://www.youtube.com/watch?v=_L2Filt7l-s"

# 英文样本 → Whisper
.kbprep/venv/Scripts/python.exe -m yt_dlp --download-sections "*0-90" --force-keyframes-at-cuts \
  -f ba -x --audio-format wav --no-playlist --postprocessor-args "-ar 16000 -ac 1" \
  -o ".kbprep/phase-b-test-media/yt-en.%(ext)s" "https://www.youtube.com/watch?v=FBHhmqBs894"
```

转写（用 kbprep provider）：调 `transcribe_media(audio, run_dir, env={"KBPREP_ASR_LANGUAGE": "zh"|"en"})`，或走 kbprep CLI `kbprep-prepare` 媒体路由。

## 状态与边界

- `media_local_transcript` 状态保持 **`partial`**：manual acceptance 证明双链路 GPU 跑通，但不等于 verified（verified 需可复现 golden fixture + 第二 agent 复核 + owner 批准）。
- 不把视频内容/转录结果 commit 进仓库作为固定 verified 证据（manual acceptance 是人工跑、人工判断，依赖外网样本可访问）。
- 不重蹈 e18cf9a：GPU（非 CPU）、真实样本（非 TTS）、单 venv（torch 不降级）、状态诚实（partial，非虚假 verified）、依赖声明（pyproject `.[asr]`）。
