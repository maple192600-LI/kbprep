# SESSION_START

本文件是任意开发 agent 进入 KBPrep 项目时的最短启动入口。

## Must Read

1. `AGENTS.md`
2. `README.md`
3. `docs/development/development-roadmap.md`
4. `docs/development/kbprep-implementation-status.json`
5. 当前任务涉及的 `docs/development/*.md`

## Current-State Preflight

先运行：

```powershell
git status --short --branch
```

如果不是干净工作树，先识别哪些改动属于当前任务，不能回滚用户或其他代理的改动。

## Unified Verification

默认快速验收：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-kbprep.ps1
```

完整验收：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-kbprep.ps1 -Full
```

等价关系：

- 默认模式运行 `npm run dev:check`
- `-Full` 运行 `npm run dev:full-check`

## Do Not

- 不把 `design_only` 或 `partial` 能力写成已完成。
- 不把测试样本通过等同于真实 PDF/真实 Vault 路径通过。
- 不提交 `dist/`、`coverage/`、缓存、临时输出或运行历史。
