# ADR-0000: Decision Title

## Status

Proposed | Accepted | Superseded | Deprecated

## Date

YYYY-MM-DD

## Decision Owners

- Owner:
- Reviewers:
- Approvers:

## Context

Describe the situation, constraints, risks, and forces that make a decision necessary.

Include:

- business or product need
- technical constraints
- security/compliance constraints
- operational constraints
- known risks
- existing architecture

## Decision

State the decision clearly.

Example:

> We will use a server-owned grant model for every high-risk action. Client-provided permissions, LLM output, document metadata, and prior assistant messages will never create authorization.

## Alternatives Considered

| Alternative | Pros | Cons | Reason Not Chosen |
| --- | --- | --- | --- |
| Option A |  |  |  |
| Option B |  |  |  |
| Option C |  |  |  |

## Consequences

### Positive

- 

### Negative

- 

### Neutral / Tradeoffs

- 

## Security And Compliance Impact

Explain how this decision affects:

- authentication
- authorization
- data classification
- auditability
- privacy
- encryption/key management
- incident response
- abuse resistance

## Operational Impact

Explain how this decision affects:

- deployment
- monitoring
- alerts
- runbooks
- rollback
- performance
- reliability
- cost

## Validation Plan

List the tests, reviews, diagrams, and operational checks that prove the decision is implemented.

- Unit tests:
- Integration tests:
- Endpoint tests:
- Abuse/security tests:
- Audit/observability checks:
- Documentation updates:

## Rollout Plan

Describe how the decision will be shipped safely.

- Phase 1:
- Phase 2:
- Compatibility mode:
- Rollback:

## Follow-Up Decisions

List decisions this ADR creates or defers.

- 

## References

- Related diagrams:
- Related ADRs:
- Related issues/PRs:
- Related runbooks:

