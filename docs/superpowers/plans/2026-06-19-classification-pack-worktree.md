# Classification Pack Worktree Plan

## Objective

建立文档类型分类的第一个可测试切片：在转换证据之后、清洗策略之前生成分类证据，帮助后续规则库选择正确策略。本分支只做分类证据与测试，不引入 AI 分类，不修改清洗执行结果。

## Source References

- `docs/kbprep-core-flow-design.md`
- `docs/kbprep-full-flowchart.html`
- `docs/flowchart/kbprep-flow.json`
- `docs/development/05-document-type-classification.md`
- `docs/development/06-cleaning-policy-library.md`
- `python/kbprep_worker/stages/`
- `rules/`

## Scope

- 新增最小 `document_classification.json` artifact，状态可为 `partial`。
- 基于文件类型、转换报告、标题密度、目录线索、链接/表格/代码块比例做 deterministic 分类。
- 输出分类候选、置信度、证据片段和“不足以分类”的原因。
- 为后续规则库选择提供只读输入，不直接改变清洗产物。
- 更新状态文档时只能标记为 `partial` 或目标，不能写成完整分类系统。

## Non-Goals

- 不调用 AI。
- 不实现规则库自动选择执行。
- 不创建用户私有规则。
- 不改 conversion gate 和 Canonical IR schema。
- 不把媒体、YouTube 或批处理能力写成已实现。

## TDD Steps

1. RED：新增分类测试，覆盖教程、论文/报告、网页文章、代码文档、未知类型。
2. RED：断言分类 artifact 缺少证据时不会被下游当作可用策略。
3. GREEN：实现独立分类模块和 stage 接入。
4. GREEN：生成 `document_classification.json` 并在运行报告中引用。
5. REFACTOR：分类规则集中放在单一模块，避免硬编码散落。

## Verification

- `npm run python:ruff`
- `npm run python:typecheck`
- `npm run python:test -- tests/test_document_classification.py`
- `npm run dev:check`

所有命令必须在本 worktree 内运行，并通过项目 npm 脚本或 `node scripts/python-venv.mjs` 使用项目环境。

## Audit Checklist

- 分类失败不会阻断转换质量门，但会阻断自动选择清洗策略。
- 分类依据可追溯，不是凭文件名猜测。
- 没有加入具体作者、课程、平台的硬编码清洗规则。
- 文档状态不夸大实现程度。

## Merge Criteria

- 本分支所有测试通过。
- `git diff --check` 通过。
- `kbprep-kf` 检查通过。
- 审计确认分类只是证据层，不直接改最终 Markdown。
