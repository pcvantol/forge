# Runtime Evidence Architecture Authoring Report 001

The Runtime Evidence query layer establishes `.forge/runtime.db` as Forge's
canonical operational reporting source. It keeps the three ownership domains
separate: Repository Truth supplies architecture, Forge supplies runtime state,
and Engineering Platform supplies execution evidence. Bootstrap and Mission
Qualification consume runtime projections and retain host artefacts only as
immutable Execution References.
