"""
End-to-end pipeline integration tests.

Verifies that the complete EventVault-R pipeline runs correctly
from frame ingestion through to downlink scheduling.
"""

import numpy as np
import pytest

from eventvault.acquisition.synthetic import generate_sequence, SourceInfo
from eventvault.config import EventVaultConfig, load_config
from eventvault.pipeline import EventVaultPipeline, PipelineResult


@pytest.fixture
def small_config():
    """Create a config suitable for fast testing."""
    config = load_config()
    config.acquisition.frame_shape = (128, 128)
    config.synthetic.num_static_sources = 10
    config.escrow.capacity = 20
    config.escrow.trigger_horizon_seconds = 600.0
    return config


@pytest.fixture
def small_sequence():
    """Generate a small 10-frame sequence for fast tests."""
    return generate_sequence(
        num_frames=10,
        frame_shape=(128, 128),
        num_static_sources=10,
        transient_position=(64, 64),
        transient_start_frame=3,
        transient_peak_flux=3000.0,
        transient_rise_time_frames=5,
        seed=42,
    )


class TestPipelineIntegration:
    """End-to-end pipeline tests."""

    def test_pipeline_runs_without_error(self, small_config, small_sequence):
        """Pipeline should process all frames without raising."""
        pipeline = EventVaultPipeline(config=small_config)
        result = pipeline.process_sequence(small_sequence)

        assert isinstance(result, PipelineResult)
        assert result.total_frames == 10
        assert len(result.metrics) == 10

    def test_base_layers_stored(self, small_config, small_sequence):
        """Every frame's base layer should be stored long-term."""
        pipeline = EventVaultPipeline(config=small_config)
        pipeline.process_sequence(small_sequence)

        assert len(pipeline.base_layer_store) == 10
        for frame_id in range(10):
            assert frame_id in pipeline.base_layer_store

    def test_escrow_buffer_populated(self, small_config, small_sequence):
        """Escrow buffer should contain entries after processing."""
        pipeline = EventVaultPipeline(config=small_config)
        pipeline.process_sequence(small_sequence)

        assert pipeline.escrow_buffer.size > 0

    def test_metrics_contain_expected_fields(self, small_config, small_sequence):
        """Each frame's metrics should contain all required fields."""
        pipeline = EventVaultPipeline(config=small_config)
        result = pipeline.process_sequence(small_sequence)

        for m in result.metrics:
            assert m.frame_id >= 0
            assert m.timestamp >= 0
            assert m.processing_time_ms > 0
            assert 0.0 <= m.p_known <= 1.0
            assert 0.0 <= m.u_ood <= 1.0
            assert 0.0 <= m.escrow_occupancy <= 1.0

    def test_pipeline_with_trigger(self, small_config, small_sequence):
        """Pipeline should handle trigger callbacks and promote entries."""
        trigger_fired = [False]

        def trigger_callback(frame_id, timestamp, sources):
            # Trigger at frame 7 (transient should be detectable)
            if frame_id == 7:
                trigger_fired[0] = True
                return True
            return False

        pipeline = EventVaultPipeline(
            config=small_config,
            trigger_callback=trigger_callback,
        )
        result = pipeline.process_sequence(small_sequence)

        assert trigger_fired[0], "Trigger should have fired at frame 7"

        # Find the metrics for frame 7
        frame7_metrics = [m for m in result.metrics if m.frame_id == 7]
        assert len(frame7_metrics) == 1
        assert frame7_metrics[0].triggered is True
        assert frame7_metrics[0].promoted_count > 0

    def test_pipeline_reset(self, small_config, small_sequence):
        """Pipeline reset should clear all state."""
        pipeline = EventVaultPipeline(config=small_config)
        pipeline.process_sequence(small_sequence)

        assert pipeline.escrow_buffer.size > 0
        assert len(pipeline.base_layer_store) > 0

        pipeline.reset()

        assert pipeline.escrow_buffer.size == 0
        assert len(pipeline.base_layer_store) == 0
        assert len(pipeline.metrics) == 0

    def test_no_uncontrolled_loss(self, small_config, small_sequence):
        """Pipeline should have zero uncontrolled buffer losses."""
        pipeline = EventVaultPipeline(config=small_config)
        result = pipeline.process_sequence(small_sequence)

        assert pipeline.escrow_buffer.uncontrolled_losses == 0, (
            "Pipeline had uncontrolled buffer overflow — "
            "this violates the zero-loss guarantee"
        )

    def test_resource_controller_updates(self, small_config, small_sequence):
        """Resource controller should update with each frame."""
        pipeline = EventVaultPipeline(config=small_config)
        result = pipeline.process_sequence(small_sequence)

        modes = [m.resource_mode for m in result.metrics]
        # At least some frames should have been processed in NOMINAL mode
        assert "NOMINAL" in modes
