# Changelog

## 0.5.2

- Corrected audit closeout overclaims from 0.5.1 with rule-backed text quality and retention signals.
- Made garbled-text classification Unicode-aware so valid accented Latin text is preserved.
- Split worker `E_/W_` codes from runtime `KBPREP_*` codes and added contract tests for both layers.

## 0.5.1

- Renamed the npm package identity to `kbprep` and kept the maintained contract on the agent-independent CLI package.
- Added a generic AI review backend interface for caller-injected review hosts.
- Hardened CTA rules, worker stdin handling, AI review patch parsing, error-code naming, and tracked `dist/` checks.
- Added standalone CLI and known-issues documentation.

## 0.5.0

- Added a host-agnostic Node runtime layer for the Python worker.
- Removed host-specific tool registration from the maintained runtime surface.
- Added standalone CLI entry points: `kbprep-preflight`, `kbprep-analyze`, `kbprep-prepare`, `kbprep-apply-review`, `kbprep-cleanup`, and `kbprep-batch`.
- Kept host dependencies outside the CLI package contract.
- Added agent-independent boundary and risk-tag documentation.

## 0.4.4

- Added curated Obsidian knowledge-base output.
- Strengthened marketing-wrapper cleanup and audit outputs.
- Preserved source-side final Markdown and cleanup lifecycle behavior.
