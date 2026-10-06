"""Architecture-approved effect boundary for one governed Mission.

The source revision is intentionally absent here. Runtime binds it to the
current Repository Truth immediately before creating an EP request.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping


_MODES = frozenset({
    "READ_ONLY_ASSESSMENT", "DOCUMENTATION_ONLY", "ARCHITECTURE_DESIGN_ONLY",
    "BOUNDED_REPOSITORY_CHANGE",
})
_DELIVERY = {
    "READ_ONLY_ASSESSMENT": frozenset({"EVIDENCE_ONLY"}),
    "DOCUMENTATION_ONLY": frozenset({"GIT"}),
    "ARCHITECTURE_DESIGN_ONLY": frozenset({"EVIDENCE_ONLY", "GIT"}),
    "BOUNDED_REPOSITORY_CHANGE": frozenset({"GIT"}),
}
_RESERVED_PARTS = frozenset({
    ".git", ".github", ".codex", ".agents", ".engineering", ".ssh", ".aws",
    ".env", ".gitconfig", ".gitattributes", ".gitmodules", "agents.md",
    "secrets", "credentials",
})
_PATH = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*/?")


def _paths(values: tuple[str, ...], label: str) -> None:
    if not isinstance(values, tuple) or len(values) > 64 or len(values) != len(set(values)):
        raise ValueError(f"Mission effect {label} must be a bounded unique tuple")
    folded = set()
    for value in values:
        if (not isinstance(value, str) or not value or len(value) > 240
                or _PATH.fullmatch(value) is None):
            raise ValueError(f"Mission effect {label} contains an unsafe path")
        parts = value.rstrip("/").split("/")
        if any(part in {"", ".", ".."} or part.lower() in _RESERVED_PARTS
               or part.lower().startswith(".env.") or part.endswith(".")
               for part in parts):
            raise ValueError(f"Mission effect {label} contains a reserved path")
        key = value.lower()
        if key in folded:
            raise ValueError(f"Mission effect {label} contains a case alias")
        folded.add(key)


@dataclass(frozen=True)
class MissionEffectPolicy:
    """Explicit effect and output authority retained across approval and restart."""

    mode: str
    delivery: str
    read_paths: tuple[str, ...]
    write_paths: tuple[str, ...]
    contract_version: str = "1.0"

    def __post_init__(self) -> None:
        if (self.contract_version != "1.0" or self.mode not in _MODES
                or self.delivery not in _DELIVERY.get(self.mode, ())):
            raise ValueError("Mission effect mode or delivery is unsupported")
        _paths(self.read_paths, "read paths")
        _paths(self.write_paths, "write paths")
        if not self.read_paths:
            raise ValueError("Mission effect requires an explicit read scope")
        if self.delivery == "EVIDENCE_ONLY" and self.write_paths:
            raise ValueError("evidence-only Mission effect cannot authorize repository writes")
        if self.delivery == "GIT" and not self.write_paths:
            raise ValueError("Git-delivered Mission effect requires explicit write paths")
        if self.mode in {"DOCUMENTATION_ONLY", "ARCHITECTURE_DESIGN_ONLY"}:
            if any(not path.endswith("/") and not path.endswith((
                    ".md", ".txt", ".rst", ".adoc", ".mmd", ".puml"))
                   for path in self.write_paths):
                raise ValueError("document Mission effect cannot authorize non-document files")
        object.__setattr__(self, "read_paths", tuple(sorted(self.read_paths)))
        object.__setattr__(self, "write_paths", tuple(sorted(self.write_paths)))

    def to_dict(self) -> dict[str, Any]:
        return {"contract_version": self.contract_version, "mode": self.mode,
                "delivery": self.delivery, "read_paths": list(self.read_paths),
                "write_paths": list(self.write_paths)}

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "MissionEffectPolicy":
        if not isinstance(document, Mapping) or set(document) != {
                "contract_version", "mode", "delivery", "read_paths", "write_paths"}:
            raise ValueError("Mission effect policy schema is invalid")
        if not isinstance(document["read_paths"], list) or not isinstance(document["write_paths"], list):
            raise ValueError("Mission effect path lists are invalid")
        return cls(str(document["mode"]), str(document["delivery"]),
                   tuple(document["read_paths"]), tuple(document["write_paths"]),
                   str(document["contract_version"]))


@dataclass(frozen=True)
class EffectRequest:
    """One immutable, source-bound EP effect request under approved policy."""

    policy: MissionEffectPolicy
    source_revision: str
    criteria: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.policy, MissionEffectPolicy):
            raise ValueError("effect request lacks approved mode and scope")
        if not isinstance(self.source_revision, str) or re.fullmatch(
                r"[0-9a-f]{40}", self.source_revision) is None:
            raise ValueError("effect request source revision must be a full SHA")
        if not isinstance(self.criteria, tuple) or not 1 <= len(self.criteria) <= 16:
            raise ValueError("effect request requires bounded criteria")
        seen = set()
        for item in self.criteria:
            if (not isinstance(item, tuple) or len(item) != 2
                    or not isinstance(item[0], str) or not isinstance(item[1], str)
                    or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", item[0]) is None
                    or item[0] in seen or not 20 <= len(item[1].strip()) <= 1000):
                raise ValueError("effect request criterion identity or description is invalid")
            seen.add(item[0])

    def to_dict(self) -> dict[str, Any]:
        return {**self.policy.to_dict(), "source_revision": self.source_revision,
                "criteria": [{"id": key, "description": value} for key, value in self.criteria]}

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "EffectRequest":
        if not isinstance(document, Mapping) or set(document) != {
                "contract_version", "mode", "delivery", "read_paths", "write_paths",
                "source_revision", "criteria"}:
            raise ValueError("effect request schema is invalid")
        rows = document["criteria"]
        if not isinstance(rows, list) or any(not isinstance(row, Mapping)
                                             or set(row) != {"id", "description"} for row in rows):
            raise ValueError("effect request criteria schema is invalid")
        policy = MissionEffectPolicy.from_dict({key: document[key] for key in (
            "contract_version", "mode", "delivery", "read_paths", "write_paths")})
        return cls(policy, document["source_revision"],
                   tuple((row["id"], row["description"]) for row in rows))
