# C2R：Canonical IR 关系/资产/注解 Route-Wide 语义硬化（Wave 1 / M2）

> 日期：2026-06-27｜类型：实施 slice 计划
> 关联：`2026-06-25-kbprep-completion-parallel-plan.md` Wave 1 Branch C2R、`docs/development/02-canonical-ir-contract.md`
> 前置：C1R 已合并 main（commit 52a16de），打通转换器原生 span 证据通道
> 状态：计划已定，待在 worktree `codex/c-ir-semantics-hardening` 执行

## Context（为什么做）

`canonical_ir_contract` 与 `conversion_quality_gate` 当前为 `partial`。Wave 1 闭环（提到 `implemented`）需要 Canonical IR 成为"完整事实层"——不只是 typed_nodes 和 source_spans 有原生精度（C1R 已做），**关系/资产/注解三类 artifact 也必须承载 route-wide 语义**，而非全部退化到 converted-Markdown 顺序逻辑。

**explorer 已确认的现状（2026-06-27，read-only 调研）**：

- **relationships**（`canonical_relationships.py`）：只有 `next_sibling` + `contains` 两种 type，全部从 typed_nodes 的 converted-Markdown 顺序推导；evidence schema 锁死为 `{basis}`，无法携带 route-native 证据（如 shape_id）。无任何 route 产源结构关系。
- **assets**（`canonical_assets.py`）：只识别 Markdown 图片引用，`asset_type` 硬编码 `"image"`、`reference_kind` 硬编码 `"markdown_image"`；无 `referenced_by`、无 `source_path`（原始媒体路径）、无 table as asset。office_xml 已把图片提取到 `office_image_assets.copied`，但这个列表**完全没进 assets.json**。
- **annotations**（`canonical_annotations.py`）：**只有一条硬编码** coverage_warning；writer 签名 `write_annotations_artifact(*, run_dir, document_id)` **不接收 typed_nodes、不接收 coverage report**，无法基于实际内容质量动态生成注解。
- **根因（P0）**：`canonical_ir.py:204-206` 三个 writer 调用只传 `typed_nodes_path`，**不传 `native_source_spans`、不传 `conversion_report`**——C1R 已让这些 route-native evidence 流到 span writer，但被 relationships/assets/annotations writer 完全忽略。

**C2R 目标**：打通 route-native evidence 到三类 artifact writer 的通道，并在现有 schema 框架内扩展 route-wide 语义（不改字段名 breaking change，只扩字段集 + evidence keys + type/kind 枚举）。

## 设计决策

### 通道：经 canonical_ir 编排透传（复用 C1R 已有变量）

`canonical_ir._write_canonical_artifacts`（line 168）在写入三类 artifact 时，`native_source_spans` 已在内存（line 184 解析），`conversion_report` 也已接收。决策：把这两个透传给三个 writer（新增可选参数），不改 C1R 已合并的 span/spans_native 模块。

**不另建 sidecar 通道**：route-native evidence 属 IR 事实层，经编排透传最自然，改动面最小，且复用 C1R 已验证的变量。

### Schema 扩展：同步更新 frozenset 锁

`canonical_record_artifacts.py` 用 `frozenset(payload) == top_keys` 且 `frozenset(record) == record_keys` 锁死字段。新增字段必须同步：

- `RELATIONSHIP_RECORD_KEYS` / `RELATIONSHIP_TOP_KEYS` / relationship evidence keys
- `ASSET_RECORD_KEYS` / `ASSET_TOP_KEYS` / asset evidence keys（注：assets 当前 evidence_keys 为空集，视情况补）
- `ANNOTATION_RECORD_KEYS` / `ANNOTATION_TOP_KEYS` / annotation evidence keys

### Relationships 语义扩展

新增 type（保留现有 `contains`/`next_sibling`）：

