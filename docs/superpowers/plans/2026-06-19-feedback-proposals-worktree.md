# Feedback Proposals Worktree Plan

## Objective

强化反馈学习的安全闭环：用户反馈只能先形成规则提案，不能直接晋升为长期规则。本分支聚焦 proposal artifact、验证、接受前检查和文档一致性，不改转换或清洗主流程。

## Source References

- `docs/kbprep-core-flow-design.md`
- `docs/feedback-learning.md`
- `docs/development/09-feedback-rule-learning.md`
- `docs/capability-matrix.md`
- `rules/`
- `.kbprep/rules/` 约定

## Scope

- 明确 feedback proposal 的最小字段：scope、positive evidence、negative examples、risk note、owner confirmation 状态。
- 增强 `kbprep-feedback` 的提案生成和验收检查。
- 保证 public `rules/` 只放通用或脱敏规则，用户私有规则仍在 `.kbprep/rules/`。
- 增加治理检查，防止文档或代码宣称“反馈自动学习已完成并自动生效”。

## Non-Goals

- 不自动接受提案。
- 不把用户私有规则提交到仓库。
- 不改转换路线、Canonical IR 或质量门。
- 不引入云端同步、账号体系或多用户权限。

## TDD Steps

1. RED：增加反馈提案 schema 测试，缺少范围、证据或负例时失败。
2. RED：增加 accept 前检查测试，未确认 owner/maintainer 时拒绝晋升。
3. GREEN：补齐提案生成和接受前验证。
4. GREEN：更新文档和治理脚本，保持能力矩阵状态准确。
5. REFACTOR：把 proposal schema 和验收规则集中，避免 CLI 和检查脚本分裂。

## Verification

- `npm run python:ruff`
- `npm run python:typecheck`
- `npm run python:test -- tests/test_feedback_learning.py`
- `npm run dev:check`
- `npm run pack:check`

所有命令必须在本 worktree 内运行，并通过项目 npm 脚本或 `node scripts/python-venv.mjs` 使用项目环境。

## Audit Checklist

- 没有新增自动晋升规则路径。
- 没有提交 `.kbprep/rules/` 内的私有内容。
- 规则证据包含正例、负例和风险说明。
- 文档清楚区分已支持、部分支持和目标设计。

## Merge Criteria

- 本分支所有测试通过。
- `git diff --check` 通过。
- `kbprep-kf` 检查通过。
- 审计确认反馈学习仍是 proposal-first。
