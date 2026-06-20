# Batch Status Rerun Worktree Plan

## Objective

建立批处理、断点续跑和受影响范围重跑的第一个安全切片：让多文件运行能记录状态、失败原因和可重跑范围。本分支只做状态和调度证据，不改变单文件 demo 主路径的稳定行为。

## Source References

- `docs/kbprep-core-flow-design.md`
- `docs/kbprep-full-flowchart.html`
- `docs/flowchart/kbprep-flow.json`
- `docs/development/10-batch-playlist-rerun.md`
- `docs/standalone-cli.md`
- `python/kbprep_worker/stages/`

## Scope

- 新增批处理 run manifest，记录每个输入的状态、artifact 目录、失败阶段、可重跑建议。
- 支持失败后只重跑失败项或受影响项的内部 contract。
- CLI 文档只写目标和部分支持边界，不声称完整批处理已完成。
- 保持单文件输出兼容，不删除旧产物。

## Non-Goals

- 不实现 YouTube playlist 下载。
- 不实现并发执行器或队列系统。
- 不改变最终 Markdown 源文件旁发布规则。
- 不改 conversion gate 判定标准。
- 不做清洗 patch 或 Clean View。

## TDD Steps

1. RED：新增 batch manifest 测试，覆盖成功、失败、跳过、可重跑建议。
2. RED：断言单文件 prepare 行为和产物名称保持兼容。
3. GREEN：实现 batch status 数据结构和写出逻辑。
4. GREEN：接入 CLI 或内部 runner 的最小状态输出。
5. REFACTOR：把单文件 run metadata 与 batch item metadata 分开，避免互相污染。

## Verification

- `npm run python:ruff`
- `npm run python:typecheck`
- `npm run python:test -- tests/test_batch_status.py`
- `npm run python:test -- tests/test_canonical_ir_manifest.py tests/test_conversion_gate.py`
- `npm run dev:check`

所有命令必须在本 worktree 内运行，并通过项目 npm 脚本或 `node scripts/python-venv.mjs` 使用项目环境。

## Audit Checklist

- 单文件主路径仍可运行。
- 批处理失败不会生成被误认为成功的最终产物。
- 可重跑范围来自证据，不是猜测。
- 文档没有把 playlist 或并发执行写成已实现。

## Merge Criteria

- 本分支所有测试通过。
- `git diff --check` 通过。
- `kbprep-kf` 检查通过。
- 审计确认单文件路径未被破坏。