- `references`：段落节点引用 figure/table 节点（基于 typed_nodes 的 figure/table 出现 + Markdown 图片/表格语法关联）。evidence 带 `basis`。
- `embeds`（pptx route）：shape 节点包含其内部 paragraph 节点。evidence 带 `shape_id`（从 native_source_spans 的 `pptx_shape` precision 反查同 shape_id 的节点聚合）。

**不做** `annotates`（notes → slide）：需扩展 office_xml 暴露 notes 的 slide 归属，侵入 C1R 已合并转换器，边界模糊——推迟到独立 slice。
**不做** transcript `speaker_segment`：typed_nodes metadata.speaker 虽存在，但 speaker 聚合逻辑 + 真实媒体验证属 Wave 4 范畴，C2R 不伪造。

### Assets 语义扩展

新增字段 + 枚举（保留现有 asset_id/asset_type/source_node_id/reference/reference_kind）：

- `referenced_by`：引用此资产的 node_id 列表（支持多引用）。
- `source_path`：原始媒体相对路径（office route 从 `office_image_assets.copied` 取，区别于 Markdown 引用路径）。Markdown route 可与 reference 同值或留空。
- `asset_type: "table"`：typed_nodes type=table 时记为资产，reference 指向 node_id。
- `reference_kind` 枚举扩展：`markdown_image`（现有）/ `office_embed`（pptx/docx 内嵌）/ `inline_table`。

### Annotations 语义扩展

writer 签名扩展为接收 `typed_nodes` + `coverage_report`（或 coverage gaps），动态生成注解（保留现有硬编码 coverage_warning）：

- `kind: coverage_gap` / `target: <node_id>` / `code: W_NATIVE_PRECISION_MISSING`：当某 route 节点的 span 缺 native precision（从 coverage report 的 route_native_precision gaps 取）。
- `kind: quality_warning` / `target: <node_id>` / `code: W_EMPTY_HEADING`（heading 无后续内容）/ `W_SHORT_PARAGRAPH`（段落过短，阈值常量化）。

**保留** content-safe 约束：所有 annotation 不含原文。

### Coverage Report 细化

`canonical_coverage.py` 的 relationships/assets/annotations 段当前只记 `record_count`。扩展为记 `types`/`kinds` 分布计数（如 relationships 段记 `{"contains": 5, "next_sibling": 12, "references": 3, "embeds": 2}`）。

## 文件改动范围

- `python/kbprep_worker/canonical_relationships.py`：新增 `references`/`embeds` type + evidence 扩展。
- `python/kbprep_worker/canonical_assets.py`：新增 `referenced_by`/`source_path`/table/kind 枚举。
- `python/kbprep_worker/canonical_annotations.py`：writer 签名扩展 + 动态生成 coverage_gap/quality_warning。
- `python/kbprep_worker/canonical_record_artifacts.py`：同步 frozenset 锁（RECORD_KEYS/TOP_KEYS/evidence_keys）。
- `python/kbprep_worker/canonical_ir.py`：`_write_canonical_artifacts` 透传 native_source_spans + conversion_report 给三个 writer（line 204-206）。
- `python/kbprep_worker/canonical_coverage.py`：三类段增 types/kinds 分布。
- `python/tests/test_canonical_ir_relationships.py`：RED — references/embeds route-wide。
- `python/tests/test_canonical_ir_assets.py`：RED — referenced_by/source_path/table/office_embed。
- `python/tests/test_canonical_ir_annotations.py`：RED — 动态 coverage_gap/quality_warning。
- `docs/development/02-canonical-ir-contract.md`：补 route × semantics 矩阵 + 字段要求 + 可验收条款。

**不动**：`canonical_spans.py`/`canonical_spans_native.py`/`canonical_nodes.py`/`converters/office_xml.py`/`pdf_text.py`（C1R 已合并，写集隔离）。

## 实施步骤（TDD）

