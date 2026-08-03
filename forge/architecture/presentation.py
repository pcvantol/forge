"""Minimal deterministic Architecture Workspace detail view."""

from __future__ import annotations

from typing import Any

from forge.models.architecture_mission import ArchitectureMission


def render_architecture_mission(mission: ArchitectureMission) -> dict[str, Any]:
    return {**mission.to_dict(), "advisory_available": True, "execution_available": False, "repository_mutation_available": False}
