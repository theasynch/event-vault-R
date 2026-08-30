"""
EventVault-R Core Control Loop.

Implements Algorithm 1 from the proposal — the main pipeline that
ties together all modules:

    1. DWT decomposition
    2. Store base layer long-term
    3. Push residuals to escrow
    4. Extract sources
    5. Estimate uncertainty
    6. Guardrail evaluation (layer-by-layer)
    7. Retention utility scoring
    8. Resource-aware scheduling
    9. Trigger-driven retroactive promotion
   10. Purge expired unlocked entries

This is the asyncio-based reference implementation described in
Section XI.A, providing deterministic inputs/outputs so that the
embedded implementation can be validated against it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from numpy.typing import NDArray

from eventvault.acquisition.calibration import (
    CalibrationFrames,
    calibrate_frame,
    check_frame_quality,
)
from eventvault.acquisition.synthetic import FrameMetadata
from eventvault.codec.dwt import (
    WaveletDecomposition,
    decompose,
    get_layer_sizes,
    reconstruct,
)
from eventvault.config import EventVaultConfig, load_config
from eventvault.escrow.buffer import EscrowBuffer
from eventvault.escrow.entry import EscrowEntry
from eventvault.escrow.promotion import PromotionController, PromotionResult
from eventvault.resource.controller import ResourceController
from eventvault.science.guardrail import evaluate_frame, FrameGuardrailDecision
from eventvault.science.source_extraction import (
    SourceMeasurement,
    extract_sources,
)
from eventvault.telemetry.downlink import DownlinkQueue
from eventvault.uncertainty.estimator import UncertaintyEstimator, create_estimator
from eventvault.uncertainty.retention import compute_retention_utility

logger = logging.getLogger(__name__)


@dataclass
class PipelineMetrics:
    """Per-frame processing metrics for instrumentation."""
    frame_id: int
    timestamp: float
    processing_time_ms: float = 0.0
    num_sources_detected: int = 0
    p_known: float = 0.0
    u_ood: float = 0.0
    retention_utility: float = 0.0
    purgeable_layers: List[int] = field(default_factory=list)
    locked_layers: List[int] = field(default_factory=list)
    escrow_occupancy: float = 0.0
    resource_mode: str = "NOMINAL"
    triggered: bool = False
    promoted_count: int = 0


@dataclass
class PipelineResult:
    """Complete result of processing a frame sequence."""
    metrics: List[PipelineMetrics] = field(default_factory=list)
    promotion_results: List[PromotionResult] = field(default_factory=list)
    total_frames: int = 0
    total_processing_time_ms: float = 0.0
    final_escrow_stats: Dict = field(default_factory=dict)
    final_downlink_stats: Dict = field(default_factory=dict)


class EventVaultPipeline:
    """
    EventVault-R end-to-end processing pipeline.

    Orchestrates all modules according to Algorithm 1.

    Parameters
    ----------
    config : EventVaultConfig, optional
        Configuration parameters. Loads defaults if not provided.
    calibration : CalibrationFrames, optional
        Calibration reference frames. Skips calibration if None.
    trigger_callback : callable, optional
        Function(frame_id, timestamp, sources) -> bool that
        returns True when a trigger event is detected.
    """

    def __init__(
        self,
        config: Optional[EventVaultConfig] = None,
        calibration: Optional[CalibrationFrames] = None,
        trigger_callback: Optional[Callable] = None,
    ):
        self.config = config or load_config()
        self.calibration = calibration

        # Initialize all sub-modules
        self.escrow_buffer = EscrowBuffer(
            capacity=self.config.escrow.capacity,
            trigger_horizon_seconds=self.config.escrow.trigger_horizon_seconds,
        )

        self.promotion_controller = PromotionController(
            escrow_buffer=self.escrow_buffer,
            default_pre_window=self.config.escrow.trigger_horizon_seconds,
        )

        self.uncertainty_estimator = create_estimator(
            method=self.config.uncertainty.method,
        )

        self.resource_controller = ResourceController(
            default_horizon=self.config.escrow.trigger_horizon_seconds,
            min_horizon=self.config.resource.min_horizon_seconds,
            warning_fraction=self.config.resource.memory_warning_fraction,
            critical_fraction=self.config.resource.memory_critical_fraction,
            min_detail_level=self.config.resource.min_detail_level,
        )

        self.downlink_queue = DownlinkQueue(
            bandwidth_bps=self.config.telemetry.downlink_bandwidth_bps,
            max_queue_depth=self.config.telemetry.max_queue_depth,
        )

        self.trigger_callback = trigger_callback

        # Storage for base layers (long-term store)
        self.base_layer_store: Dict[int, NDArray] = {}

        # Processing log
        self._metrics: List[PipelineMetrics] = []

    def process_frame(
        self,
        frame: NDArray,
        metadata: FrameMetadata,
    ) -> PipelineMetrics:
        """
        Process a single frame through the full EventVault-R pipeline.

        Implements Algorithm 1 from the proposal.

        Parameters
        ----------
        frame : ndarray
            Raw or calibrated detector frame.
        metadata : FrameMetadata
            Frame metadata (timestamp, frame_id, etc.).

        Returns
        -------
        PipelineMetrics for this frame.
        """
        t_start = time.perf_counter()
        metrics = PipelineMetrics(
            frame_id=metadata.frame_id,
            timestamp=metadata.timestamp,
        )

        # --- Step 0: Calibration ---
        if self.calibration is not None:
            quality = check_frame_quality(
                frame,
                expected_shape=self.config.acquisition.frame_shape,
            )
            if not quality.is_valid:
                logger.warning(
                    "Frame %d failed quality check: %s",
                    metadata.frame_id, quality.message,
                )
            calibrated = calibrate_frame(frame, self.calibration)
        else:
            calibrated = frame.astype(np.float64)

        # --- Step 1: DWT Decomposition (Algorithm 1, line 1) ---
        # {L0, R1, R2, R3} ← DWT_DECOMPOSE(I_t)
        decomp = decompose(
            calibrated,
            wavelet=self.config.codec.wavelet,
            levels=self.config.codec.decomposition_levels,
            mode=self.config.codec.mode,
        )

        # --- Step 2: Store base layer long-term (line 2) ---
        # STORE_LONGTERM(L0, t)
        self.base_layer_store[metadata.frame_id] = decomp.base_layer.copy()

        # Queue base layer for downlink
        base_size = decomp.base_layer.nbytes
        self.downlink_queue.enqueue_base_layer(
            metadata.frame_id, base_size, metadata.timestamp,
        )

        # --- Step 3: Push residuals to escrow (line 3) ---
        # PUSH_ESCROW(R1, R2, R3, t)
        try:
            escrow_entry = self.escrow_buffer.push(
                frame_id=metadata.frame_id,
                timestamp=metadata.timestamp,
                residual_layers=dict(decomp.residual_layers),
                source_count=0,  # Updated below
                horizon_override=self.resource_controller.parameters.trigger_horizon,
            )
        except Exception as e:
            logger.error("Failed to push frame %d to escrow: %s",
                         metadata.frame_id, e)
            metrics.processing_time_ms = (time.perf_counter() - t_start) * 1000
            self._metrics.append(metrics)
            return metrics

        # --- Step 4: Extract sources (line 4) ---
        # S ← EXTRACT_SOURCES(L0, R1)
        full_recon = reconstruct(decomp)
        reference_sources = extract_sources(
            full_recon,
            min_snr=self.resource_controller.parameters.snr_threshold,
            aperture_radius=self.config.guardrail.aperture_radius,
            annulus_inner=self.config.guardrail.annulus_inner,
            annulus_outer=self.config.guardrail.annulus_outer,
            threshold_sigma=self.config.guardrail.min_source_snr,
        )
        metrics.num_sources_detected = len(reference_sources)
        escrow_entry.source_count = len(reference_sources)

        # --- Step 5: Estimate uncertainty (line 5) ---
        # (p_known, u_OOD) ← ESTIMATE_UNCERTAINTY(S)
        p_known, u_ood = self.uncertainty_estimator.estimate(calibrated)
        metrics.p_known = p_known
        metrics.u_ood = u_ood
        escrow_entry.uncertainty_score = u_ood

        # --- Steps 6-21: Guardrail evaluation (lines 6-21) ---
        if len(reference_sources) > 0:
            guardrail_decision = evaluate_frame(
                decomp,
                reference_sources,
                epsilon_F=self.config.guardrail.epsilon_F,
                epsilon_x=self.config.guardrail.epsilon_x,
                aperture_radius=self.config.guardrail.aperture_radius,
                annulus_inner=self.config.guardrail.annulus_inner,
                annulus_outer=self.config.guardrail.annulus_outer,
            )
            guardrail_decision.frame_id = metadata.frame_id

            # Apply guardrail decisions to escrow entry
            for layer, result in guardrail_decision.layer_decisions.items():
                if result.is_safe:
                    self.escrow_buffer.unlock_layer(metadata.frame_id, layer)
                else:
                    self.escrow_buffer.lock(metadata.frame_id)

            metrics.purgeable_layers = guardrail_decision.purgeable_layers
            metrics.locked_layers = guardrail_decision.locked_layers
        else:
            # No sources detected — all layers are purgeable
            for layer in range(1, decomp.levels + 1):
                self.escrow_buffer.unlock_layer(metadata.frame_id, layer)

        # --- Step 22: Compute retention utility (line 22) ---
        # U ← RETENTION_UTILITY(p_known, u_OOD, t)
        utility = compute_retention_utility(
            p_known=p_known,
            u_ood=u_ood,
            timestamp=metadata.timestamp,
            event_time=metadata.timestamp,  # Current time as reference
            storage_cost_bits=escrow_entry.total_bytes * 8,
            alpha=self.config.uncertainty.alpha,
            beta=self.config.uncertainty.beta,
            temporal_decay_lambda=self.config.uncertainty.temporal_decay_lambda,
        )
        escrow_entry.retention_utility = utility
        metrics.retention_utility = utility

        # --- Step 23: Resource-aware scheduling (line 23) ---
        # SCHEDULE(U, C(t))
        memory_free = 1.0 - self.escrow_buffer.occupancy_fraction
        params = self.resource_controller.update_state(
            memory_free_fraction=memory_free,
        )
        metrics.resource_mode = self.resource_controller.get_mode()
        metrics.escrow_occupancy = self.escrow_buffer.occupancy_fraction

        # Force purge if resource controller demands it
        if params.force_purge:
            self.escrow_buffer.purge_expired_unlocked(metadata.timestamp)

        # --- Steps 24-26: Check for trigger (lines 24-26) ---
        # if TRIGGER_RECEIVED then PROMOTE_HISTORY(...)
        if self.trigger_callback is not None:
            triggered = self.trigger_callback(
                metadata.frame_id, metadata.timestamp, reference_sources,
            )
            if triggered:
                metrics.triggered = True
                result = self.promotion_controller.promote_history(
                    trigger_time=metadata.timestamp,
                )
                metrics.promoted_count = len(result.promoted_ids)

                # Queue promoted entries for priority downlink
                for fid in result.promoted_ids:
                    entry = self.escrow_buffer.get(fid)
                    if entry:
                        for level, (lh, hl, hh) in entry.layers.items():
                            self.downlink_queue.enqueue_promoted(
                                fid, f"H{level}",
                                lh.nbytes + hl.nbytes + hh.nbytes,
                                entry.timestamp,
                            )

        # --- Step 27: Purge expired unlocked entries (line 27) ---
        # PURGE_EXPIRED_UNLOCKED(t - Th)
        self.escrow_buffer.purge_expired_unlocked(metadata.timestamp)

        # Simulate downlink during cadence
        self.downlink_queue.transmit(self.config.acquisition.cadence_seconds)

        # Record timing
        metrics.processing_time_ms = (time.perf_counter() - t_start) * 1000
        self._metrics.append(metrics)

        logger.debug(
            "Frame %d processed in %.1f ms: %d sources, u_OOD=%.3f, "
            "utility=%.4f, escrow=%.1f%%",
            metadata.frame_id, metrics.processing_time_ms,
            metrics.num_sources_detected, metrics.u_ood,
            metrics.retention_utility, metrics.escrow_occupancy * 100,
        )

        return metrics

    def process_sequence(
        self,
        frames: List[Tuple[NDArray, FrameMetadata]],
    ) -> PipelineResult:
        """
        Process a complete frame sequence through the pipeline.

        Parameters
        ----------
        frames : list of (frame, metadata)
            Sequence of detector frames with metadata.

        Returns
        -------
        PipelineResult with all metrics and final statistics.
        """
        logger.info("Processing sequence of %d frames", len(frames))
        t_start = time.perf_counter()

        for frame, metadata in frames:
            self.process_frame(frame, metadata)

        total_time = (time.perf_counter() - t_start) * 1000

        result = PipelineResult(
            metrics=list(self._metrics),
            promotion_results=self.promotion_controller.promotion_history,
            total_frames=len(frames),
            total_processing_time_ms=total_time,
            final_escrow_stats=self.escrow_buffer.get_statistics(),
            final_downlink_stats={
                "total_transmitted": self.downlink_queue.statistics.total_transmitted,
                "total_bytes": self.downlink_queue.statistics.total_bytes_transmitted,
                "queue_depth": self.downlink_queue.queue_depth,
            },
        )

        logger.info(
            "Sequence complete: %d frames in %.1f ms (%.1f ms/frame)",
            len(frames), total_time, total_time / max(len(frames), 1),
        )

        return result

    @property
    def metrics(self) -> List[PipelineMetrics]:
        """All collected per-frame metrics."""
        return list(self._metrics)

    def reset(self) -> None:
        """Reset pipeline state for a new sequence."""
        self.escrow_buffer = EscrowBuffer(
            capacity=self.config.escrow.capacity,
            trigger_horizon_seconds=self.config.escrow.trigger_horizon_seconds,
        )
        self.promotion_controller = PromotionController(
            escrow_buffer=self.escrow_buffer,
            default_pre_window=self.config.escrow.trigger_horizon_seconds,
        )
        self.base_layer_store.clear()
        self._metrics.clear()
