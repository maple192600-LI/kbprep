// Enforces the "Parallel Subagent And Worktree Protocol" in AGENTS.md.
//
// This check exists because an uncontrolled parallel subagent once produced a
// "shadow branch": a dangling unpushed commit that silently downgraded the
// project torch to CPU, declared a false `verified` capability status, and was
// reported as "pushed" without ever reaching the remote. The three checks below
// catch the observable consequences of that pattern so it cannot recur silently.
//
// Run by `scripts/check-governance.mjs` (therefor `check:governance`,
// `check:development-docs`, `pack:check`). Exits 1 with a JSON failure list on
// violation, 0 with a JSON ok payload otherwise.
//
// Scope (intentionally automatable parts of the protocol):
//   §1  registered worktrees must live under .worktrees/ (no wild directories)
//   §2  a `codex/*` slice branch must not lag `main` by more than 5 commits
//   §4  promoting a capability to verified/implemented requires the owner marker
//       KBPREP_ALLOW_STATUS_PROMOTION=1 (forces conscious owner action + second
//       agent review per the protocol)
import { spawnSync } from "node:child_process";
import path from "node:path";

const repoRoot = path.resolve(process.argv[2] ?? ".");
const MAX_BEHIND = 5;
const failures = [];

// §1 — every registered worktree except the main worktree must be under .worktrees/.
// Judge by absolute path (git worktree list prints absolute paths) and treat the
// first listed worktree as the main worktree, so the verdict is identical whether
// this script runs from the main repo or from inside a slice worktree. A
// cwd-relative check wrongly flags the main worktree when run from a slice worktree.
const worktreeLines = lines(git(["worktree", "list"]));
const mainWorktreePath = worktreeLines.length ? (worktreeLines[0].match(/^(\S+)/) || [])[1] : null;
for (const line of worktreeLines) {
  const wtPath = (line.match(/^(\S+)/) || [])[1];
  if (!wtPath) continue;
  const isMain = Boolean(mainWorktreePath) && wtPath === mainWorktreePath;
  const normalized = wtPath.replace(/\\/g, "/") + "/";
  const underWorktrees = normalized.includes("/.worktrees/");
  if (!isMain && !underWorktrees) {
    failures.push({
      check: "worktree-location",
      worktree: wtPath,
      reason:
        "slice worktrees must live under .worktrees/ (Parallel Subagent And Worktree Protocol §1); use `git worktree add .worktrees/<slice> -b codex/<slice> main`",
    });
  }
}

// §2 — a codex/* slice branch must not lag main by more than MAX_BEHIND commits.
const branch = git(["rev-parse", "--abbrev-ref", "HEAD"]).trim();
if (branch.startsWith("codex/")) {
  const base = git(["merge-base", branch, "main"]).trim();
  if (base) {
    const behind = parseCount(git(["rev-list", "--count", `${base}..main`]));
    if (Number.isFinite(behind) && behind > MAX_BEHIND) {
      failures.push({
        check: "slice-base-staleness",
        branch,
        behind,
        limit: MAX_BEHIND,
        reason: `slice base is ${behind} commits behind main (limit ${MAX_BEHIND}); run \`git fetch --all --prune\` then rebase onto origin/main (Protocol §2)`,
      });
    }
  }
}

// §4 — capability status promotion to verified/implemented needs the owner marker.
if (process.env.KBPREP_ALLOW_STATUS_PROMOTION !== "1") {
  const diff = git(["diff", "main", "--", "docs/development/kbprep-implementation-status.json", "docs/capability-matrix.md"]);
  const promotions = [];
  for (const line of diff.split(/\r?\n/)) {
    if (!line.startsWith("+") || line.startsWith("+++")) continue;
    if (/"status"\s*:\s*"(verified|implemented)"/.test(line) || /\|\s*(verified|implemented)\s*\|/.test(line)) {
      promotions.push(line.slice(1).trim());
    }
  }
  if (promotions.length) {
    failures.push({
      check: "status-promotion-gate",
      promotions,
      reason:
        "promoting a capability to verified/implemented requires owner marker KBPREP_ALLOW_STATUS_PROMOTION=1 plus a second independent agent review (Protocol §4); keep the capability partial until evidence is real and reviewed",
    });
  }
}

if (failures.length) {
  process.stderr.write(JSON.stringify({ ok: false, failures }, null, 2));
  process.stderr.write("\n");
  process.exit(1);
}
process.stdout.write(JSON.stringify({ ok: true, check: "subagent-worktree-discipline", branch: branch || null }, null, 2));
process.stdout.write("\n");

function git(args) {
  const result = spawnSync("git", args, { cwd: repoRoot, encoding: "utf8" });
  return result.status === 0 ? result.stdout : "";
}

function lines(text) {
  return text.split(/\r?\n/).filter(Boolean);
}

function parseCount(text) {
  const n = parseInt((text || "").trim(), 10);
  return Number.isNaN(n) ? Number.NaN : n;
}
