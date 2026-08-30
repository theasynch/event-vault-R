"""
Tests for the circular escrow buffer.

Verifies:
- FIFO ordering and capacity enforcement
- Lock/unlock/promote semantics
- Zero uncontrolled data loss guarantee
- Expired entry purging
- Memory pressure behavior
"""

import numpy as np
import pytest

from eventvault.escrow.buffer import EscrowBuffer, EscrowBufferOverflowError
from eventvault.escrow.entry import EscrowEntry, RetentionClass


def _make_residual_layers(levels=3, shape=(32, 32)):
    """Create dummy residual layers for testing."""
    rng = np.random.default_rng(42)
    layers = {}
    for k in range(1, levels + 1):
        lh = rng.normal(0, 10, shape)
        hl = rng.normal(0, 10, shape)
        hh = rng.normal(0, 10, shape)
        layers[k] = (lh, hl, hh)
    return layers


class TestEscrowBuffer:
    """Core buffer tests."""

    def test_push_and_retrieve(self):
        """Push an entry and retrieve it by frame ID."""
        buf = EscrowBuffer(capacity=10)
        layers = _make_residual_layers()
        entry = buf.push(frame_id=0, timestamp=0.0, residual_layers=layers)
        assert entry is not None
        assert buf.get(0) is entry
        assert buf.size == 1

    def test_capacity_enforcement(self):
        """Buffer should not exceed capacity."""
        buf = EscrowBuffer(capacity=5, trigger_horizon_seconds=10.0)
        layers = _make_residual_layers()

        for i in range(5):
            buf.push(frame_id=i, timestamp=float(i), residual_layers=layers)

        assert buf.size == 5
        assert buf.is_full

        # Pushing one more should evict the oldest
        buf.push(frame_id=5, timestamp=100.0, residual_layers=layers)
        assert buf.size == 5
        assert buf.get(0) is None  # Oldest should be evicted
        assert buf.get(5) is not None

    def test_fifo_eviction_order(self):
        """Oldest unlocked entry should be evicted first."""
        buf = EscrowBuffer(capacity=3, trigger_horizon_seconds=10.0)
        layers = _make_residual_layers()

        buf.push(0, 0.0, layers)
        buf.push(1, 1.0, layers)
        buf.push(2, 2.0, layers)

        # Push beyond capacity
        buf.push(3, 100.0, layers)

        assert buf.get(0) is None  # First in, first out
        assert buf.get(1) is not None
        assert buf.get(2) is not None
        assert buf.get(3) is not None

    def test_locked_entries_not_evicted(self):
        """Locked entries must never be evicted."""
        buf = EscrowBuffer(capacity=3, trigger_horizon_seconds=10.0)
        layers = _make_residual_layers()

        buf.push(0, 0.0, layers)
        buf.push(1, 1.0, layers)
        buf.push(2, 2.0, layers)

        # Lock the oldest entry
        buf.lock(0)

        # Push beyond capacity — should skip frame 0 and evict frame 1
        buf.push(3, 100.0, layers)

        assert buf.get(0) is not None  # Locked — protected
        assert buf.get(1) is None      # Evicted
        assert buf.get(2) is not None
        assert buf.get(3) is not None

    def test_zero_uncontrolled_loss_guarantee(self):
        """
        CRITICAL TEST: When all entries are locked, buffer should
        raise an error rather than silently losing data.
        """
        buf = EscrowBuffer(capacity=3, trigger_horizon_seconds=10.0)
        layers = _make_residual_layers()

        for i in range(3):
            buf.push(i, float(i), layers)
            buf.lock(i)

        # All entries locked — pushing should fail safely
        with pytest.raises(EscrowBufferOverflowError):
            buf.push(3, 100.0, layers)

        # Verify no data was lost
        assert buf.uncontrolled_losses == 1
        assert buf.size == 3
        for i in range(3):
            assert buf.get(i) is not None

    def test_promoted_entries_not_evicted(self):
        """Promoted entries must be treated as locked."""
        buf = EscrowBuffer(capacity=3, trigger_horizon_seconds=10.0)
        layers = _make_residual_layers()

        buf.push(0, 0.0, layers)
        buf.push(1, 1.0, layers)
        buf.push(2, 2.0, layers)

        # Promote oldest
        buf.promote(0)

        # Push beyond capacity
        buf.push(3, 100.0, layers)

        assert buf.get(0) is not None  # Promoted — protected
        assert buf.get(0).is_promoted


