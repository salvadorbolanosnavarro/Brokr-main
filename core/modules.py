"""Declarative contract for Broquer modules.

Future modules describe themselves once. Platform code consumes the same
metadata for backend registration, navigation, permissions, observability, and
documentation instead of maintaining parallel lists.

Visual design is intentionally not configurable per module. Every application
module inherits Broquer's canonical design system; modules may not select or
fork their own theme through this contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable, Optional


_MODULE_KEY = re.compile(r"^[a-z][a-z0-9-]*$")


@dataclass(frozen=True)
class ModuleDefinition:
    key: str
    name: str
    description: str
    route_prefix: str = ""
    navigation_path: Optional[str] = None
    navigation_group: Optional[str] = None
    icon: Optional[str] = None
    permissions: tuple[str, ...] = field(default_factory=tuple)
    enabled: bool = True

    def __post_init__(self) -> None:
        if not _MODULE_KEY.fullmatch(self.key):
            raise ValueError(
                "Module key must match ^[a-z][a-z0-9-]*$"
            )
        if not self.name.strip():
            raise ValueError("Module name must not be empty")
        if not self.description.strip():
            raise ValueError("Module description must not be empty")
        if self.route_prefix and not self.route_prefix.startswith("/"):
            raise ValueError("route_prefix must start with '/' when provided")
        if self.navigation_path and not self.navigation_path.startswith("/"):
            raise ValueError("navigation_path must start with '/' when provided")
        if len(set(self.permissions)) != len(self.permissions):
            raise ValueError("Module permissions must not contain duplicates")


class ModuleRegistry:
    """Registry that rejects ambiguous module metadata at startup."""

    def __init__(self) -> None:
        self._definitions: dict[str, ModuleDefinition] = {}

    def register(self, definition: ModuleDefinition) -> None:
        if definition.key in self._definitions:
            raise ValueError(f"Duplicate module key: {definition.key}")
        self._definitions[definition.key] = definition

    def get(self, key: str) -> Optional[ModuleDefinition]:
        return self._definitions.get(key)

    def all(self) -> tuple[ModuleDefinition, ...]:
        return tuple(self._definitions.values())

    def enabled(self) -> tuple[ModuleDefinition, ...]:
        return tuple(m for m in self._definitions.values() if m.enabled)

    def register_many(self, definitions: Iterable[ModuleDefinition]) -> None:
        for definition in definitions:
            self.register(definition)


registry = ModuleRegistry()
