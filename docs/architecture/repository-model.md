# Forge Repository and Catalog Model

A Repository is an engineering-truth reference: stable ID, display name, Git
provider/reference, local path, and descriptive metadata. It deliberately
does not contain a `role` field.

Repository role belongs only to Repository Catalog. A catalog has a stable ID
and maps repository IDs into four roles:

- `canonical`: exactly one repository; the primary product source of truth.
- `supporting`: product-supporting repositories.
- `documentation`: documentation repositories.
- `capability`: future capability repositories.

The catalog must have exactly one canonical ID, and the Python model also
rejects a repository assigned to more than one role. JSON Schema enforces the
required one-item canonical slot and unique IDs within each role; full
cross-role identity validation is the responsibility of the local model
validator until a composite-document schema is introduced.

Schemas: `repository.schema.json` and `repository-catalog.schema.json`.