class TestEscrowPurging:
    """Tests for expiry-based purging."""

    def test_purge_expired_unlocked(self):
        """Expired unlocked entries should be purged."""
        buf = EscrowBuffer(capacity=10, trigger_horizon_seconds=60.0)
        layers = _make_residual_layers()

        buf.push(0, 0.0, layers)
        buf.push(1, 30.0, layers)
        buf.push(2, 90.0, layers)

        # At t=120, entries 0 and 1 should be expired (horizon=60s)
        purged = buf.purge_expired_unlocked(120.0)
        assert 0 in purged
        assert 1 in purged
        assert 2 not in purged

    def test_expired_locked_entries_not_purged(self):
        """Expired but locked entries must not be purged."""
        buf = EscrowBuffer(capacity=10, trigger_horizon_seconds=60.0)
        layers = _make_residual_layers()

        buf.push(0, 0.0, layers)
        buf.lock(0)

        purged = buf.purge_expired_unlocked(120.0)
        assert 0 not in purged
        assert buf.get(0) is not None

    def test_per_layer_purge(self):
        """Should be able to purge individual layers."""
        buf = EscrowBuffer(capacity=10)
        layers = _make_residual_layers()

        buf.push(0, 0.0, layers)
        buf.unlock_layer(0, 3)  # Mark H3 as safe to purge

        assert buf.purge_layer(0, 3) is True
        assert 3 not in buf.get(0).layers

        # H1, H2 should still be there
        assert 1 in buf.get(0).layers
        assert 2 in buf.get(0).layers

    def test_cannot_purge_locked_layer(self):
        """Should not be able to purge a locked layer."""
        buf = EscrowBuffer(capacity=10)
        layers = _make_residual_layers()

        buf.push(0, 0.0, layers)
        buf.lock(0)

        assert buf.purge_layer(0, 3) is False


class TestEscrowQueries:
    """Tests for buffer query methods."""

    def test_get_entries_in_window(self):
        """Should return entries within a time window."""
        buf = EscrowBuffer(capacity=100)
        layers = _make_residual_layers()

        for i in range(10):
            buf.push(i, float(i * 30), layers)

        # Window [60, 180] should include frames 2, 3, 4, 5, 6
        entries = buf.get_entries_in_window(60.0, 180.0)
        frame_ids = {e.frame_id for e in entries}
        assert frame_ids == {2, 3, 4, 5, 6}

    def test_get_promoted_entries(self):
        """Should return only promoted entries."""
        buf = EscrowBuffer(capacity=10)
        layers = _make_residual_layers()

        for i in range(5):
            buf.push(i, float(i), layers)

        buf.promote(1)
        buf.promote(3)

        promoted = buf.get_promoted_entries()
        ids = {e.frame_id for e in promoted}
        assert ids == {1, 3}

    def test_statistics(self):
        """Statistics should accurately reflect buffer state."""
        buf = EscrowBuffer(capacity=10)
        layers = _make_residual_layers()

        for i in range(5):
            buf.push(i, float(i), layers)

        buf.lock(2)
        buf.promote(4)

        stats = buf.get_statistics()
        assert stats["capacity"] == 10
        assert stats["size"] == 5
        assert stats["locked"] == 1  # Frame 2
        assert stats["promoted"] == 1  # Frame 4
        assert stats["total_pushed"] == 5

    def test_occupancy_fraction(self):
        """Occupancy should be correctly computed."""
        buf = EscrowBuffer(capacity=10)
        layers = _make_residual_layers()

        assert buf.occupancy_fraction == 0.0

        for i in range(5):
            buf.push(i, float(i), layers)

        assert buf.occupancy_fraction == 0.5
