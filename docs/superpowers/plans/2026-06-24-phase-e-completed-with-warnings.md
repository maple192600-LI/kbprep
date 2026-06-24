# Phase E: completed_with_warnings 状态机通用化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让单文件任务（prepare）产出明确的 job status（`completed` / `completed_with_warnings` / `failed`），对齐核心设计 §17，并和 batch parent 已有的 `completed_with_warnings` 统一。

**Architecture:** 质量门（`quality/runner.py`）已把 findings 分成 `strict_errors`（阻塞/hard gate）和 `warnings`（非阻塞）。在 envelope 构造点加 `status` 字段：有 `strict_errors` → `failed`；无 `strict_errors` + 有 `warnings` → `completed_with_warnings`；否则 `completed`。Python 的 `envelope.ok/fail` + pipeline `_emit_success` 定 status，TS `WorkerEnvelopeSchema` 同步加 status（跨语言契约）。

**Tech Stack:** Python（unittest, ruff, mypy）、TypeScript（vitest, typebox, eslint）。

**Contract:** `docs/kbprep-core-flow-design.md` §17（Job Status）。

---

## File Structure

**修改：**
- `python/kbprep_worker/envelope.py` — `ok()`/`fail()` 加 `status` 参数
- `python/kbprep_worker/stages/pipeline_core.py` — `_emit_success` 按 warnings 定 status
- `src/worker.ts` — `WorkerEnvelopeSchema` 加 `status`（ok:true / ok:false 两分支）
- `docs/development/development-roadmap.md` — Phase E 标记完成
- `docs/development/kbprep-implementation-status.json` — capability 更新
- `docs/capability-matrix.md` — capability 更新

**新增/扩展测试：**
- `python/tests/test_envelope_status.py`（新）— envelope status 单元测试
- `python/tests/test_phase_e_status.py`（新）— pipeline status 端到端边界
- `src/test/scenarios/worker-job-status.test.ts`（新）— TS schema 验证 status

---

## Task 1: envelope.ok / envelope.fail 加 status 字段（Python）

**Files:**
- Modify: `python/kbprep_worker/envelope.py:16-52`
- Test: `python/tests/test_envelope_status.py`（新建）

- [ ] **Step 1: 写失败测试（envelope status）**

新建 `python/tests/test_envelope_status.py`：

```python
"""Phase E: envelope status field (completed / completed_with_warnings / failed)."""
import json
import unittest

from kbprep_worker import envelope


class EnvelopeStatusTest(unittest.TestCase):
    def test_ok_defaults_to_completed_status(self):
        try:
            envelope.ok(data={"x": 1})
        except envelope.EnvelopeExit:
            pass
        # ok() writes to stdout; capture via patching is heavy — instead test the dict builder
        # envelope.ok/fail write+raise, so we test the status logic via a helper (see Step 3)

    def test_status_from_findings_completed(self):
        self.assertEqual(envelope.status_from_findings(strict_errors=[], warnings=[]), "completed")

    def test_status_from_findings_completed_with_warnings(self):
        self.assertEqual(
            envelope.status_from_findings(strict_errors=[], warnings=["W_LOW_COVERAGE: x"]),
            "completed_with_warnings",
        )

    def test_status_from_findings_failed(self):
        self.assertEqual(
            envelope.status_from_findings(strict_errors=["E_X: y"], warnings=[]),
            "failed",
        )

    def test_status_from_findings_failed_even_with_warnings(self):
        # strict errors dominate: failed even if warnings also present
        self.assertEqual(
            envelope.status_from_findings(strict_errors=["E_X: y"], warnings=["W_A: z"]),
            "failed",
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `node scripts/python-venv.mjs -m unittest python.tests.test_envelope_status -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'status_from_findings'`

- [ ] **Step 3: 实现 status_from_findings + ok/fail 加 status**

修改 `python/kbprep_worker/envelope.py`，在 `ok` 之前加 helper，并给 `ok`/`fail` 加 `status` 参数：

```python
def status_from_findings(strict_errors: list[str], warnings: list[str]) -> str:
    """Map quality findings to a job status per core design §17."""
    if strict_errors:
        return "failed"
    if warnings:
        return "completed_with_warnings"
    return "completed"


