# Follow-Up Report: Intent Classifier To Grant Wiring

## Summary

`/api/query` now classifies user intent through the governed LLM gateway before invoking the agent. The classifier returns labels only; server code maps those labels into an `IntentGrant`.

## Implementation Summary

- Added `app/intent_classifier.py`.
- Classifier output is normalized to controlled intent/scope/risk labels.
- Unknown or malformed classifier output fails closed.
- Default-deny labels return a denied response before planning or tool execution.
- `/api/query` builds a grant from the normalized label and passes it into `run_agent_query`.
- Agent standard/deep entrypoints now accept an externally issued grant.

## Validation

```text
pytest tests/test_intent_classifier.py
5 passed
```

## Residual Work

- Add deterministic reference and scope-jump resolution before grant construction.
- Add broader live endpoint tests for classifier timeout/LLM failure.
- Tune classifier prompt labels if product terminology changes.
