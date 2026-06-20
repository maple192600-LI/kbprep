# KBPrep Canonical IR 首个开发切片与质量防跑偏计划

## Summary

本切片在现有 `converted.md`、`conversion_report.json` 和清洗流程旁边，并行新增最小 Canonical IR manifest 证据。目标是让转换阶段开始写入可追溯的 IR manifest，并让清洗前转换质量门读取它。

本切片不替换现有稳定产物，不改变源文件旁发布规则，不引入 Clean View、CleaningPatch 或 CleaningPolicySnapshot 的完整实现。

## Scope

本次允许修改：

- `python/kbprep_worker/canonical_ir.py`
- `python/kbprep_worker/stages/pipeline_conversion.py`
- `python/kbprep_worker/quality/conversion_gate.py`
- `python/tests/test_canonical_ir_manifest.py`
- `python/tests/test_conversion_gate.py`
- `docs/development/kbprep-implementation-status.json`

本次允许新增：

- `docs/superpowers/plans/2026-06-19-canonical-ir-first-slice.md`
- `canonical_ir/manifest.json` 运行产物
- `document_manifest.json` 运行产物

## Artifact Contract

`canonical_ir/manifest.json` 必须包含：

- `schema: "kbprep.canonical_ir_manifest.v1"`
- `document_id`
- `source_snapshot`
- `conversion`
- `artifacts`
- `coverage`
- `status: "partial"`

`source_snapshot` 至少包含：

- `input_path`
- `input_name`
- `input_sha256`
- `input_size`
- `source_type`

`conversion` 至少包含：

- `converter`
- `actual_route`
- `route_decision`

`artifacts` 至少包含：

- `converted_md`
- `conversion_report`
- `diagnosis_report`

`coverage` 至少包含：

- `typed_nodes_available`
- `source_spans_available`
- `assets_available`

`document_manifest.json` 必须包含：

- `schema: "kbprep.document_manifest.v1"`
- `canonical_ir_manifest`
- `conversion_report`
- `converted_md`
- `created_from_run`

## TDD Plan

### RED

新增 `python/tests/test_canonical_ir_manifest.py`：

- 成功 prepare 后必须存在 `canonical_ir/manifest.json`。
- 成功 prepare 后必须存在 `document_manifest.json`。
- `conversion_quality_report.json` 必须引用 Canonical IR manifest 和 document manifest。
- manifest 缺失时，`run_pre_clean_conversion_gate` 必须返回 strict error，阻止后续清洗。

先运行：

```powershell
node scripts/python-venv.mjs -m unittest discover -s python/tests -p test_canonical_ir_manifest.py -v
```

预期失败原因必须是 artifact 不存在或质量门尚未校验 manifest。

### GREEN

新增 `python/kbprep_worker/canonical_ir.py`：

- 只根据已有 run metadata、diagnosis report、conversion report 和转换输出写 manifest。
- 不承载清洗逻辑。
- 不构造完整 typed nodes。
- 不构造 source spans。
- 不改 splitter、render、publish 和 cleanup 逻辑。

修改转换阶段：

- 在 `conversion_report.json` 写出后，写出 `canonical_ir/manifest.json` 和 `document_manifest.json`。

修改转换质量门：

- 读取并校验 `canonical_ir/manifest.json`。
- 读取并校验 `document_manifest.json`。
- 校验失败时写入清晰 strict error。
- 校验通过时把 manifest 路径写入 `conversion_quality_report.json`。

## Rollback Rules

如出现不可接受的回归，回滚范围只限：

- 删除 `python/kbprep_worker/canonical_ir.py`
- 移除转换阶段对 manifest 写入的调用
- 移除转换质量门的 manifest 校验
- 删除本切片新增测试
- 将 `canonical_ir_contract` 恢复为 `design_only`

不得借回滚删除或改写旧稳定运行产物。

## Forbidden Scope

本切片严禁：

- 把 Markdown 终局替换为 IR。
- 删除、重命名或替换 `converted.md`、`normalized.md`、`blocks.jsonl`、`chunk_manifest.jsonl`、`quality_report.json`。
- 修改源文件旁发布规则。
- 实现 CleaningPolicySnapshot。
- 实现 CleaningPatch。
- 实现 Clean View。
- 把 YouTube 或 media 目标能力写成已实现。
- 把 `canonical_ir_contract` 标为 `implemented`。
- 声称 Canonical IR 已经成为完整 worker fact layer。

## Acceptance Commands

```powershell
node scripts/python-venv.mjs -m unittest discover -s python/tests -p test_canonical_ir_manifest.py -v
npm run python:test
KBPREP_ALLOW_CORE_DOC_EDIT=1 npm run dev:check
npm test
git diff --check
```

## Drift Checks

完成前必须搜索禁止声明和旧阶段残留：

```powershell
rg -n "Canonical IR is the complete shipped worker fact layer|canonical_ir_contract.*implemented|YouTube input is a verified standalone CLI capability" docs README.md AGENTS.md scripts package.json
rg -n "基础 Markdown|小资料|大资料|旧阶段|04-structure-block-chunk|block_quality_gate|merge_completeness_gate|final_quality_gate" docs README.md AGENTS.md scripts package.json
```

命中必须逐条判断。正式设计和当前实施文档不得出现当前语义冲突。
