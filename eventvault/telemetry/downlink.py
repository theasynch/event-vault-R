"""
Throttled downlink queue for EventVault-R.

Simulates a bandwidth-constrained telemetry downlink for the
software reference model. Priority ordering ensures that:
1. Base layers are always transmitted first
2. Promoted residuals get highest priority
3. Normal escrow residuals are transmitted as bandwidth allows
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class DownlinkPriority(IntEnum):
    """Downlink priority levels (lower number = higher priority)."""
    CRITICAL = 0      # Base layers, always downlink
    PROMOTED = 1      # Retroactively promoted residuals
    HIGH = 2          # High-uncertainty observations
    NORMAL = 3        # Standard residual layers
    LOW = 4           # Low-priority background data


@dataclass
class DownlinkItem:
    """
    A single item in the downlink queue.

    Attributes
    ----------
    frame_id : int
        Frame identifier.
    layer : str
        Layer identifier ('base', 'H1', 'H2', 'H3').
    priority : DownlinkPriority
        Transmission priority.
    size_bytes : int
        Data size in bytes.
    timestamp : float
        When this item was queued.
    data : bytes or None
        Actual data payload (None for simulation).
    """
    frame_id: int
    layer: str
    priority: DownlinkPriority
    size_bytes: int
    timestamp: float
    data: Optional[bytes] = None


@dataclass
class DownlinkStatistics:
    """Downlink queue and transmission statistics."""
    total_queued: int = 0
    total_transmitted: int = 0
    total_bytes_transmitted: int = 0
    total_dropped: int = 0
    queue_depth: int = 0
    items_by_priority: Dict[str, int] = field(default_factory=dict)


class DownlinkQueue:
    """
    Priority-ordered throttled downlink queue.

    Simulates bandwidth-constrained spacecraft telemetry with
    priority-based scheduling.

    Parameters
    ----------
    bandwidth_bps : int
        Available downlink bandwidth in bits per second.
    max_queue_depth : int
        Maximum items in the queue before dropping low-priority items.
    """

    def __init__(
        self,
        bandwidth_bps: int = 9600,
        max_queue_depth: int = 50,
    ):
        self.bandwidth_bps = bandwidth_bps
        self.max_queue_depth = max_queue_depth

        # Priority queues (one deque per priority level)
        self._queues: Dict[DownlinkPriority, deque] = {
            p: deque() for p in DownlinkPriority
        }

        # Statistics
        self._stats = DownlinkStatistics()

        # Transmission log
        self._transmitted: List[DownlinkItem] = []

    def enqueue(self, item: DownlinkItem) -> bool:
        """
        Add an item to the downlink queue.

        If the queue is full, drops the lowest-priority item.

        Parameters
        ----------
        item : DownlinkItem
            Item to queue for downlink.

        Returns
        -------
        bool
            True if item was queued, False if dropped.
        """
        total_depth = sum(len(q) for q in self._queues.values())

        if total_depth >= self.max_queue_depth:
            # Try to drop lowest priority item
            dropped = self._drop_lowest_priority()
            if not dropped:
                logger.warning(
                    "Downlink queue full, dropping frame %d layer %s",
                    item.frame_id, item.layer,
                )
                self._stats.total_dropped += 1
                return False

        self._queues[item.priority].append(item)
        self._stats.total_queued += 1

        logger.debug(
            "Queued frame %d layer %s (priority=%s, %d bytes)",
            item.frame_id, item.layer, item.priority.name, item.size_bytes,
        )
        return True

    def enqueue_base_layer(
        self,
        frame_id: int,
        size_bytes: int,
        timestamp: float,
    ) -> bool:
        """Shortcut to enqueue a base layer with CRITICAL priority."""
        return self.enqueue(DownlinkItem(
            frame_id=frame_id,
            layer="base",
            priority=DownlinkPriority.CRITICAL,
            size_bytes=size_bytes,
            timestamp=timestamp,
        ))

    def enqueue_promoted(
        self,
        frame_id: int,
        layer: str,
        size_bytes: int,
        timestamp: float,
    ) -> bool:
        """Shortcut to enqueue a promoted residual layer."""
        return self.enqueue(DownlinkItem(
            frame_id=frame_id,
            layer=layer,
            priority=DownlinkPriority.PROMOTED,
            size_bytes=size_bytes,
            timestamp=timestamp,
        ))

    def transmit(self, duration_seconds: float) -> List[DownlinkItem]:
        """
        Simulate downlink transmission for a given duration.

        Transmits items in priority order until bandwidth is exhausted.

        Parameters
        ----------
        duration_seconds : float
            Available transmission time.

        Returns
        -------
        List of transmitted items.
        """
        available_bits = self.bandwidth_bps * duration_seconds
        available_bytes = available_bits / 8.0

        transmitted = []
        bytes_sent = 0

        # Transmit in priority order
        for priority in sorted(self._queues.keys()):
            queue = self._queues[priority]
            while queue and bytes_sent + queue[0].size_bytes <= available_bytes:
                item = queue.popleft()
                bytes_sent += item.size_bytes
                transmitted.append(item)
                self._stats.total_transmitted += 1
                self._stats.total_bytes_transmitted += item.size_bytes

        self._transmitted.extend(transmitted)

        if transmitted:
            logger.debug(
                "Transmitted %d items (%.1f KB) in %.1f seconds",
                len(transmitted), bytes_sent / 1024, duration_seconds,
            )

        return transmitted

    @property
    def queue_depth(self) -> int:
        """Total items currently in the queue."""
        return sum(len(q) for q in self._queues.values())

    @property
    def statistics(self) -> DownlinkStatistics:
        """Return current downlink statistics."""
        self._stats.queue_depth = self.queue_depth
        self._stats.items_by_priority = {
            p.name: len(q) for p, q in self._queues.items()
        }
        return self._stats

    @property
    def transmitted_items(self) -> List[DownlinkItem]:
        """All items that have been transmitted."""
        return list(self._transmitted)

    def _drop_lowest_priority(self) -> bool:
        """Drop the lowest priority item from the queue."""
        for priority in reversed(sorted(self._queues.keys())):
            queue = self._queues[priority]
            if queue:
                dropped = queue.pop()
                self._stats.total_dropped += 1
                logger.debug(
                    "Dropped frame %d layer %s (priority=%s)",
                    dropped.frame_id, dropped.layer, dropped.priority.name,
                )
                return True
        return False
