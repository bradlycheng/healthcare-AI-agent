# Agent Report Folder Diagram

Agents do the work in Codex. Markdown files are where their findings and handoffs are saved.

## Folder Placement

```text
healthcare_ai_agent/
|
+-- docs/
    |
    +-- security-kernel-plan.md
    |   Final V2 target architecture
    |
    +-- security-kernel-execution-plan.md
    |   Main rollout plan
    |
    +-- security-kernel-agent-sandbox-diagram.html
    |   Visual sandbox + agent execution diagram
    |
    +-- agent-reports/
        |
        +-- README.md
        |   Explains the report structure
        |
        +-- agent-report-folder-diagram.md
        |   This file
        |
        +-- phase-0-mapping/
        |   |
        |   +-- 01-explorer-query-flow.md
        |   |   Explorer A writes findings here
        |   |
        |   +-- 02-explorer-hl7-messages.md
        |   |   Explorer B writes findings here
        |   |
        |   +-- 03-explorer-warden-guards.md
        |   |   Explorer C writes findings here
        |   |
        |   +-- 04-explorer-storage-audit-admin.md
        |   |   Explorer D writes findings here
        |   |
        |   +-- 00-lead-mapping-summary.md
        |       Lead Codex combines reports here
        |
        +-- phase-1-kernel-spine/
        |   |
        |   +-- 10-worker-kernel-contracts.md
        |   +-- 11-worker-llm-gateway.md
        |   +-- 12-worker-warden-v2.md
        |   +-- 13-worker-hl7-messages-governance.md
        |   +-- 19-lead-phase-1-integration.md
        |
        +-- phase-2-guard-depth/
        |   |
        |   +-- 20-worker-sqlguard.md
        |   +-- 21-worker-hl7guard.md
        |   +-- 22-worker-tokenguard.md
        |   +-- 23-worker-rag-calculator-guards.md
        |   +-- 29-lead-phase-2-integration.md
        |
        +-- review/
            |
            +-- 90-reviewer-security-pass.md
```

## Phase 0 Mapping Flow

```text
                           +---------------------------+
                           |        Lead Codex         |
                           | owns architecture + merge |
                           +-------------+-------------+
                                         |
                                         | assigns read-only mapping
                                         v
+------------------------+   +------------------------+   +------------------------+   +------------------------+
| Explorer A             |   | Explorer B             |   | Explorer C             |   | Explorer D             |
| Query Flow             |   | HL7 + Messages         |   | Warden + Guards        |   | Storage + Audit/Admin  |
+-----------+------------+   +-----------+------------+   +-----------+------------+   +-----------+------------+
            |                            |                            |                            |
            v                            v                            v                            v
+------------------------+   +------------------------+   +------------------------+   +------------------------+
| 01-explorer-query-     |   | 02-explorer-hl7-      |   | 03-explorer-warden-   |   | 04-explorer-storage-  |
| flow.md                |   | messages.md            |   | guards.md              |   | audit-admin.md         |
+-----------+------------+   +-----------+------------+   +-----------+------------+   +-----------+------------+
            |                            |                            |                            |
            +----------------------------+-------------+--------------+----------------------------+
                                                       |
                                                       v
                                      +----------------+----------------+
                                      | 00-lead-mapping-summary.md      |
                                      | combined bypass + test checklist |
                                      +----------------+----------------+
                                                       |
                                                       v
                                      Phase 1 implementation may start
```

## Phase 1 Worker Flow

```text
Phase 0 summary approved
        |
        v
+----------------------------+
| Lead Codex                 |
| creates Phase 1 work plan  |
+-------------+--------------+
              |
              | assigns narrow worker slices
              v
+-------------------+  +-------------------+  +-------------------+  +------------------------+
| Worker 1          |  | Worker 2          |  | Worker 3          |  | Worker 4               |
| Kernel Contracts  |  | LLM Gateway       |  | Warden v2         |  | HL7 / Messages Gov     |
+---------+---------+  +---------+---------+  +---------+---------+  +-----------+------------+
          |                      |                      |                        |
          v                      v                      v                        v
+-------------------+  +-------------------+  +-------------------+  +------------------------+
| 10-worker-kernel- |  | 11-worker-llm-    |  | 12-worker-warden-|  | 13-worker-hl7-        |
| contracts.md      |  | gateway.md        |  | v2.md             |  | messages-governance.md |
+---------+---------+  +---------+---------+  +---------+---------+  +-----------+------------+
          |                      |                      |                        |
          +----------------------+-----------+----------+------------------------+
                                             |
                                             v
                              +--------------+---------------+
                              | 19-lead-phase-1-integration.md |
                              | integration + acceptance gate   |
                              +--------------+---------------+
                                             |
                                             v
                                  Reviewer security pass
```

## Where Verification Sits

```text
Agent report
    |
    v
Lead review
    |
    v
Phase summary
    |
    v
Tests / validation gate
    |
    v
Reviewer security pass
    |
    v
Next phase
```

## Important Rule

```text
Agents are not stored in the repo.
Reports are stored in the repo.
Lead Codex decides what reports become implementation.
```
