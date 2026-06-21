# AI Review External Command

KBPrep core is agent-independent. It can call a generic external review command, but Ollama, OpenAI-compatible, Anthropic, or other provider clients belong outside KBPrep core.

Use `review_mode: "shadow"` for a new model rollout. Shadow mode validates model patch output and writes `review_suggestions.json`, but it does not call `apply_review` and does not change final Markdown.

## Stdin

The command receives one JSON object on stdin:

```json
{
  "sessionKey": "kbprep-review:<tool-call>:<batch>:<attempt>",
  "message": "Review this kbprep review_pack.json batch...",
  "systemPrompt": "You are a conservative knowledge-base cleaning reviewer.",
  "provider": "optional-provider-name",
  "model": "optional-model-name",
  "timeoutMs": 60000,
  "idempotencyKey": "<tool-call>:<batch>:<attempt>"
}
```

`message` contains the bounded `review_pack.json` batch. It includes candidate block text and a small `policy_context`, but not global neighboring text by default.

## Stdout

The command must write JSON with a `messages` array:

```json
{
  "messages": [
    "[{\"op\":\"replace\",\"path\":\"/blocks/b1/status\",\"value\":\"review\"}]"
  ],
  "warning": "optional warning text"
}
```

The latest JSON array found in `messages` is parsed as RFC 6902 JSON Patch. KBPrep accepts only:

- `/blocks/{block_id}/status`
- `/blocks/{block_id}/risk_tags`
- `/blocks/{block_id}/reason`
- `/blocks/{block_id}/confidence`

It rejects attempts to rewrite source text, remove blocks, or use unknown fields. Python `apply_review` still performs the final safety check before any apply-mode update is published.

## Wrapper Pattern

```js
let input = "";
process.stdin.on("data", (chunk) => {
  input += chunk;
});
process.stdin.on("end", async () => {
  const payload = JSON.parse(input);
  const patch = await callYourModel(payload.systemPrompt, payload.message);
  process.stdout.write(JSON.stringify({ messages: [JSON.stringify(patch)] }));
});
```

## Manual Acceptance

1. Run prepare with review artifacts:

   ```bash
   kbprep-prepare --input ./source.md --output ./.kbprep/source --mode rules_plus_review_pack
   ```

2. Run the host integration with `mode: "ai_review"` and `review_mode: "shadow"`.

3. Inspect `runs/<run-id>/review_suggestions.json`.

4. Confirm no final Markdown changed during shadow mode.

5. Switch to `review_mode: "apply"` only after the same representative sources produce safe suggestions.
