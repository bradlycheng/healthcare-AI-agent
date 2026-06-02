# Professional Workflow Diagram Package

This folder contains a generic diagram package for documenting and reviewing a production system. It is not specific to the healthcare AI agent project.

## Files

- `pro-diagrams-package.html`  
  Browser-friendly standalone diagram package with no external JavaScript, CDN, image, or Mermaid dependency.

- `structural-diagrams.html`  
  Browser-friendly structural diagram package covering C4 structure, layering, modules, domain model, data stores, API surface, infrastructure topology, repository shape, ownership, and structural review checks.

- `audit-observability-map.html`  
  Browser-friendly audit and observability map covering event sources, sanitization, correlation, audit storage, alerting, dashboards, ownership, retention, and review checks.

- `architecture-decision-records.md`  
  Short guide explaining when to write ADRs, how to organize them, and how ADRs connect to diagrams.

- `adr-template.md`  
  Reusable Architecture Decision Record template.

## Diagram Set

The package includes:

1. Context diagram
2. Component diagram
3. Data flow diagram
4. Trust boundary diagram
5. Critical sequence diagram
6. State machine diagram
7. Authorization matrix
8. Control enforcement map
9. Threat model diagram
10. Audit and observability diagram
11. Deployment diagram
12. Resilience and failure diagram
13. CI/CD release flow
14. Data lifecycle and retention map
15. Incident response flow

## How To Use

Use this package as a template for new systems. For each system, replace the generic nodes with real services, owners, controls, risks, tests, and evidence.

The professional standard is not just having diagrams. The diagrams should connect to:

- owners
- security controls
- enforcement points
- logs and alerts
- tests
- risk decisions
- operational runbooks
