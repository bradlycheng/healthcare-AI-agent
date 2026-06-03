# Skill: run-hardening-slice

## When to use

Invoke this skill when you want to implement one hardening slice from the baseline
security plan. Type `/run-hardening-slice` or describe a task that matches
"implement a hardening slice", "run the next hardening slice", etc.

## What this skill does

Guides the lead session through the correct sequence for one hardening slice:
read plan -> confirm scope -> dispatch narrow-worker -> require reviewer gate.

It does not implement code itself. It orchestrates the existing subagents.

---

## Step 1 -- Read the plan

Read docs/agent-reports/baseline-audit/00-lead-hardening-plan.md.

Ask the user which slice to run if not specified (e.g. "Slice 2", "Slice 3").
Find that slice's section in the plan.

---

## Step 2 -- Confirm scope before dispatching

Before dispatching the narrow-worker, confirm with the user:

1. **File ownership** — list every file the worker may edit. Ask the user to confirm.
2. **Files NOT to touch** — list the explicit exclusions from the plan.
3. **Sign-off condition** — state it plainly. Example: "Patient name must not appear
   in the string passed to embed_text()."
4. **Tests required** — list the test names from the plan.

Do not proceed to Step 3 until the user confirms scope.

---

## Step 3 -- Dispatch narrow-worker

Use the narrow-worker subagent. Pass:
- The exact file ownership list (confirmed in Step 2)
- The exact files NOT to touch
- The implementation guidance from the plan for this slice
- The test names to add
- The sign-off condition
- Requirement to write a worker report (numbered correctly: 10/20/30 = worker,
  11/21/31 = reviewer first pass, 12/22/32 = rework pass if needed)
- Requirement to write a prompt-ledger entry

Wait for the worker to return. Do not proceed until the worker reports test results.

---

## Step 4 -- Verify worker output

After the worker returns, check:

- [ ] All specified tests pass
- [ ] No regression in the slice-specific and relevant regression tests named in the plan; run full suite when feasible
- [ ] Worker report written to docs/agent-reports/baseline-audit/
- [ ] Prompt-ledger entry written and prepended to docs/agent-reports/prompt-ledger.md
- [ ] Any deferred items documented with clear rationale

If any check fails, tell the user and do not proceed to the reviewer.

---

## Step 5 -- Require reviewer gate

Dispatch the security-reviewer subagent (read-only: Read, Grep, Glob; model: opus).

Pass the files changed by the worker plus the worker report and hardening plan section.
Tell the reviewer to check:
- The specific security objective for this slice
- Test quality (assertions test the right thing, not just no exception)
- Scope discipline (only ownership files changed)
- Deferred items documented

Write the reviewer report to the correct numbered file.
Write the reviewer ledger entry.

Do not declare the slice done until the reviewer returns MERGEABLE.

---

## Step 6 -- Handle NOT MERGEABLE

If the reviewer returns NOT MERGEABLE:
- List the blocking findings (Critical items only)
- Dispatch narrow-worker again with only the blocking findings as the assignment
- Re-run the reviewer after the rework
- Acceptable deferrals (Warnings) do not block merge if documented

---

## Governance rules (always enforce)

- The narrow-worker must not touch security files (warden.py, llm_gateway.py, *_guard.py)
  unless those files are explicitly listed in the slice's file ownership
- The reviewer is always read-only -- it must never write code
- Every subagent session must produce a prompt-ledger entry
- docs/agent-reports/** must never be indexed into runtime RAG
- Do not commit until the reviewer signs off MERGEABLE
