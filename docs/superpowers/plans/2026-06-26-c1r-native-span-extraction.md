# C1R：转换器原生 SourceSpan 提取（Wave 1 / M2）

> 日期：2026-06-26｜类型：实施 slice 计划
> 关联：`2026-06-25-kbprep-completion-parallel-plan.md` Wave 1 Branch C1R、`docs/development/02-canonical-ir-contract.md`
> 状态：计划已定，待在 worktree `codex/c-native-span-extraction` 执行

## Context（为什么做）

`canonical_ir_contract` 与 `conversion_quality_gate` 当前为 `partial`。项目完成定义要求它们提到 `implemented`，依赖 Canonical IR 成为"完整事实层"——每个 typed_node 都能指向源文件里的精确位置。

**explorer 已确认的现状**：
- SourceSpan 的 **schema + validator 已完整支持** 9 种 precision（`pdf_bbox`/`docx_run_range`/`pptx_shape`/`xlsx_cell_range`/`transcript_cue_id`/`youtube_cue_id` 等），并有守护测试确保 writer 不编造（`test_writer_does_not_invent_pdf_bbox_without_native_evidence`）。
- **缺口**：writer `write_source_spans_artifact`（`canonical_spans.py:97`）只接收 converted Markdown + input_path，**不接收转换器原生证据**；转换器 `office_xml.py`/`pdf_text.py` 也**根本不提取** bbox/run/shape/cell。→ 原生 precision 有 schema 却无人产生，全部退化为 `converted_line_range`。

**C1R 目标**：打通"转换器原生证据 → span writer"通道，让 PDF/DOCX/PPTX/XLSX 在源文件含可提取坐标时，产出对应原生 precision span。

## 设计决策：证据经 conversion_report 流转

writer 当前签名只吃 converted Markdown。原生证据通道两候选：
- **方案 A（采用）**：转换器把原生证据写入 `conversion_report` 新字段（如 `native_source_spans`）。`_write_canonical_artifacts`（`canonical_ir.py:168`）**已接收** `conversion_report`，把它（或提取出的 native 证据）传给 `_write_validated_source_spans`（`:241`）→ `write_source_spans_artifact`。复用现有通道，writer 签名只多一个可选参数。
- 方案 B（弃）：独立 sidecar JSON。多一次 IO，解耦但碎。

**选 A**：`conversion_report` 已是"转换器产出 → IR"的标准通道，原生坐标属转换产出，放这里语义最自然，改动面最小。

**匹配逻辑**：native 证据按 converted line range 关联到 typed_node；命中则生成对应 precision（如 `pptx_shape`），未命中保持 `converted_line_range`（现有护栏不变）。

## 文件改动范围

- `python/kbprep_worker/canonical_spans.py`：writer 加 `native_evidence` 可选参数；`_span_location`/`_span_evidence` 据此在命中时生成原生 precision。
- `python/kbprep_worker/canonical_ir.py`：`_write_validated_source_spans` 从 `conversion_report` 提取 native 证据传给 writer。
- `python/kbprep_worker/converters/office_xml.py`：PPTX 提 `shape_id`、DOCX 提 run range、XLSX 提 cell range，写入 `conversion_report`。
- `python/kbprep_worker/pdf_text.py`：提 PDF bbox（对接 PyMuPDF/MinerU 坐标输出）。
- 测试：`python/tests/test_canonical_ir_source_spans.py`（RED：有证据→原生 precision）、office_xml/pdf 相关转换器测试。
- 文档：`docs/development/02-canonical-ir-contract.md`。

## 实施步骤（TDD，先最小验证机制再扩转换器）

- [ ] **Step 1**：开 worktree `git worktree add .worktrees/c-native-span-extraction -b codex/c-native-span-extraction main`，`npm ci`。
- [ ] **Step 2 机制 RED**：加测试——writer 收到 PPTX `shape_id` 证据 → 生成 `pptx_shape` precision span；无证据 → 仍 `converted_line_range`。先跑红。
- [ ] **Step 3 机制 GREEN**：writer 加 `native_evidence` 参数 + line-range 匹配；canonical_ir 编排传证。跑绿。
- [ ] **Step 4 PPTX**：`office_xml.py` 提 `shape_id`（已解析 slide，最小改造）+ 转换器测试。
- [ ] **Step 5 PDF bbox**：`pdf_text.py` 对接坐标输出 + 测试。若工具不给行级 bbox → 记 gap 到 `coverage.report`（schema 已支持），**不强造**。
- [ ] **Step 6 DOCX run / XLSX cell**：解析 OOXML 提取 + 测试。
- [ ] **Step 7 护栏**：`test_writer_does_not_invent_pdf_bbox_without_native_evidence` 等仍绿。
- [ ] **Step 8 验证**：`npm run dev:check` + `npm run check:development-docs` + reviewer subagent（审无 fabricated span / 无 overclaim / 护栏完整）。
- [ ] **Step 9 合并 main**（C7 的 `canonical_ir_contract`/`conversion_quality_gate` 状态提升等 C1R + C2R 都合并后另做）。

## 不做什么

- 不擅自把 `canonical_ir_contract` 提 `implemented`（C7 才提，需 C1R+C2R 完成 + reviewer APPROVED + owner 标记 `KBPREP_ALLOW_STATUS_PROMOTION=1`）。
- 不编造原生证据（无坐标时退化 `converted_line_range`，schema 的 coverage 报告如实记 missing kinds）。
- 不在本 slice 碰 C2R（关系/资产/注解）——独立分支，写集不冲突可并行。

## 验证

- 每步：`node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_source_spans -v` + `npm run python:ruff` + `npm run python:typecheck` + `git diff --check`。
- 合并前：`npm run dev:full-check` + `npm run check:development-docs` + `npm run check:flowchart`。
- reviewer 审：无 fabricated source span、无 target-only overclaim、状态仍 partial 直到 C7。

## 风险与回滚

- **PDF bbox 提取**：PyMuPDF4LLM/MinerU 的文本层输出未必带行级 bbox。Step 5 若不可行，**不强造**——在 `coverage.report` 记 `pdf_bbox` 为 missing kind（schema 已支持此报告），保持诚实 partial。可在 C1R 内只做 PPTX/DOCX/XLSX，PDF bbox 留待 MinerU OCR 路径单独处理。
- **OOXML 解析复杂度**：DOCX run range / XLSX cell range 需解析 XML 结构映射到 Markdown 行，可能 line-range 对齐有坑——先 PPTX（最简）验证机制，再依次扩。
- **回滚**：全程在 `codex/c-native-span-extraction` 分支，不合 main 前可整支丢弃；worktree remove + 删分支即可。
