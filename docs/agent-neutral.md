# Agent-Independent Boundary

KBPrep is not an AI development agent adapter project. Its maintained surface is:

- Node CLI commands in `src/adapters/standalone/`
- Python worker commands in `python/kbprep_worker/cli.py`
- JSON envelopes returned by the worker bridge
- review packs, review patches, quality reports, and feedback rule proposals

Agent-host packaging is outside the KBPrep product boundary.

Allowed:

- document how an agent can call `kbprep-*` commands
- provide stable CLI examples
- provide a generic `review_pack` and patch protocol
- provide a generic feedback-to-rule proposal protocol
- accept caller-injected review backends only through the agent-independent patch protocol

Not allowed in the maintained core:

- importing host SDKs
- registering host-specific tools
- naming concrete agent hosts in runtime selection
- making a host plugin manifest part of the package contract
- testing package success through a host plugin validator

If a user wants KBPrep in a specific AI development agent, that calling environment should package the repository outside this maintained core.

## Evidence Checks

The package is agent-independent only when all are true:

- `package.json` has no host SDK dependency or host plugin manifest field
- `src/index.ts` exports the CLI/runtime contract, not an agent-host adapter
- CI builds and tests the CLI/package without agent-host plugin validation
- `node scripts/checks/agent-neutral-runtime.mjs` passes, proving runtime code does not name concrete agent hosts
- AI review tests use an injected fake backend and prove malformed patch operations are rejected before worker application
- README describes KBPrep as a CLI quality-loop tool
- package contents do not include agent-host install material as the primary path