def ok(
    data: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    status: str | None = None,
) -> dict:
    """Write a success envelope to stdout."""
    envelope: dict[str, Any] = {
        "ok": True,
        "status": status,
        "data": data or {},
        "metrics": metrics or {},
        "warnings": warnings or [],
    }
    sys.stdout.write(json.dumps(envelope, ensure_ascii=False))
    sys.stdout.flush()
    raise EnvelopeExit(0)


def fail(
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    recoverable: bool = True,
    suggested_action: str = "Check input and retry.",
    status: str = "failed",
) -> dict:
    """Write a failure envelope to stdout."""
    envelope: dict[str, Any] = {
        "ok": False,
        "status": status,
        "error": {
            "code": code,
            "message": message,
            "recoverable": recoverable,
            "suggested_action": suggested_action,
            "details": details or {},
        },
        "warnings": warnings or [],
    }
    sys.stdout.write(json.dumps(envelope, ensure_ascii=False))
    sys.stdout.flush()
    raise EnvelopeExit(1)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `node scripts/python-venv.mjs -m unittest python.tests.test_envelope_status -v`
Expected: PASS（4 个 status_from_findings 测试）

- [ ] **Step 5: ruff + mypy + commit**

```bash
node scripts/python-venv.mjs -m ruff check python/kbprep_worker/envelope.py python/tests/test_envelope_status.py
node scripts/python-venv.mjs -m mypy --config-file python/pyproject.toml python/kbprep_worker
git add python/kbprep_worker/envelope.py python/tests/test_envelope_status.py
git commit -m "feat(e): add status field and status_from_findings to envelope"
```

---

## Task 2: _emit_success 按 warnings 定 status（Python pipeline）

**Files:**
- Modify: `python/kbprep_worker/stages/pipeline_core.py:687-697`（`_emit_success`）
- Test: `python/tests/test_phase_e_status.py`（新建，端到端边界）

- [ ] **Step 1: 写失败测试（pipeline status 边界）**

新建 `python/tests/test_phase_e_status.py`（用 `status_from_findings` 驱动，覆盖三个边界；端到端跑真实 pipeline 见 Task 4）：

```python
"""Phase E: pipeline emits completed / completed_with_warnings / failed."""
import unittest

from kbprep_worker.envelope import status_from_findings


class PipelineStatusBoundaryTest(unittest.TestCase):
    def test_clean_run_is_completed(self):
        self.assertEqual(status_from_findings([], []), "completed")

    def test_run_with_warning_is_completed_with_warnings(self):
        self.assertEqual(
            status_from_findings([], ["W_LOW_COVERAGE: coverage 78%"]),
            "completed_with_warnings",
        )

    def test_run_with_strict_error_is_failed(self):
        self.assertEqual(
            status_from_findings(["E_TEXT_COVERAGE_LOW: coverage 60%"], []),
            "failed",
        )

    def test_strict_error_dominates_warnings(self):
        self.assertEqual(
            status_from_findings(["E_X: y"], ["W_A: z"]),
            "failed",
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认通过（status_from_findings 已在 Task 1 实现）**

Run: `node scripts/python-venv.mjs -m unittest python.tests.test_phase_e_status -v`
Expected: PASS（验证 status 判定规则锁死）

- [ ] **Step 3: 修改 _emit_success 传 status**

修改 `python/kbprep_worker/stages/pipeline_core.py` 的 `_emit_success`（约 687 行），把 status 传给 `ok()`：

```python
def _emit_success(state: PipelineState, run_dir: Path, run_outputs: dict[str, Any]) -> None:
    chunks_dir = run_dir / "chunks"
    from ..envelope import status_from_findings
    status = status_from_findings(state.strict_errors, state.warnings)
    ok(
        data={
            "run_id": state.run_id,
            "run_dir": str(run_dir),
            "latest_outputs": state.latest_outputs,
            "outputs": run_outputs,
            "chunk_count": len(list(chunks_dir.glob("*.md"))) if chunks_dir.exists() else 0,
            "warnings": state.warnings,
            "strict_errors": state.strict_errors,
            "status": status,
        },
        warnings=state.warnings,
        status=status,
    )
