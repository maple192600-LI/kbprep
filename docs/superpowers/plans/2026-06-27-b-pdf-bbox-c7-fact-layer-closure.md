# B：PDF bbox 接入 + C7 Fact-Layer Closure + 状态提升（Wave 1 闭环）

> 日期：2026-06-27｜类型：实施 slice 计划（多 slice）
> 关联：母计划 `2026-06-25-kbprep-completion-parallel-plan.md` Wave 1 Branch C7 + C1R PDF bbox gap 补全
> 前置：C1R（52a16de）+ C2R（0746cb6）已合并 main
> 决策：老李选 B（全量 implemented）—— PDF route 通过 MinerU bbox 接入获得 native span；canonical_ir_contract/conversion_quality_gate 提 implemented

## Context（为什么做）

C1R 打通了 PPTX/DOCX/XLSX 原生 span，但 PDF text-layer route（PyMuPDF `page.get_text("text")` 无坐标）诚实记 `pdf_bbox` 为 gap。C2R 打通了关系/资产/注解 route-wide 语义。两者合并后，IR fact-layer 缺口集中在：

1. **PDF bbox 未接入**：MinerU 已装 + 有 `mineru_adapter.py`（CLI wrapper）+ content_list 消费者 `blockify.py:_build_page_map` 已读 `page_idx`+`text` 做行映射，**但 content_list item 的 `bbox` 字段没读**。MinerU 产的 bbox 数据没喂给 IR source_spans。
2. **gate 不消费 route-wide IR**：`canonical_gate_evidence._has_complete_ir_evidence` 的 `complete` 判定只看 typed_nodes+source_spans，不看 relationships/assets/annotations。
3. **状态仍是 partial**：`canonical_ir.py:520` 硬编码 `"status": "partial"`。

**B 目标**：全量 implemented——PDF route 通过 MinerU bbox 接入完整；gate 消费 route-wide IR；状态提升（YouTube/音频/image optional route 仍 partial，诚实标注）。

## Slice 1：PDF bbox 接入（C1R 补全）

**Branch**：`codex/b-pdf-bbox-native-span`

**机制**（复用 C1R + blockify 现有逻辑）：
- 转换阶段（MinerU route 产 conversion_report 处）：从 `content_list` item 提 `bbox` + `page_idx` + text→行映射（复用 `_build_page_map` 的 `text.find(item_text[:40])` → `_offset_to_line`）→ 组装 `native_source_spans`（`pdf_bbox` precision：`{page, bbox, converted_line_start, converted_line_end}`）
- 喂 `conversion_report.mineru_artifacts.native_source_spans`（C1R 已有的通道，`canonical_ir._write_canonical_artifacts:184` 已提取）
- `canonical_spans` writer 命中 typed_node 行范围 + `source_kind=pdf` 时生成 `pdf_bbox` native span（C1R 的 `native_evidence_precision` 门控已支持）

**文件**：
- Modify: `python/kbprep_worker/blockify.py`（或新 helper）—— 提 bbox 进 native_source_spans
- Modify: MinerU route 产 conversion_report 的位置（把 native_source_spans 塞进 mineru_artifacts）
- Modify: `python/tests/test_canonical_ir_source_spans.py`（RED：MinerU content_list fixture → pdf_bbox native span 产出 + 行对齐）
- Modify: `docs/development/02-canonical-ir-contract.md`（PDF bbox 从 gap 改 landed）

**不动**：`canonical_spans.py`/`canonical_spans_native.py`（C1R 机制复用）；`pdf_text.py`（text-layer route 仍不产 bbox，走 MinerU route 才产）。

**风险**：MinerU content_list 的 bbox 是 block 级（段落/标题块），不是行级。映射到 typed_node 行用 text find（已有机制），bbox 取 block 级即可（pdf_bbox schema 接受 page+bbox，不要求行级精度）。若 text find 失败（item_text 不在 converted text），跳过该 item 不强造（C1R 护栏）。

## Slice 2：C7 gate 扩展

**Branch**：`codex/c-ir-fact-layer-closure`（母计划 C7 分支名）

**改动**：
- `canonical_gate_evidence.py`：`_has_complete_ir_evidence` 的 `complete` 判定加入 relationships/assets/annotations available 检查（从 coverage.report 取）
- `conversion_gate.py`：route claim complete IR 但 relationships/assets/annotations 缺失/不一致 → 转 strict_error（block）
- 测试：`test_conversion_gate.py` RED——manifest 声称 relationships_available=True 但 artifact 缺 → gate block

**文件**（母计划 C7 写集）：
- Modify: `python/kbprep_worker/canonical_gate_evidence.py`
- Modify: `python/kbprep_worker/quality/conversion_gate.py`
- Modify: `python/tests/test_conversion_gate.py`

## Slice 3：状态提升

**Branch**：同 Slice 2（C7 分支内）或独立 status commit

**改动**：
- `canonical_ir.py:520`：`"status": "partial"` → `"implemented"`（或根据 coverage 动态）
- `docs/development/kbprep-implementation-status.json`：`canonical_ir_contract`/`conversion_quality_gate` status → implemented；scope 诚实标注"YouTube/media/image optional route 仍 partial（Wave 4）"
- `docs/development/development-roadmap.md`：Phase C 标 closed
- `docs/capability-matrix.md`：若涉及 route status 更新
- `docs/development/02-canonical-ir-contract.md`：Current Shipped Boundary 更新

**owner marker**：`KBPREP_ALLOW_STATUS_PROMOTION=1`（老李选 B = 授权状态提升；governance `subagent-worktree-discipline.mjs:67-85` 放行）

**第二审**：Claude reviewer（codex 命令通道 1312 仍坏）

## 不做什么

- `youtube_cue_id` native span（Wave 4 F3，需真实字幕样本验证）
- 音频/image/legacy office route 的 native span（Wave 4 optional route，本身 partial/experimental）
- 改 YouTube route 的 partial 状态（route 本身 partial，待 Wave 4 真实证据）
- obsidian profile IR regeneration（当前设计保留 curated text，`test_ir_markdown_regeneration.py:50` 已 pin，不改）

## 验证

- 每步：相关 unittest + `npm run python:ruff` + `npm run python:typecheck` + `npm run python:check-size`
- 合并前：`npm run dev:full-check` + `npm run check:development-docs` + `npm run check:governance`（状态提升需 owner marker）+ Claude reviewer APPROVED

## 执行顺序

1. **Slice 1**（PDF bbox 接入）先——C7 状态提升需 PDF route 完整。独立分支 `codex/b-pdf-bbox-native-span`，合并 main。
2. **Slice 2 + 3**（C7 gate 扩展 + 状态提升）——分支 `codex/c-ir-fact-layer-closure`，从含 Slice 1 的 main 开。合并 main。
3. Wave 1 闭环（C1R+C2R+B 全合并 + status implemented）。

## 风险与回滚

- MinerU content_list bbox 格式：若实测 bbox 字段缺失或格式不同，Slice 1 降级为"只提 page_idx（page 级 span），bbox 留 future"——但目标尽量拿 bbox。
- 状态提升 overpromote 风险：scope 必须诚实标注哪些 route 完整、哪些 partial。Claude reviewer 把关。
- 回滚：每 slice 独立分支，不合 main 前可整支丢弃。
