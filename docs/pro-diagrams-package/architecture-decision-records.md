# Architecture Decision Records

Architecture Decision Records, or ADRs, document important architecture decisions in a short, reviewable format.

Diagrams show structure and flow. ADRs explain why the structure and flow were chosen.

## When To Write An ADR

Write an ADR when a decision is:

- hard to reverse
- security-sensitive
- cross-cutting
- likely to affect multiple teams
- likely to affect data, identity, audit, deployment, or operations
- a meaningful tradeoff rather than an obvious implementation detail

## What ADRs Should Capture

Each ADR should capture:

- the context
- the chosen decision
- alternatives considered
- pros and cons
- consequences
- security and compliance impact
- validation plan
- rollout plan
- references to diagrams, tests, issues, and PRs

## Recommended Folder Layout

```text
docs/
  architecture/
    adr/
      0001-use-managed-database.md
      0002-adopt-service-owned-grants.md
      0003-use-event-driven-workers.md
      0004-encrypt-backups-with-kms.md
```

## Naming Convention

Use stable numbered files:

```text
0001-short-decision-title.md
0002-short-decision-title.md
0003-short-decision-title.md
```

Do not renumber ADRs after they are created.

## Status Values

Use one of:

- `Proposed`
- `Accepted`
- `Superseded`
- `Deprecated`

If a decision changes, do not rewrite history. Create a new ADR and mark the old one as superseded.

## How ADRs Connect To Diagrams

| Diagram Type | What It Shows | ADR Explains |
| --- | --- | --- |
| Context diagram | External systems and actors | Why those integrations exist |
| Component diagram | Major services | Why responsibilities are split that way |
| Trust boundary diagram | Trusted and untrusted zones | Why those boundaries and controls were chosen |
| State machine | Valid lifecycle states | Why certain transitions are allowed or denied |
| Deployment diagram | Runtime topology | Why this infrastructure shape was selected |
| Audit diagram | Evidence flow | Why logs contain certain fields and omit others |

## Professional Rule

An ADR should make future readers say:

> I understand why this was chosen, what alternatives were rejected, what risk we accepted, and how we proved the decision was implemented.

