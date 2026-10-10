"""Activation contract for the bounded StateAxis eviction bitmap."""

from __future__ import annotations

from dataclasses import dataclass

MOD_ID = "org.vllm-hust.stateaxis-incremental-eviction"


@dataclass(frozen=True, slots=True)
class IncrementalEvictionConfig:
    """Configuration accepted by the hash-bound Native Engine host."""

    bitmap_enabled: bool = True
    single_victim_only: bool = True
    max_index_states: int = 64
    fail_closed: bool = True

    def __post_init__(self) -> None:
        if (
            self.bitmap_enabled is not True
            or self.single_victim_only is not True
            or self.max_index_states != 64
            or self.fail_closed is not True
        ):
            raise ValueError(
                "incremental eviction requires the bounded 64-state, "
                "single-victim, fail-closed contract"
            )


def incremental_eviction() -> IncrementalEvictionConfig:
    """Return the default-off candidate's only admitted ON configuration."""

    return IncrementalEvictionConfig()


__all__ = ["MOD_ID", "IncrementalEvictionConfig", "incremental_eviction"]
