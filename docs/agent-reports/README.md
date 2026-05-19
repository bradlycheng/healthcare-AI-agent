# Multi-Agent Report File Map

Agents do not live in Markdown files. The files are their written reports, checklists, and handoff notes. Lead Codex reads those reports and decides what becomes implementation work.

## Folder Diagram

```text
healthcare_ai_agent/
  docs/
    security-kernel-plan.md
      Final V2 target architecture.

    security-kernel-execution-plan.md
      Main rollout plan and phase gates.

    security-kernel-agent-sandbox-diagram.html
      Visual diagram of sandbox, agents, phases, and validation.

    agent-reports/
      README.md
        This file. Explains where agent reports sit.

      agent-report-folder-diagram.md
        Visual folder and handoff diagram for agent report files.

      agent-report-folder-diagram.html
        Browser-friendly visual version of the agent report folder diagram.

      phase-0-mapping/
        01-explorer-query-flow.md
          Explorer A report for /api/query, process_query, SQL, RAG, fallback paths, and LLM calls.

        02-explorer-hl7-messages.md
          Explorer B report for /oru/parse, /messages, FHIR, observations, and client-trusted fields.

        03-explorer-warden-guards.md
          Explorer C report for current Warden, schemas, tokenization, SQL validation, calculators, and audit JSONL.

        04-explorer-storage-audit-admin.md
          Explorer D report for DB setup, sessions, TTL, reset/admin, trace storage, and audit risks.

        00-lead-mapping-summary.md
          Lead Codex combined summary. This is the gate before implementation starts.

      phase-1-kernel-spine/
        10-worker-kernel-contracts.md
          Worker notes for security contracts, config, sessions, decisions, and audit helper.

        11-worker-llm-gateway.md
          Worker notes for LLM Gateway migration and direct-import tests.

        12-worker-warden-v2.md
          Worker notes for grant-aware tool/schema validation.

        13-worker-hl7-messages-governance.md
          Worker notes for parse sessions, /messages authority, TTL, status, and idempotency.

        19-lead-phase-1-integration.md
          Lead Codex integration notes and Phase 1 acceptance checklist.

      phase-2-guard-depth/
        20-worker-sqlguard.md
        21-worker-hl7guard.md
        22-worker-tokenguard.md
        23-worker-rag-calculator-guards.md
        29-lead-phase-2-integration.md

      review/
        90-reviewer-security-pass.md
          Independent bypass, PHI leak, fallback, metadata injection, stale-state, and missing-test review.
```

## How To Read The Structure

```text
Agent runs
  -> writes one focused Markdown report
  -> lead reads reports
  -> lead creates summary
  -> only then implementation starts
```

The phase folders are not permission boundaries. They are organization folders. The real safety boundary is the sandbox plus the project policy:

```text
Phase 0 agents are read-only.
Worker agents do not edit until mapping is reviewed.
Lead Codex integrates and verifies.
```

## Agent Report Rules

- Each agent gets one report file.
- Each report must name the files inspected.
- Each report must list risks, bypasses, and recommended tests.
- Explorer reports do not propose code patches as final authority.
- Worker reports must list changed files only after implementation is approved.
- Reviewer reports must prioritize findings over summaries.

## Minimal Report Template

```text
# Agent Report: <name>

## Assignment

## Files Inspected

## Current Flow

## Risks / Bypasses

## Recommended Implementation Notes

## Tests To Add

## Open Questions
```

## Current Status

The folder map is ready. The individual phase report files should be created only when those agents actually run, so the reports contain real findings instead of placeholder content.
