# Forge Workspace Readiness

## Purpose

Workspace Readiness is the generic Forge capability for assessing whether a
Workspace is prepared to enter a declared execution profile. It is distinct
from phase completion: readiness establishes whether work may begin in a
profile, while phase completion assesses whether a bounded phase has met its
declared criteria.

This document defines architecture only. It introduces no readiness runtime,
provider, queue, repository operation, or execution behavior.

## Assessment model

A readiness profile declares its checks, required evidence, and assessment
rules. A readiness assessment records the outcome against those declared
checks. Repository evidence remains authoritative for any check concerning
repository reality.

Future capabilities may add checks only by declaring their responsibility,
evidence needs, and the profiles to which they apply. They must not replace
the common readiness assessment model or infer readiness from runtime names.

## Initial profiles

| Profile | Purpose | Current architectural boundary |
| --- | --- | --- |
| Genesis Readiness | Bootstrap execution against a local, independent Forge repository. | Requires a bounded local transaction and objective local Git evidence; no upstream remote or pull request is required. |
| Managed Readiness | Governed execution where repository and human-governance checks are managed explicitly. | Defines the future profile boundary only; its checks and runtime remain separately governed work. |

Genesis Mode is an execution profile for bootstrap, not a permanent dependency
on Engineering Platform 1.5. Managed Readiness is not an implementation claim.

## Relationship to future work

Readiness can receive contributions from future capabilities such as durable
Engineering Intent validation, Runtime Provider contracts, governance, or
evidence capture. Each contribution must remain declarative until separately
authorized implementation establishes its runtime boundary.
