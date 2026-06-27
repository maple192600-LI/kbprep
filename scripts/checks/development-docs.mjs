import { existsSync, readFileSync } from "node:fs";

const requiredDocs = [
  "docs/development/README.md",
  "docs/development/00-current-state-and-gap.md",
  "docs/development/01-design-source-sync.md",
  "docs/development/02-canonical-ir-contract.md",
  "docs/development/03-deterministic-conversion-routing.md",
  "docs/development/04-conversion-quality-gate.md",
  "docs/development/05-document-type-classification.md",
  "docs/development/06-cleaning-policy-library.md",
  "docs/development/07-cleaning-unit-patch-clean-view.md",
  "docs/development/08-source-side-publish.md",
  "docs/development/09-feedback-rule-learning.md",
  "docs/development/10-batch-playlist-rerun.md",
  "docs/development/11-multimedia-youtube-optional.md",
  "docs/development/12-release-acceptance-and-governance.md",
];

const currentDocs = [
  "README.md",
  "AGENTS.md",
  "docs/kbprep-core-flow-design.md",
  "docs/kbprep-full-flowchart.html",
  "docs/kbprep-development-implementation-plan.md",
  "docs/quality-loop.md",
  "docs/standalone-cli.md",
  "docs/feedback-learning.md",
  "docs/known-issues.md",
  "docs/reports/kbprep-current-architecture.html",
  ...requiredDocs,
];

const stalePhrases = [
  { text: ["\u57fa\u7840", " Markdown"].join(""), wordBoundary: false },
  { text: "\u5206\u5757", wordBoundary: false },
  { text: ["chu", "nk"].join(""), wordBoundary: true },
  { text: "\u5c0f\u8d44\u6599", wordBoundary: false },
  { text: "\u5927\u8d44\u6599", wordBoundary: false },
  { text: "\u65e7\u9636\u6bb5", wordBoundary: false },
  { text: ["R", "AG"].join(""), wordBoundary: true },
];

const failures = [];

for (const file of requiredDocs) {
  if (!existsSync(file)) {
    failures.push({ file, reason: "required development document is missing" });
  }
}

const read = (file) => (existsSync(file) ? readFileSync(file, "utf8") : "");

requireIncludes("docs/development/README.md", read("docs/development/README.md"), [
  "Canonical IR",
  "Risk And Rollback Rule",
  "source-side Markdown",
  "kbprep-implementation-status.json",
]);

requireIncludes("docs/kbprep-development-implementation-plan.md", read("docs/kbprep-development-implementation-plan.md"), [
  "M1: Design Source Aligned",
  "M2: Canonical IR Contract",
  "M3: Policy Snapshot And Patch Cleanup",
  "M4: Source-Side Publication And Failure Safety",
  "M5: Feedback And Selective Rerun",
  "M6: Optional Source Expansion",
  "docs/development/12-release-acceptance-and-governance.md",
]);

requireIncludes(
  "docs/development/12-release-acceptance-and-governance.md",
  read("docs/development/12-release-acceptance-and-governance.md"),
  [
    "docs/flowchart/kbprep-flow.json",
    "## Conflict Handling Rule",
    "## One-Sentence Feedback Behavior",
    "## Required Checks",
    "## Release Acceptance",
  ],
);

requireIncludes("docs/feedback-learning.md", read("docs/feedback-learning.md"), [
  "## Plain-Language Behavior",
  "KBPrep must not silently turn one sentence into a permanent rule.",
  "then the user confirms",
  "confirm_rule_acceptance=true",
  "owner_confirmation_status",
]);

for (const file of requiredDocs.filter((file) => /^docs\/development\/\d{2}-/.test(file))) {
  const text = read(file);
  requireIncludes(file, text, ["## Flowchart Mapping", "## Risk And Rollback"]);
}

for (const file of currentDocs) {
  const text = read(file);
  for (const { text: phrase, wordBoundary } of stalePhrases) {
    const found = wordBoundary ? new RegExp(`\\b${phrase}\\b`).test(text) : text.includes(phrase);
    if (found) {
      failures.push({ file, reason: `stale architecture wording remains: ${phrase}` });
    }
  }
}

if (failures.length) {
  process.stderr.write(JSON.stringify({ ok: false, failures }, null, 2));
  process.stderr.write("\n");
  process.exit(1);
}

process.stdout.write(
  JSON.stringify(
    {
      ok: true,
      checkedDocs: requiredDocs.length,
      currentDocs: currentDocs.length,
    },
    null,
    2,
  ),
);
process.stdout.write("\n");

function requireIncludes(file, text, phrases) {
  for (const phrase of phrases) {
    if (!text.includes(phrase)) {
      failures.push({ file, reason: `missing required phrase: ${phrase}` });
    }
  }
}
