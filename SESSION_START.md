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

## Parallel Subagent And Worktree Protocol

任何并行子代理（codex worker 等）或 slice 实现必须遵守 `AGENTS.md` 的 "Parallel Subagent And Worktree Protocol"：

- 正规 worktree（`git worktree add .worktrees/<slice> -b codex/<slice> main`），禁止在项目外建野目录。
- 从最新 `main` 起步（`git fetch --all --prune` + rebase），base 不许落后 main 超过 5 commit。
- push 到命名分支，报告"完成"前用 `git ls-remote origin <branch>` 自验分支真实存在；禁止虚报"已推送"。
- `verified` 提升需三重门：真实样本/fixtures（禁 TTS/纯 mock/版权内容）+ 第二 agent 复核 + owner 批准；否则保持 `partial`。
- 不得以任何路径把项目 GPU torch 降级成 CPU；重依赖须先声明进 `python/pyproject.toml` 并验证与 mineru/lmdeploy 的 torch 约束不冲突。
- 换核心引擎属架构变更，须 owner 决策。

`npm run check:governance` 的 `subagent-worktree-discipline` check 强制其中可自动化的部分（worktree 位置、slice base 过期、未授权 `verified`/`implemented` 提升）。
