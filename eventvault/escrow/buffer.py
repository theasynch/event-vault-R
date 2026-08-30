"""
Circular escrow buffer for EventVault-R.

Implements the finite circular buffer described in Section IV.D
of the proposal. The buffer holds residual wavelet layers and
guarantees zero uncontrolled data loss: locked entries are
never overwritten.

Key design principles:
- Locked/promoted entries are protected from eviction
- Expired unlocked entries are purged first
- Memory pressure tracking for the resource controller
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

import numpy as np
from numpy.typing import NDArray

from eventvault.escrow.entry import EscrowEntry, LayerInfo, RetentionClass

logger = logging.getLogger(__name__)


class EscrowBufferOverflowError(Exception):
    """Raised when buffer is full and all entries are locked."""
    pass


class EscrowBuffer:
    """
    Finite circular escrow buffer.

    Stores residual wavelet layers for frames that have not yet
    been definitively classified. Implements FIFO eviction with
    protection for locked/promoted entries.

    Parameters
    ----------
    capacity : int
        Maximum number of frame entries in the buffer.
    trigger_horizon_seconds : float
        Default expiry time for new entries.
    """

    def __init__(
        self,
        capacity: int = 100,
        trigger_horizon_seconds: float = 1800.0,
    ):
        self.capacity = capacity
        self.trigger_horizon_seconds = trigger_horizon_seconds

        # OrderedDict preserves insertion order for FIFO
        self._entries: OrderedDict[int, EscrowEntry] = OrderedDict()

        # Statistics
        self._total_pushed = 0
        self._total_purged = 0
        self._total_promoted = 0
        self._uncontrolled_losses = 0

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def push(
        self,
        frame_id: int,
        timestamp: float,
        residual_layers: Dict[int, Tuple[NDArray, NDArray, NDArray]],
        uncertainty_score: float = 0.0,
        source_count: int = 0,
        horizon_override: Optional[float] = None,
    ) -> EscrowEntry:
        """
        Push a new frame's residual layers into the escrow buffer.

        If the buffer is at capacity, evicts the oldest unlocked
        expired entry. If all entries are locked, raises an error.

        Parameters
        ----------
        frame_id : int
            Unique frame identifier.
        timestamp : float
            Acquisition timestamp.
        residual_layers : dict
            {level: (LH, HL, HH)} wavelet coefficient arrays.
        uncertainty_score : float
            OOD/uncertainty score for this frame.
        source_count : int
            Number of detected sources.
        horizon_override : float, optional
            Custom trigger horizon for this entry.

        Returns
        -------
        EscrowEntry that was created.

        Raises
        ------
        EscrowBufferOverflowError
            If buffer is full and no entries can be evicted.
        """
        # Check if we need to evict
        if len(self._entries) >= self.capacity:
            evicted = self._evict_one(timestamp)
            if not evicted:
                self._uncontrolled_losses += 1
                raise EscrowBufferOverflowError(
                    f"Buffer full ({self.capacity} entries), "
                    "all entries are locked or unexpired. "
                    "Cannot push without data loss."
                )

        # Build layer info
        horizon = horizon_override or self.trigger_horizon_seconds
        layer_info = {}
        for level, (lh, hl, hh) in residual_layers.items():
            byte_size = lh.nbytes + hl.nbytes + hh.nbytes
            layer_info[level] = LayerInfo(
                level=level,
                byte_size=byte_size,
                retention_class=RetentionClass.ESCROW,
            )

        entry = EscrowEntry(
            frame_id=frame_id,
            timestamp=timestamp,
            layers=residual_layers,
            layer_info=layer_info,
            uncertainty_score=uncertainty_score,
            source_count=source_count,
            trigger_horizon_expiry=timestamp + horizon,
        )

        self._entries[frame_id] = entry
        self._total_pushed += 1

        logger.debug(
            "Pushed frame %d to escrow (buffer: %d/%d)",
            frame_id, len(self._entries), self.capacity,
        )

        return entry

    def get(self, frame_id: int) -> Optional[EscrowEntry]:
        """Retrieve an entry by frame ID."""
        return self._entries.get(frame_id)

    def lock(self, frame_id: int) -> bool:
        """Lock an entry to prevent purging."""
        entry = self._entries.get(frame_id)
        if entry is None:
            return False
        entry.lock()
        logger.debug("Locked frame %d in escrow", frame_id)
        return True

    def unlock_layer(self, frame_id: int, layer: int) -> bool:
        """Mark a specific layer as safe for purging."""
        entry = self._entries.get(frame_id)
        if entry is None:
            return False
        entry.unlock_layer(layer)
        return True

    def promote(self, frame_id: int) -> Optional[EscrowEntry]:
        """
        Promote an entry to protected storage.

        Returns the promoted entry (which remains in the buffer
        but is now protected and flagged for priority downlink).
        """
        entry = self._entries.get(frame_id)
        if entry is None:
            logger.warning("Cannot promote frame %d: not in escrow", frame_id)
            return None

        entry.promote()
        self._total_promoted += 1
        logger.info("Promoted frame %d to protected storage", frame_id)
        return entry

    def purge_expired_unlocked(self, current_time: float) -> List[int]:
        """
        Purge all expired, unlocked entries from the buffer.

        Implements PURGEEXPIREDUNLOCKED(t - Th) from Algorithm 1.

        Parameters
        ----------
        current_time : float
            Current timestamp.

        Returns
        -------
        List of purged frame IDs.
        """
        to_purge = []
        for frame_id, entry in self._entries.items():
            if entry.can_purge(current_time):
                to_purge.append(frame_id)

        for frame_id in to_purge:
            del self._entries[frame_id]
            self._total_purged += 1
            logger.debug("Purged expired frame %d from escrow", frame_id)

        return to_purge

    def purge_layer(self, frame_id: int, layer: int) -> bool:
        """
        Purge a specific layer from an entry.

        Only allowed if the layer is UNLOCKED.

        Returns True if the layer was purged.
        """
        entry = self._entries.get(frame_id)
        if entry is None:
            return False

        info = entry.layer_info.get(layer)
        if info is None or info.retention_class != RetentionClass.UNLOCKED:
            return False

        # Remove the layer data
        if layer in entry.layers:
            del entry.layers[layer]
            info.retention_class = RetentionClass.PURGED
            logger.debug(
                "Purged layer %d from frame %d", layer, frame_id
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        """Current number of entries in the buffer."""
        return len(self._entries)

    @property
    def is_full(self) -> bool:
        """Whether the buffer is at capacity."""
        return len(self._entries) >= self.capacity

    @property
    def occupancy_fraction(self) -> float:
        """Fraction of buffer capacity used."""
        return len(self._entries) / self.capacity if self.capacity > 0 else 0.0

    @property
    def total_bytes(self) -> int:
        """Total bytes stored in the buffer."""
        return sum(entry.total_bytes for entry in self._entries.values())

    @property
    def uncontrolled_losses(self) -> int:
        """Number of times the buffer overflowed without safe eviction."""
        return self._uncontrolled_losses

    def get_entries_in_window(
        self,
        start_time: float,
        end_time: float,
    ) -> List[EscrowEntry]:
        """
        Retrieve all entries within a time window.

        Used by the retroactive promotion controller to find
        pre-event frames.
        """
        return [
            entry for entry in self._entries.values()
            if start_time <= entry.timestamp <= end_time
        ]

    def get_promoted_entries(self) -> List[EscrowEntry]:
        """Return all promoted entries (for downlink scheduling)."""
        return [
            entry for entry in self._entries.values()
            if entry.is_promoted
        ]

    def get_statistics(self) -> Dict:
        """Return buffer statistics for monitoring."""
        locked_count = sum(
            1 for e in self._entries.values()
            if e.is_locked and not e.is_promoted
        )
        promoted_count = sum(
            1 for e in self._entries.values()
            if e.is_promoted
        )
        return {
            "capacity": self.capacity,
            "size": self.size,
            "occupancy": self.occupancy_fraction,
            "total_bytes": self.total_bytes,
            "locked": locked_count,
            "promoted": promoted_count,
            "total_pushed": self._total_pushed,
            "total_purged": self._total_purged,
            "total_promoted": self._total_promoted,
            "uncontrolled_losses": self._uncontrolled_losses,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _evict_one(self, current_time: float) -> bool:
        """
        Evict the oldest purgeable entry.

        Priority order:
        1. Expired unlocked entries (oldest first)
        2. Unlocked entries with lowest utility (oldest first)
        3. Fail if all are locked/promoted
        """
        # First pass: find expired unlocked entries
        for frame_id, entry in self._entries.items():
            if entry.can_purge(current_time):
                del self._entries[frame_id]
                self._total_purged += 1
                logger.debug("Evicted expired frame %d", frame_id)
                return True

        # Second pass: find any unlocked entry (oldest first)
        for frame_id, entry in self._entries.items():
            if not entry.is_locked and not entry.is_promoted:
                del self._entries[frame_id]
                self._total_purged += 1
                logger.debug("Evicted oldest unlocked frame %d", frame_id)
                return True

        # All entries are locked/promoted — cannot evict
        return False