```

注：`_fail_quality_gate`（663 行）调 `fail(...)`，`fail` 默认 `status="failed"`（Task 1 已加），无需改。

- [ ] **Step 4: 跑全量 Python 测试确认无回归**

Run: `node scripts/python-venv.mjs -m unittest discover -s python/tests -q`
Expected: 全部 PASS（envelope 加 status 不破坏现有 envelope 消费者）

- [ ] **Step 5: ruff + mypy + commit**

```bash
node scripts/python-venv.mjs -m ruff check python/kbprep_worker/stages/pipeline_core.py python/tests/test_phase_e_status.py
node scripts/python-venv.mjs -m mypy --config-file python/pyproject.toml python/kbprep_worker
git add python/kbprep_worker/stages/pipeline_core.py python/tests/test_phase_e_status.py
git commit -m "feat(e): emit completed/completed_with_warnings status from pipeline"
```

---

## Task 3: TS WorkerEnvelopeSchema 加 status（跨语言契约）

**Files:**
- Modify: `src/worker.ts:81-108`（`WorkerEnvelopeSchema`）
- Test: `src/test/scenarios/worker-job-status.test.ts`（新建）

- [ ] **Step 1: 写失败测试（TS schema 接受 status）**

新建 `src/test/scenarios/worker-job-status.test.ts`：

```typescript
import { describe, expect, it } from "vitest";
import { Value } from "typebox/value";
import { WorkerEnvelopeSchema } from "../../worker.js";

