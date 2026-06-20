# Conversion Gate Evidence Worktree Plan

## Objective

把转换质量门从“检查转换报告和最小 manifest”推进为“清楚说明转换证据、失败原因、阻断范围和可修复动作”的质量关口。本分支只改转换质量门和相关证据报告，不改清洗、发布或反馈学习。

## Source References

- `docs/kbprep-core-flow-design.md`
- `docs/kbprep-full-flowchart.html`
- `docs/flowchart/kbprep-flow.json`
- `docs/development/03-deterministic-conversion-routing.md`
- `docs/development/04-conversion-quality-gate.md`
- `python/kbprep_worker/quality/conversion_gate.py`
- `python/tests/test_conversion_gate.py`

## Scope

- 梳理 conversion quality report 的证据字段：输入源、实际路线、转换报告、诊断报告、Canonical IR manifest、strict errors、warnings。
- 增加可读的 failure action，让用户知道是重新转换、换路线、补依赖、检查源文件，还是不能继续清洗。
- 增强测试覆盖：manifest 缺失、schema 错误、转换报告缺失、诊断报告缺失、转换报告声明失败。
- 保持质量门是阻断点：strict error 出现时不得继续到 cleanup。

## Non-Goals

- 不新增新的转换器。
- 不实现 OCR 逻辑或媒体下载逻辑。
- 不改变 final markdown 发布位置。
- 不改变清洗策略或规则库。
- 不改 Canonical IR schema 的字段定义；如发现 schema 缺口，记录为跨分支依赖。

## TDD Steps

1. RED：扩展 `python/tests/test_conversion_gate.py`，覆盖每类证据缺失和错误 schema。
2. RED：增加质量报告结构测试，断言 `canonical_ir_manifest`、`failure_actions` 和 `blocked_stage` 出现在报告中。
3. GREEN：修改 `conversion_gate.py` 输出结构和错误路径。
4. GREEN：确保 pipeline 在 strict error 下停止后续阶段。
5. REFACTOR：把证据构造拆成小函数，避免 gate 主函数过长。

## Verification

- `npm run python:ruff`
- `npm run python:typecheck`
- `npm run python:test -- tests/test_conversion_gate.py tests/test_canonical_ir_manifest.py`
- `npm run dev:check`

所有命令必须在本 worktree 内运行，并通过项目 npm 脚本或 `node scripts/python-venv.mjs` 使用项目环境。

## Audit Checklist

- strict error 不被 warning 替代。
- 报告不声称后续阶段已经执行。
- 错误信息对非开发者可理解。
- 没有把 gate 放宽成“尽量继续”。

## Merge Criteria

- 本分支所有测试通过。
- `git diff --check` 通过。
- `kbprep-kf` 检查通过。
- 审计确认转换质量门仍然是正式阻断点。
