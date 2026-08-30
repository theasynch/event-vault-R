"""
Tests for the retroactive promotion controller.

Verifies:
- Pre-event frames are correctly identified by time window
- Promotion changes entry state to PROMOTED
- Already-purged entries are reported (not silently lost)
- Recovery rate computation
"""

import numpy as np
import pytest

from eventvault.escrow.buffer import EscrowBuffer
from eventvault.escrow.promotion import PromotionController, PromotionResult


def _make_layers(shape=(16, 16)):
    rng = np.random.default_rng(42)
    return {
        k: (rng.normal(size=shape), rng.normal(size=shape), rng.normal(size=shape))
        for k in range(1, 4)
    }


class TestRetroactivePromotion:
    """Tests for the retroactive promotion controller."""

    def test_promote_pre_event_frames(self):
        """Frames in the pre-trigger window should be promoted."""
        buf = EscrowBuffer(capacity=100, trigger_horizon_seconds=3600)
        ctrl = PromotionController(buf, default_pre_window=300.0)

        # Push 10 frames at 30s cadence
        for i in range(10):
            buf.push(i, float(i * 30), _make_layers())

        # Trigger at t=240 (frame 8), pre-window = 300s
        # Should promote frames with timestamp in [240-300, 240] = [-60, 240]
        # That means frames 0-8 (timestamps 0-240)
        result = ctrl.promote_history(trigger_time=240.0, pre_window=300.0)

        assert isinstance(result, PromotionResult)
        assert len(result.promoted_ids) == 9  # Frames 0-8
        assert result.trigger_time == 240.0

    def test_promoted_entries_are_protected(self):
        """Promoted entries should be locked and flagged."""
        buf = EscrowBuffer(capacity=100, trigger_horizon_seconds=3600)
        ctrl = PromotionController(buf, default_pre_window=300.0)

        for i in range(5):
            buf.push(i, float(i * 30), _make_layers())

        ctrl.promote_history(trigger_time=120.0, pre_window=150.0)

        # Check promoted entries are protected
        for i in range(5):
            entry = buf.get(i)
            if entry and entry.timestamp <= 120.0:
                assert entry.is_promoted, f"Frame {i} should be promoted"
                assert entry.is_locked, f"Frame {i} should be locked"

    def test_already_promoted_not_double_counted(self):
        """Already-promoted entries should be reported separately."""
        buf = EscrowBuffer(capacity=100, trigger_horizon_seconds=3600)
        ctrl = PromotionController(buf, default_pre_window=300.0)

        for i in range(5):
            buf.push(i, float(i * 30), _make_layers())

        # First promotion
        r1 = ctrl.promote_history(trigger_time=120.0, pre_window=300.0)
        assert len(r1.promoted_ids) == 5

        # Second promotion on same window
        r2 = ctrl.promote_history(trigger_time=120.0, pre_window=300.0)
        assert len(r2.promoted_ids) == 0
        assert len(r2.already_promoted) == 5

    def test_purged_entries_reported(self):
        """Entries that were already purged should be reported."""
        buf = EscrowBuffer(capacity=100, trigger_horizon_seconds=30.0)
        ctrl = PromotionController(buf, default_pre_window=300.0)

        for i in range(5):
            buf.push(i, float(i * 30), _make_layers())

        # Purge all expired entries (horizon=30s, at t=200 frames 0-4 are expired)
        buf.purge_expired_unlocked(200.0)

        # Now try to promote — entries are gone
        result = ctrl.promote_history(trigger_time=120.0, pre_window=300.0)
        # All were purged, so candidates_found should be 0
        assert result.candidates_found == 0

    def test_recovery_rate_computation(self):
        """Recovery rate should reflect successful promotions."""
        buf = EscrowBuffer(capacity=100, trigger_horizon_seconds=3600)
        ctrl = PromotionController(buf, default_pre_window=300.0)

        for i in range(10):
            buf.push(i, float(i * 30), _make_layers())

        ctrl.promote_history(trigger_time=150.0, pre_window=300.0)

        rate = ctrl.get_recovery_rate()
        assert 0.0 <= rate <= 1.0

    def test_narrow_window_limits_promotion(self):
        """A narrow pre-window should only promote nearby frames."""
        buf = EscrowBuffer(capacity=100, trigger_horizon_seconds=3600)
        ctrl = PromotionController(buf, default_pre_window=300.0)

        for i in range(10):
            buf.push(i, float(i * 30), _make_layers())

        # Very narrow window: only 60s before trigger
        result = ctrl.promote_history(trigger_time=240.0, pre_window=60.0)

        # Should only include frames at t=180, t=210, t=240
        # (timestamps within [180, 240])
        for pid in result.promoted_ids:
            entry = buf.get(pid)
            assert entry is not None
            assert 180.0 <= entry.timestamp <= 240.0

    def test_promotion_history_accumulated(self):
        """Promotion history should accumulate across multiple triggers."""
        buf = EscrowBuffer(capacity=100, trigger_horizon_seconds=3600)
        ctrl = PromotionController(buf, default_pre_window=300.0)

        for i in range(20):
            buf.push(i, float(i * 30), _make_layers())

        ctrl.promote_history(trigger_time=150.0, pre_window=100.0)
        ctrl.promote_history(trigger_time=450.0, pre_window=100.0)

        assert len(ctrl.promotion_history) == 2
