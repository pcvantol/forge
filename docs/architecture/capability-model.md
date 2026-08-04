# Forge Capability and Knowledge Source Model

Capability is a reusable engineering capability declaration with a stable ID,
name, description, metadata, and bootstrap status `declared`. Examples such as
Workspace Management, Documentation, Apple Platform, Technical Debt, and
Release Readiness can be represented without implementing any of them.

Knowledge Source is an external evidence provider. It records a stable ID,
name, source type, locator, and metadata. `read_only` is required and always
true. Forge may later consume evidence from sources such as an AI Platform
Engineering Knowledge Base, DJConnect, or a Technical Debt Engine, but this
model gives it no write, sync, or mutation authority.

Schemas: `capability.schema.json` and `knowledge-source.schema.json`.

The bootstrap declaration remains a legacy Foundation Model. The canonical
execution-time registry is the [Capability Delegation Framework](capability-delegation-framework.md),
with schema `capability-registry-1.0.schema.json`.