- [ ] **Step 1**：开 worktree `git worktree add .worktrees/c-ir-semantics-hardening -b codex/c-ir-semantics-hardening main`，`npm ci`，基线 `npm run dev:check`。
- [ ] **Step 2 通道 RED**：测试——pptx 输入 → relationships writer 收到 native_source_spans → 产出 `embeds` 关系（evidence 带 shape_id）。先跑红。
- [ ] **Step 3 通道 GREEN**：`canonical_ir.py` 透传 + relationships writer 消费 native_source_spans 产 `embeds`。跑绿。
- [ ] **Step 4 relationships**：`references` type（段落 → figure/table）+ 测试。
- [ ] **Step 5 assets RED/GREEN**：`referenced_by`/`source_path`/`asset_type:table`/`reference_kind:office_embed` + 测试。需把 office_image_assets 经 conversion_report 透传给 assets writer（若未在 report 中，补流；若补流侵入 office_xml，降级为只读 typed_nodes figure Markdown 引用 + source_path 可选）。
- [ ] **Step 6 annotations RED/GREEN**：writer 接收 coverage report + typed_nodes → 动态 `coverage_gap`/`quality_warning` + 测试。
- [ ] **Step 7 schema 同步**：更新 `canonical_record_artifacts.py` 的 frozenset 锁，确保新字段不被 validator 拒绝。
- [ ] **Step 8 coverage 细化**：三类段增 types/kinds 分布 + 测试。
- [ ] **Step 9 合约文档**：`02-canonical-ir-contract.md` 补 route × semantics 矩阵 + 可验收条款。
- [ ] **Step 10 护栏**：现有三个 happy-path 测试仍绿（content-safe 不破）+ C1R 护栏（`test_writer_does_not_invent_*`）不破。
- [ ] **Step 11 验证**：`npm run dev:check` + `npm run check:development-docs` + `npm run check:flowchart` + reviewer subagent。
- [ ] **Step 12 合并 main**（C7 的状态提升等 C2R 合并后另做）。

## 不做什么

- 不擅自把 `canonical_ir_contract`/`conversion_quality_gate` 提 `implemented`（C7 才提，需 C1R+C2R+C7 全合并 + reviewer APPROVED + owner `KBPREP_ALLOW_STATUS_PROMOTION=1`）。
- 不做 `annotates` 关系（需扩展 office_xml notes 暴露，侵入 C1R 转换器，推迟独立 slice）。
- 不做 transcript `speaker_segment`（需真实媒体 ASR 验证，Wave 4）。
- 不在 PDF route 伪造 native 关系（PDF text-layer 无 bbox，留 MinerU，与 C1R gap 一致）。
- 不做 youtube_cue_id route（无 converter，未来 route）。
- 不改现有字段名（breaking change），只扩字段集 + evidence keys + type/kind 枚举。
- 不把原文复制进 relationship/asset/annotation（content-safe 不变）。
- 不动 C1R 已合并的 spans/nodes/office_xml/pdf_text（写集隔离）。

## 验证

- 每步：`node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_relationships python.tests.test_canonical_ir_assets python.tests.test_canonical_ir_annotations -v` + `npm run python:ruff` + `npm run python:typecheck` + `git diff --check`。
- 合并前：`npm run dev:full-check` + `npm run check:development-docs` + `npm run check:flowchart`。
- reviewer 审：无 fabricated route semantics、无 status overpromotion、content-safe 不破、schema 锁同步、C1R 写集未侵入。

## 风险与回滚

- **office_image_assets 透传**：若 `office_image_assets.copied` 当前未进 `conversion_report`，需补流（office_xml → report → assets writer）。若补流侵入 office_xml，改用"只读 typed_nodes 的 figure 节点 Markdown 引用 + 不追原始媒体路径"降级，保持 `source_path` 可选。
- **schema frozenset 锁**：新增字段漏更新 RECORD_KEYS/TOP_KEYS 会被 validator 拒绝。Step 7 必须同步全量。
- **content-safe 回归**：新 annotation（quality_warning 等）可能不小心写入段落原文。护栏测试 + reviewer 双校验。
- **回滚**：全程在 `codex/c-ir-semantics-hardening` 分支，不合 main 前可整支丢弃；worktree remove + 删分支即可。