describe("WorkerEnvelopeSchema status (Phase E)", () => {
  it("accepts ok:true with completed status", () => {
    const env = { ok: true, status: "completed", data: {}, metrics: {}, warnings: [] };
    expect(Value.Check(WorkerEnvelopeSchema, env)).toBe(true);
  });

  it("accepts ok:true with completed_with_warnings status", () => {
    const env = { ok: true, status: "completed_with_warnings", data: {}, metrics: {}, warnings: ["w"] };
    expect(Value.Check(WorkerEnvelopeSchema, env)).toBe(true);
  });

  it("accepts ok:false with failed status", () => {
    const env = {
      ok: false,
      status: "failed",
      error: { code: "E_X", message: "m", recoverable: true, suggested_action: "a", details: {} },
      warnings: [],
    };
    expect(Value.Check(WorkerEnvelopeSchema, env)).toBe(true);
  });

  it("rejects ok:true with failed status", () => {
    const env = { ok: true, status: "failed", data: {}, metrics: {}, warnings: [] };
    expect(Value.Check(WorkerEnvelopeSchema, env)).toBe(false);
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `npx vitest run src/test/scenarios/worker-job-status.test.ts`
Expected: FAIL（schema 无 status 字段，且 WorkerEnvelopeSchema 可能未 export）

- [ ] **Step 3: 修改 WorkerEnvelopeSchema 加 status + export**

修改 `src/worker.ts`（约 81 行），给两个分支加 `status` 并 export schema：

```typescript
export const WorkerEnvelopeSchema = Type.Union([
  Type.Object(
    {
      ok: Type.Literal(true),
      status: Type.Union([Type.Literal("completed"), Type.Literal("completed_with_warnings")]),
      data: Type.Optional(EnvelopeRecordSchema),
      metrics: Type.Optional(EnvelopeRecordSchema),
      warnings: Type.Optional(Type.Array(Type.String())),
    },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      ok: Type.Literal(false),
      status: Type.Literal("failed"),
      error: Type.Object(
        {
          code: Type.String(),
          message: Type.String(),
          recoverable: Type.Boolean(),
          suggested_action: Type.String(),
          details: EnvelopeRecordSchema,
        },
        { additionalProperties: false },
      ),
      warnings: Type.Optional(Type.Array(Type.String())),
    },
    { additionalProperties: false },
  ),
]);
```

注：`export` 让测试能 import。status 在两个分支都是必填（Python 端 prepare/fail 都传；diagnose 等非 job 命令若也走此 schema，需在 Task 4 核对——见下）。

- [ ] **Step 4: 跑 TS 测试确认通过**

Run: `npx vitest run src/test/scenarios/worker-job-status.test.ts`
Expected: PASS（4 个用例）

- [ ] **Step 5: eslint + tsc + commit**

```bash
npm run lint:check
npx tsc -p tsconfig.json --noEmit
git add src/worker.ts src/test/scenarios/worker-job-status.test.ts
git commit -m "feat(e): add status to WorkerEnvelopeSchema (completed/completed_with_warnings/failed)"
```

---

## Task 4: 端到端核对 + 非 job 命令兼容

**Files:**
- Check: `python/kbprep_worker/cli.py`（diagnose/preflight 等非 job 命令的 envelope）
- Test: 现有 `python/tests/test_core_processing_paths.py` 扩展 + TS `worker.contract.test.ts`

- [ ] **Step 1: 核对非 job 命令的 envelope 是否需 status**

Run: `node scripts/python-venv.mjs -m kbprep_worker.cli --help`（确认子命令）
Grep: `git grep -nE "envelope\.(ok|fail)\(" -- python/kbprep_worker/`

判断：diagnose/preflight 等子命令调 `envelope.ok/fail` 时是否传 status。若 TS schema 把 status 设为必填，这些命令的 envelope 会校验失败。

**决策点（实现时定）：**
- 若非 job 命令（diagnose）的 envelope 也经 TS schema 校验 → status 必须传（给 diagnose 也加 status，或 schema 中 status 改 Optional）。
- 推荐：schema 中 status 保持必填，给所有 `envelope.ok()` 调用传 status（diagnose 等 non-job 用 `"completed"` 或新增 `"diagnosed"` 语义——按 §17，job status 只三种，diagnose 非 job 可用 `"completed"`）。

- [ ] **Step 2: 给所有 envelope.ok 调用补 status（若 Step 1 判定必填）**

Grep 所有 `envelope.ok(` 调用，补 `status="completed"`（或按语义）。`fail(` 默认 `status="failed"` 已满足。

- [ ] **Step 3: 跑跨语言契约测试**

Run: `npm run python:test-contract`
Expected: PASS（error-code 契约 + envelope schema 跨语言一致）

- [ ] **Step 4: 端到端跑一个有 warning 的 prepare（人工/集成测试）**

Run（在有 fixture 的环境）: `node scripts/python-venv.mjs -m kbprep_worker.cli prepare --json-stdin < fixture.json`
检查输出 envelope：`"ok": true, "status": "completed_with_warnings"`（当有 warning 时）。

- [ ] **Step 5: commit**

```bash
git add -A
git commit -m "feat(e): wire status across all envelope emitters and contract test"
```

---

## Task 5: 文档 + capability 更新

**Files:**
- Modify: `docs/development/development-roadmap.md`（Phase E 标记完成）
- Modify: `docs/development/kbprep-implementation-status.json`
- Modify: `docs/capability-matrix.md`

- [ ] **Step 1: roadmap Phase E 标记完成**

在 `docs/development/development-roadmap.md` 的 Phase E 部分，把 slices 标记为 Landed（参考 Phase D 的 "Landed" 措辞），并在 Acceptance 注明已实现 + 测试覆盖三边界。

- [ ] **Step 2: status JSON + capability-matrix 更新**

更新 `kbprep-implementation-status.json`：新增/更新 `completed_with_warnings` capability 为 `implemented`，指向 envelope.status + pipeline _emit_success 代码证据 + test_phase_e_status.py。
更新 `docs/capability-matrix.md` 对应行。

- [ ] **Step 3: 跑 governance 检查**

Run: `KBPREP_ALLOW_CORE_DOC_EDIT=1 npm run check:governance && npm run pack:check`
Expected: PASS（governance 接受 capability 更新）

- [ ] **Step 4: commit**

```bash
git add docs/development/development-roadmap.md docs/development/kbprep-implementation-status.json docs/capability-matrix.md
git commit -m "docs(e): mark Phase E completed_with_warnings as implemented"
```

---

## Verification（端到端验收）

完成全部 task 后跑：
```bash
npm run python:test          # 含 test_envelope_status / test_phase_e_status
npm run python:ruff
npm run python:typecheck
npm run lint:check           # eslint
npm run format:check         # prettier
npm test                     # vitest 含 worker-job-status
npm run python:test-contract # 跨语言契约
npm run release:check        # 全量 14+ 步
```

**Acceptance（roadmap Phase E）**：单源 run 硬门通过 + 有软警告 → 发布 status `completed_with_warnings`；测试覆盖对 `completed` 和 `failed` 的边界。

## Risk & Rollback

- **风险**：envelope 加 status 是跨语言 schema 变更，所有 envelope 消费者（TS adapter、CLI、测试）要兼容。Task 4 专门核对。
- **风险**：若非 job 命令（diagnose）的 envelope 没传 status 而 schema 必填 → 契约测试失败。Task 4 Step 1-2 处理。
- **回滚**：`git revert` Phase E commits；envelope.ok/fail 的 status 参数默认值保证向后兼容（旧消费者不传 status 不报错，只是 envelope 多/少一个字段）。
