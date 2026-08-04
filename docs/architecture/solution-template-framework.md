# Forge Solution Template Framework

## Purpose

Solution Templates are reusable, versioned Portfolio assets that help a
Business Owner start a software initiative from a recognised archetype rather
than an empty Mission Candidate. The built-in Solution Catalogue includes Web
Application, Mobile Application, REST API, CRM, ERP, Dashboard, Knowledge
Base, AI Assistant, IoT Platform, Media Platform, E-commerce, Internal Tool,
and Automation Platform. Additional immutable templates can be supplied to the
catalogue.

Each template declares purpose, users, stakeholders, objectives, capabilities,
recommended Candidate definitions, architecture patterns, disciplines, risks,
compliance considerations, and phases. A `identifier@version` reference is
recorded on every draft, so later catalogue evolution does not rewrite its
origin.

## Lifecycle and determinism

```text
Solution Template → Business Advisor → Mission Candidate → Business Review
  → Architecture Review → Mission → Engineering
```

The pure generator canonicalises the template reference, declared Business
Advisor answers, candidate key, and declared Repository Context before deriving
a stable candidate identifier. Identical inputs therefore produce identical,
editable drafts. Templates do not access a provider, read a repository, create
a Mission, approve a Candidate, or execute work.

Template-originated Candidates enter `business_review` and intentionally have
no Architecture Review or Mission Recommendation reference: neither upstream
artefact exists yet. The template provenance replaces neither review. Business
approval remains necessary before the [Architecture Workspace](architecture-workspace.md)
may admit a Candidate.

## Advisor, architecture, and Portfolio relationship

The [Business Workspace](business-workspace.md) exposes the canonical Advisor
questions: users, customers, internal/external delivery, cloud/on-premise,
mobile, offline support, compliance, scale, and existing systems. Answers are
advisory and incomplete answers remain visible for the Business Owner to
decide. Required-discipline gaps are declared against available disciplines;
Forge never fabricates expertise.

Architecture patterns, technology considerations, dependencies, and discipline
recommendations are advisory context for Architecture Workspace review. They
do not override that workspace's authority. Templates are Portfolio assets;
[Mission Recommendations](mission-recommendation-engine.md) may reference a
template, but neither mechanism can auto-approve or auto-execute a Mission.
Governance Profiles retain their existing separate Business and Architecture
approval stages.
