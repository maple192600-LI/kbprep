# Canonical IR Schema Worktree Plan

## Objective

把当前最小 Canonical IR manifest 从“可写出的部分证据”推进为“有明确契约和验证器的部分事实层”。本分支只强化 schema、路径引用、hash、状态和错误信息，不把 Canonical IR 扩展成完整 worker fact layer。

## Source References

- `docs/kbprep-core-flow-design.md`
- `docs/kbprep-full-flowchart.html`
- `docs/flowchart/kbprep-flow.json`
- `docs/development/02-canonical-ir-contract.md`
- `docs/development/04-conversion-quality-gate.md`
- `python/kbprep_worker/canonical_ir.py`
- `python/kbprep_worker/quality/conversion_gate.py`

## Scope

- 为 `canonical_ir/manifest.json` 和 `document_manifest.json` 增加集中 schema 常量和验证函数。
- 统一 manifest 内部路径引用为相对运行目录的可追溯路径。
- 覆盖 source hash、conversion report、diagnosis report、converted markdown、route 摘要和 coverage 状态。
- 让 conversion gate 复用同一个验证函数，避免 gate 和 writer 各自维护一套字段判断。
- 增加 owner-readable strict error，说明缺失字段、错误 schema 或路径不可解析的具体原因。

## Non-Goals

- 不实现 typed nodes、source spans、asset registry 的完整抽取。
- 不替换 `converted.md`、`normalized.md`、`blocks.jsonl`、`chunk_manifest.jsonl`。
- 不实现 CleaningPolicySnapshot、CleaningPatch、Clean View。
- 不调整源文件旁发布规则。
- 不把 `canonical_ir_contract` 状态改成 `implemented`。

## TDD Steps

1. RED：增加 `python/tests/test_canonical_ir_schema.py`，断言缺失 schema、错误 schema、缺失关键 artifact、不可解析路径都会失败。
2. RED：增加成功路径测试，断言 writer 产物通过同一验证器，且 gate 报告引用 canonical manifest。
3. GREEN：在 `python/kbprep_worker/canonical_ir.py` 内实现 dataclass 契约、schema 常量和验证函数。
4. GREEN：让 conversion gate 调用 Canonical IR 验证函数，只保留 gate 自己的质量判断。
5. REFACTOR：删除重复字段集合，保持文件和函数尺寸符合项目限制。

## Verification

- `npm run python:ruff`
- `npm run python:typecheck`
- `npm run python:test -- tests/test_canonical_ir_manifest.py tests/test_canonical_ir_schema.py tests/test_conversion_gate.py`
- `npm run dev:check`

所有命令必须在本 worktree 内运行，并通过项目 npm 脚本或 `node scripts/python-venv.mjs` 使用项目环境。

## Audit Checklist

- manifest 失败会阻止后续清洗，而不是静默降级。
- manifest 的 `status` 仍为 `partial`。
- README、能力矩阵、状态文档没有把 Canonical IR 写成完整已实现。
- 错误码如果新增，必须同步 `src/errorCodes.ts` 并运行契约测试。

## Merge Criteria

- 本分支所有测试通过。
- `git diff --check` 通过。
- `kbprep-kf` 检查通过。
- 代码审计确认没有扩大到 Clean View、Patch、反馈学习或批处理范围。
