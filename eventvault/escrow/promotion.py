"""
Retroactive promotion controller for EventVault-R.

Implements Section VIII of the proposal: when a transient becomes
confidently detectable at T_trig, the controller searches

    t ∈ [T_trig - ΔT_pre, T_trig]

and re-evaluates all matching escrow entries. If they contribute
to the rising light curve or another required measurement, the
layers are promoted to protected storage.

This is the key mechanism that allows EventVault-R to "change
its mind" about previously ambiguous observations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from eventvault.escrow.buffer import EscrowBuffer
from eventvault.escrow.entry import EscrowEntry

logger = logging.getLogger(__name__)


@dataclass
class PromotionResult:
    """
    Result of a retroactive promotion operation.

    Attributes
    ----------
    trigger_time : float
        Time at which the trigger was received.
    window_start : float
        Start of the pre-event search window.
    window_end : float
        End of the search window.
    candidates_found : int
        Number of entries in the search window.
    promoted_ids : list
        Frame IDs that were promoted.
    already_promoted : list
        Frame IDs that were already promoted.
    already_purged : list
        Frame IDs that had already been purged.
    total_bytes_promoted : int
        Total bytes of promoted residual data.
    """
    trigger_time: float
    window_start: float
    window_end: float
    candidates_found: int
    promoted_ids: List[int]
    already_promoted: List[int]
    already_purged: List[int]
    total_bytes_promoted: int


class PromotionController:
    """
    Retroactive promotion controller.

    Manages trigger-driven promotion of pre-event escrow entries
    for priority downlink.

    Parameters
    ----------
    escrow_buffer : EscrowBuffer
        Reference to the shared escrow buffer.
    default_pre_window : float
        Default pre-trigger window in seconds (ΔT_pre).
    """

    def __init__(
        self,
        escrow_buffer: EscrowBuffer,
        default_pre_window: float = 600.0,
    ):
        self.escrow_buffer = escrow_buffer
        self.default_pre_window = default_pre_window
        self._promotion_history: List[PromotionResult] = []

    def promote_history(
        self,
        trigger_time: float,
        pre_window: Optional[float] = None,
        trigger_position: Optional[tuple] = None,
    ) -> PromotionResult:
        """
        Promote pre-event residuals after a trigger.

        Implements PROMOTEHISTORY(T_trig - ΔT_pre, T_trig) from
        Algorithm 1, line 25.

        Parameters
        ----------
        trigger_time : float
            Time at which the event was confidently detected.
        pre_window : float, optional
            Pre-trigger time window to search (seconds).
            Defaults to self.default_pre_window.
        trigger_position : (x, y), optional
            Spatial position of the trigger (for filtering).

        Returns
        -------
        PromotionResult summarizing the operation.
        """
        if pre_window is None:
            pre_window = self.default_pre_window

        window_start = trigger_time - pre_window
        window_end = trigger_time

        logger.info(
            "Retroactive promotion: searching [%.1f, %.1f] "
            "(ΔT_pre = %.1f s)",
            window_start, window_end, pre_window,
        )

        # Find all entries in the pre-event window
        candidates = self.escrow_buffer.get_entries_in_window(
            window_start, window_end
        )

        promoted_ids = []
        already_promoted = []
        already_purged = []
        total_bytes = 0

        for entry in candidates:
            if entry.is_promoted:
                already_promoted.append(entry.frame_id)
                continue

            if len(entry.layers) == 0:
                # Entry was already fully purged
                already_purged.append(entry.frame_id)
                continue

            # Promote the entry
            promoted = self.escrow_buffer.promote(entry.frame_id)
            if promoted is not None:
                promoted_ids.append(entry.frame_id)
                total_bytes += entry.total_bytes

        result = PromotionResult(
            trigger_time=trigger_time,
            window_start=window_start,
            window_end=window_end,
            candidates_found=len(candidates),
            promoted_ids=promoted_ids,
            already_promoted=already_promoted,
            already_purged=already_purged,
            total_bytes_promoted=total_bytes,
        )

        self._promotion_history.append(result)

        logger.info(
            "Promotion complete: %d frames promoted, %d already promoted, "
            "%d already purged, %d bytes protected",
            len(promoted_ids), len(already_promoted),
            len(already_purged), total_bytes,
        )

        return result

    @property
    def promotion_history(self) -> List[PromotionResult]:
        """Return all past promotion operations."""
        return list(self._promotion_history)

    def get_recovery_rate(self) -> float:
        """
        Compute the overall recovery rate across all promotions.

        Recovery rate = promoted / (promoted + already_purged)
        """
        total_promoted = 0
        total_purged = 0
        for result in self._promotion_history:
            total_promoted += len(result.promoted_ids)
            total_purged += len(result.already_purged)

        total = total_promoted + total_purged
        if total == 0:
            return 1.0
        return total_promoted / total
