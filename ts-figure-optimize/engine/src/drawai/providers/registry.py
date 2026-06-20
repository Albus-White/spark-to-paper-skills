from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ProviderEntry:
    name: str
    protocol: str
    provider: Any
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ProviderLookupError(LookupError):
    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name
        super().__init__(f"provider not registered: {provider_name}")


class ProviderRegistry:
    def __init__(self, entries: Iterable[ProviderEntry] = ()) -> None:
        self._entries: dict[str, ProviderEntry] = {}
        for entry in entries:
            self.register(entry)

    def register(self, entry: ProviderEntry) -> None:
        if entry.name in self._entries:
            raise ValueError(f"duplicate provider name: {entry.name}")
        self._entries[entry.name] = entry

    def require(self, name: str) -> Any:
        return self.require_entry(name).provider

    def require_entry(self, name: str) -> ProviderEntry:
        try:
            return self._entries[name]
        except KeyError as exc:
            raise ProviderLookupError(name) from exc

    def names_for_protocol(self, protocol: str) -> list[str]:
        return sorted(
            entry.name
            for entry in self._entries.values()
            if entry.protocol == protocol
        )

    def entries_for_protocol(self, protocol: str) -> list[ProviderEntry]:
        return [
            self._entries[name]
            for name in self.names_for_protocol(protocol)
        ]

    def as_context_providers(self) -> dict[str, Any]:
        return {
            name: entry.provider
            for name, entry in sorted(self._entries.items())
        }
