"""
Escrow buffer entry dataclass.

Represents a single entry in the science escrow buffer,
containing residual wavelet layers and associated metadata
as described in Section IV.D of the proposal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple

import numpy as np
from numpy.typing import NDArray


class RetentionClass(Enum):
    """Retention state for an escrow entry."""
    ESCROW = auto()       # In temporary escrow, subject to expiry
    LOCKED = auto()       # Guardrail says this layer is needed
    PROMOTED = auto()     # Retroactively promoted to protected storage
    UNLOCKED = auto()     # Safe to purge (guardrail approved removal)
    PURGED = auto()       # Already purged from buffer


@dataclass
class LayerInfo:
    """Metadata for a single residual layer within an escrow entry."""
    level: int                              # DWT detail level (1, 2, 3)
    byte_size: int                          # Size in bytes
    retention_class: RetentionClass = RetentionClass.ESCROW
    guardrail_safe: Optional[bool] = None   # Result of guardrail eval


@dataclass
class EscrowEntry:
    """
    A single entry in the escrow buffer.

    Each entry represents one frame's residual layers and all
    associated metadata needed for retention decisions.

    Attributes
    ----------
    frame_id : int
        Unique frame identifier.
    timestamp : float
        Acquisition time in seconds since epoch/start.
    layers : dict
        {level: (LH, HL, HH)} wavelet coefficient arrays.
    layer_info : dict
        {level: LayerInfo} metadata for each layer.
    source_count : int
        Number of detected sources in this frame.
    uncertainty_score : float
        OOD/uncertainty score from the estimator.
    retention_utility : float
        Combined retention utility U(fi).
    trigger_horizon_expiry : float
        Timestamp at which this entry expires from escrow.
    is_locked : bool
        If True, this entry cannot be purged (guardrail or promotion).
    is_promoted : bool
        If True, this entry has been promoted to protected storage.
    """
    frame_id: int
    timestamp: float
    layers: Dict[int, Tuple[NDArray, NDArray, NDArray]]
    layer_info: Dict[int, LayerInfo] = field(default_factory=dict)
    source_count: int = 0
    uncertainty_score: float = 0.0
    retention_utility: float = 0.0
    trigger_horizon_expiry: float = float("inf")
    is_locked: bool = False
    is_promoted: bool = False

    @property
    def total_bytes(self) -> int:
        """Total byte size of all stored layers."""
        total = 0
        for level, (lh, hl, hh) in self.layers.items():
            total += lh.nbytes + hl.nbytes + hh.nbytes
        return total

    @property
    def retention_class(self) -> RetentionClass:
        """Overall retention class for the entry."""
        if self.is_promoted:
            return RetentionClass.PROMOTED
        if self.is_locked:
            return RetentionClass.LOCKED
        # Check individual layers
        for info in self.layer_info.values():
            if info.retention_class == RetentionClass.LOCKED:
                return RetentionClass.LOCKED
        return RetentionClass.ESCROW

    def lock(self) -> None:
        """Lock this entry — prevent purging."""
        self.is_locked = True
        for info in self.layer_info.values():
            info.retention_class = RetentionClass.LOCKED

    def unlock_layer(self, level: int) -> None:
        """Mark a specific layer as safe to purge."""
        if level in self.layer_info:
            self.layer_info[level].retention_class = RetentionClass.UNLOCKED
            self.layer_info[level].guardrail_safe = True

    def promote(self) -> None:
        """Promote this entry to protected storage."""
        self.is_promoted = True
        self.is_locked = True
        for info in self.layer_info.values():
            info.retention_class = RetentionClass.PROMOTED

    def is_expired(self, current_time: float) -> bool:
        """Check if this entry has exceeded its trigger horizon."""
        return current_time > self.trigger_horizon_expiry

    def can_purge(self, current_time: float) -> bool:
        """
        Check if this entry can be purged.

        An entry can be purged only if:
        1. It is not locked or promoted
        2. All its layers are either UNLOCKED or ESCROW
        3. It has expired its trigger horizon
        """
        if self.is_locked or self.is_promoted:
            return False
        if not self.is_expired(current_time):
            return False
        return True

    def purgeable_layers(self) -> List[int]:
        """Return layer levels that can be individually purged."""
        result = []
        for level, info in self.layer_info.items():
            if info.retention_class == RetentionClass.UNLOCKED:
                result.append(level)
        return sorted(result, reverse=True)
