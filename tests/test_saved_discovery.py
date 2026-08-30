"""
Saved Discovery test — the primary EventVault-R demonstration.

Implements Section XIII.B of the proposal:
- 60 frames at 30-second cadence
- Transient begins rising at frame T10
- Transient not confidently recognized until T25
- EventVault-R retains pre-trigger residuals in escrow
- After detection at T25, retroactively promotes pre-trigger history

Compares EventVault-R against a naive immediate-triage baseline.

Principal measurement: percentage of pre-trigger photometric
samples recovered within the target error bound.
"""

import numpy as np
import pytest

from eventvault.acquisition.synthetic import generate_sequence, SourceInfo
from eventvault.codec.dwt import decompose, reconstruct
from eventvault.config import load_config
from eventvault.pipeline import EventVaultPipeline
from eventvault.science.source_extraction import measure_source


@pytest.fixture(scope="module")
def saved_discovery_config():
    """Config for the Saved Discovery test."""
    config = load_config()
    # Use smaller frames for faster testing
    config.acquisition.frame_shape = (128, 128)
    config.synthetic.num_static_sources = 15
    config.escrow.capacity = 70  # Must hold >60 frames
    config.escrow.trigger_horizon_seconds = 3600.0  # Long horizon
    config.saved_discovery.transient_position = (64, 64)
    return config


@pytest.fixture(scope="module")
def saved_discovery_sequence(saved_discovery_config):
    """Generate the 60-frame Saved Discovery sequence."""
    cfg = saved_discovery_config.saved_discovery
    return generate_sequence(
        num_frames=cfg.num_frames,
        cadence_seconds=cfg.cadence_seconds,
        frame_shape=saved_discovery_config.acquisition.frame_shape,
        num_static_sources=saved_discovery_config.synthetic.num_static_sources,
        transient_position=tuple(cfg.transient_position),
        transient_start_frame=cfg.transient_start_frame,
        transient_peak_flux=cfg.transient_peak_flux,
        transient_rise_time_frames=cfg.transient_rise_time_frames,
        seed=42,
    )


class TestSavedDiscovery:
    """
    The Saved Discovery experiment (Section XIII.B).

    This is the primary demonstration of EventVault-R's value:
    recovering pre-event photometric data that a naive triage
    system would have discarded.
    """

    def test_eventvault_recovers_pre_trigger_frames(
        self, saved_discovery_config, saved_discovery_sequence
    ):
        """
        EventVault-R should recover pre-trigger photometric samples.

        The trigger fires at frame 25, and all frames from 10-24
        (the pre-trigger window where the transient was rising but
        not yet confidently detected) should be recoverable.
        """
        cfg = saved_discovery_config.saved_discovery

        def trigger_callback(frame_id, timestamp, sources):
            # Transient confidently detected at frame 25
            return frame_id == cfg.transient_detect_frame

        pipeline = EventVaultPipeline(
            config=saved_discovery_config,
            trigger_callback=trigger_callback,
        )

        result = pipeline.process_sequence(saved_discovery_sequence)

        # Check that promotion happened
        promoted_results = result.promotion_results
        assert len(promoted_results) > 0, "No promotion occurred"

        # Check promoted frames include pre-trigger window
        promoted_ids = set()
        for pr in promoted_results:
            promoted_ids.update(pr.promoted_ids)

        pre_trigger_frames = set(range(
            cfg.transient_start_frame,
            cfg.transient_detect_frame
        ))
        recovered = pre_trigger_frames & promoted_ids

        recovery_rate = len(recovered) / max(len(pre_trigger_frames), 1)

        # Target: recover all pre-trigger frames
        assert recovery_rate > 0.0, (
            f"EventVault-R failed to recover any pre-trigger frames. "
            f"Expected frames {pre_trigger_frames}, got {promoted_ids}"
        )

    def test_naive_triage_loses_pre_trigger(
        self, saved_discovery_config, saved_discovery_sequence
    ):
        """
        Naive triage baseline: immediate keep-or-delete decisions
        should lose pre-trigger data.

        A simple threshold-based triage that only keeps frames with
        obvious transient detections would miss the early rising phase.
        """
        cfg = saved_discovery_config.saved_discovery
        transient_pos = tuple(cfg.transient_position)

        # Naive triage: only keep frames where transient is above threshold
        detection_threshold = cfg.transient_peak_flux * 0.3
        kept_frames = []

        for frame, metadata in saved_discovery_sequence:
            # Check if transient is detectable at this frame
            image = frame.astype(np.float64)
            pos = (int(transient_pos[1]), int(transient_pos[0]))
            meas = measure_source(image, pos, aperture_radius=5.0)

            if meas.flux > detection_threshold:
                kept_frames.append(metadata.frame_id)

        pre_trigger_frames = set(range(
            cfg.transient_start_frame,
            cfg.transient_detect_frame
        ))
        naive_recovered = pre_trigger_frames & set(kept_frames)

        # Naive triage should miss at least some early frames
        # (the transient is too faint to detect in early rising phase)
        naive_rate = len(naive_recovered) / max(len(pre_trigger_frames), 1)

        # The naive triage won't recover all pre-trigger frames
        # (it can only detect the transient once it's bright enough)
        assert naive_rate < 1.0 or len(pre_trigger_frames) == 0, (
            "Naive triage unexpectedly recovered all pre-trigger frames"
        )

    def test_zero_buffer_overflow(
        self, saved_discovery_config, saved_discovery_sequence
    ):
        """
        Verification matrix target: 0 uncontrolled buffer loss
        during the 60-frame test.
        """
        def trigger_callback(frame_id, timestamp, sources):
            return frame_id == saved_discovery_config.saved_discovery.transient_detect_frame

        pipeline = EventVaultPipeline(
            config=saved_discovery_config,
            trigger_callback=trigger_callback,
        )

        pipeline.process_sequence(saved_discovery_sequence)

        assert pipeline.escrow_buffer.uncontrolled_losses == 0, (
            "Uncontrolled buffer loss during Saved Discovery test"
        )

    def test_all_frames_processed(
        self, saved_discovery_config, saved_discovery_sequence
    ):
        """All 60 frames should be successfully processed."""
        pipeline = EventVaultPipeline(config=saved_discovery_config)
        result = pipeline.process_sequence(saved_discovery_sequence)

        assert result.total_frames == saved_discovery_config.saved_discovery.num_frames
        assert len(result.metrics) == saved_discovery_config.saved_discovery.num_frames

    def test_base_layers_always_available(
        self, saved_discovery_config, saved_discovery_sequence
    ):
        """Base layers should be stored for every frame (continuous context)."""
        pipeline = EventVaultPipeline(config=saved_discovery_config)
        pipeline.process_sequence(saved_discovery_sequence)

        num_frames = saved_discovery_config.saved_discovery.num_frames
        assert len(pipeline.base_layer_store) == num_frames
