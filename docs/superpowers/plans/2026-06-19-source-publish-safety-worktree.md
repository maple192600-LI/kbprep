# Source Publish Safety Worktree Plan

## Objective

强化最终结果发布到源文件旁边的安全规则：最终 Markdown 只能在质量门通过后发布，中间输出可以清理但证据必须可追溯。本分支只处理发布安全、清理状态和可验收报告，不改转换或清洗算法。

## Source References

- `docs/kbprep-core-flow-design.md`
- `docs/quality-loop.md`
- `docs/standalone-cli.md`
- `docs/development/08-source-side-publish.md`
- `docs/development/12-release-acceptance-and-governance.md`
- `python/kbprep_worker/`

## Scope

- 明确 final markdown、assets、latest_outputs、review_needed、安全清理状态之间的 contract。
- 增加测试：质量门失败时不得写源文件旁最终结果。
- 增加测试：清理 output_root 时不删除源文件旁 final deliverable。
- 输出 owner-readable publish report，说明哪些文件可保留、哪些只是过程证据。

## Non-Goals

- 不改变清洗规则。
- 不新增格式转换器。
- 不实现 Clean View。
- 不删除现有兼容产物。
- 不把失败输出伪装成最终结果。

## TDD Steps

1. RED：增加发布失败保护测试，conversion 或 cleanup strict error 时 final output 不出现。
2. RED：增加 cleanup lifecycle 测试，final deliverable 不被 `output_root` 清理删除。
3. GREEN：补齐发布前断言和 publish report。
4. GREEN：补齐 CLI/operator 文档中的验收描述。
5. REFACTOR：把发布决策和清理决策分开，保持职责清晰。

## Verification

- `npm run python:ruff`
- `npm run python:typecheck`
- `npm run python:test -- tests/test_publish_safety.py`
- `npm run dev:check`
- `npm run pack:check`

所有命令必须在本 worktree 内运行，并通过项目 npm 脚本或 `node scripts/python-venv.mjs` 使用项目环境。

## Audit Checklist

- 不绕过质量门直接写最终 Markdown。
- 源文件旁 final deliverable 与 output_root 清理生命周期分开。
- 失败原因对非开发者可理解。
- 文档与最高设计文档一致。

## Merge Criteria

- 本分支所有测试通过。
- `git diff --check` 通过。
- `kbprep-kf` 检查通过。
- 审计确认发布规则没有被放宽。
