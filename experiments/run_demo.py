"""
Saved Discovery Experiment Runner.

The primary demonstration of EventVault-R (Section XIII.B):
- 60 frames at 30-second cadence
- Transient begins rising at T10, detected at T25
- Compares EventVault-R vs naive immediate triage
- Reports pre-trigger recovery rate

Usage:
    python experiments/saved_discovery.py
"""

from __future__ import annotations

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from eventvault.acquisition.synthetic import generate_sequence, SourceInfo
from eventvault.codec.dwt import decompose, reconstruct, compute_compression_ratio
from eventvault.config import load_config
from eventvault.pipeline import EventVaultPipeline
from eventvault.science.source_extraction import measure_source


def run_saved_discovery():
    """Run the Saved Discovery experiment and generate results."""
    print("=" * 70)
    print("EventVault-R: Saved Discovery Experiment")
    print("Section XIII.B — Primary Demonstration")
    print("=" * 70)

    config = load_config()
    cfg = config.saved_discovery

    # Use moderate-size frames
    frame_shape = (256, 256)
    config.acquisition.frame_shape = frame_shape
    config.escrow.capacity = 70
    config.escrow.trigger_horizon_seconds = 3600.0
    cfg.transient_position = [128, 128]

    print(f"\nParameters:")
    print(f"  Frames:           {cfg.num_frames}")
    print(f"  Cadence:          {cfg.cadence_seconds}s")
    print(f"  Frame size:       {frame_shape}")
    print(f"  Transient start:  frame {cfg.transient_start_frame}")
    print(f"  Transient detect: frame {cfg.transient_detect_frame}")
    print(f"  Escrow capacity:  {config.escrow.capacity}")
    print(f"  Guard εF:         {config.guardrail.epsilon_F}")
    print(f"  Guard εx:         {config.guardrail.epsilon_x}")

    # Generate sequence
    print("\nGenerating 60-frame observation sequence...")
    sequence = generate_sequence(
        num_frames=cfg.num_frames,
        cadence_seconds=cfg.cadence_seconds,
        frame_shape=frame_shape,
        num_static_sources=30,
        transient_position=tuple(cfg.transient_position),
        transient_start_frame=cfg.transient_start_frame,
        transient_peak_flux=cfg.transient_peak_flux,
        transient_rise_time_frames=cfg.transient_rise_time_frames,
        seed=42,
    )

    # ─────────────────────────────────────────────────────────
    # 1. EventVault-R pipeline
    # ─────────────────────────────────────────────────────────
    print("\n" + "─" * 50)
    print("Running EventVault-R pipeline...")

    def trigger_at_t25(frame_id, timestamp, sources):
        return frame_id == cfg.transient_detect_frame

    ev_pipeline = EventVaultPipeline(
        config=config,
        trigger_callback=trigger_at_t25,
    )
    ev_result = ev_pipeline.process_sequence(sequence)

    # Collect promoted frame IDs
    ev_promoted = set()
    for pr in ev_result.promotion_results:
        ev_promoted.update(pr.promoted_ids)

    pre_trigger_frames = set(range(cfg.transient_start_frame, cfg.transient_detect_frame))
    ev_recovered = pre_trigger_frames & ev_promoted
    ev_recovery_rate = len(ev_recovered) / max(len(pre_trigger_frames), 1)

    print(f"  Pre-trigger frames:    {sorted(pre_trigger_frames)}")
    print(f"  Promoted frames:       {sorted(ev_promoted)}")
    print(f"  Recovered pre-trigger: {sorted(ev_recovered)}")
    print(f"  Recovery rate:         {ev_recovery_rate:.1%}")
    print(f"  Buffer overflows:      {ev_pipeline.escrow_buffer.uncontrolled_losses}")

    # ─────────────────────────────────────────────────────────
    # 2. Naive triage baseline
    # ─────────────────────────────────────────────────────────
    print("\n" + "─" * 50)
    print("Running naive triage baseline...")

    detection_threshold = cfg.transient_peak_flux * 0.3
    transient_pos = (int(cfg.transient_position[1]), int(cfg.transient_position[0]))
    naive_kept = []

    for frame, metadata in sequence:
        image = frame.astype(np.float64)
        meas = measure_source(image, transient_pos, aperture_radius=5.0)
        if meas.flux > detection_threshold:
            naive_kept.append(metadata.frame_id)

    naive_recovered = pre_trigger_frames & set(naive_kept)
    naive_recovery_rate = len(naive_recovered) / max(len(pre_trigger_frames), 1)

    print(f"  Detection threshold:   {detection_threshold:.0f} ADU")
    print(f"  Frames kept:           {len(naive_kept)}")
    print(f"  Pre-trigger recovered: {sorted(naive_recovered)}")
    print(f"  Recovery rate:         {naive_recovery_rate:.1%}")

    # ─────────────────────────────────────────────────────────
    # 3. Results comparison
    # ─────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RESULTS COMPARISON")
    print("=" * 70)
    print(f"  {'Metric':<30} {'EventVault-R':>15} {'Naive Triage':>15}")
    print(f"  {'─' * 60}")
    print(f"  {'Pre-trigger recovery':<30} {ev_recovery_rate:>14.1%} {naive_recovery_rate:>14.1%}")
    print(f"  {'Frames in escrow':<30} {ev_pipeline.escrow_buffer.size:>15d} {'N/A':>15}")
    print(f"  {'Buffer overflows':<30} {ev_pipeline.escrow_buffer.uncontrolled_losses:>15d} {'N/A':>15}")
    print(f"  {'Promoted for downlink':<30} {len(ev_promoted):>15d} {len(naive_kept):>15d}")

    # ─────────────────────────────────────────────────────────
    # 4. Generate plots
    # ─────────────────────────────────────────────────────────
    print("\nGenerating plots...")
    output_dir = os.path.join(os.path.dirname(__file__), "..", "results")
    os.makedirs(output_dir, exist_ok=True)

    # Light curve plot
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("EventVault-R: Saved Discovery Experiment", fontsize=14, fontweight="bold")

    # Plot 1: Transient light curve
    ax = axes[0, 0]
    transient_fluxes = []
    for frame, meta in sequence:
        image = frame.astype(np.float64)
        meas = measure_source(image, transient_pos, aperture_radius=5.0)
        transient_fluxes.append(meas.flux)

    frames_x = np.arange(cfg.num_frames)
    ax.plot(frames_x, transient_fluxes, "b.-", label="Measured flux")
    ax.axvline(cfg.transient_start_frame, color="g", linestyle="--", alpha=0.7, label="Transient start (T10)")
    ax.axvline(cfg.transient_detect_frame, color="r", linestyle="--", alpha=0.7, label="Detection (T25)")
    ax.axhline(detection_threshold, color="orange", linestyle=":", alpha=0.7, label="Naive threshold")
    ax.set_xlabel("Frame")
    ax.set_ylabel("Flux (ADU)")
    ax.set_title("Transient Light Curve")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # Plot 2: Recovery comparison
    ax = axes[0, 1]
    categories = ["EventVault-R", "Naive Triage"]
    rates = [ev_recovery_rate * 100, naive_recovery_rate * 100]
    colors = ["#2ecc71", "#e74c3c"]
    bars = ax.bar(categories, rates, color=colors, edgecolor="black")
    ax.set_ylabel("Recovery Rate (%)")
    ax.set_title("Pre-Trigger Recovery Rate")
    ax.set_ylim(0, 110)
    for bar, rate in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                f"{rate:.0f}%", ha="center", fontweight="bold")
    ax.axhline(100, color="green", linestyle=":", alpha=0.5, label="Target: 100%")
    ax.legend()

    # Plot 3: Escrow occupancy over time
    ax = axes[1, 0]
    occupancies = [m.escrow_occupancy * 100 for m in ev_result.metrics]
    ax.plot(frames_x, occupancies, "m.-")
    ax.axvline(cfg.transient_detect_frame, color="r", linestyle="--", alpha=0.7, label="Trigger")
    ax.set_xlabel("Frame")
    ax.set_ylabel("Escrow Occupancy (%)")
    ax.set_title("Escrow Buffer Occupancy")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Plot 4: Uncertainty scores
    ax = axes[1, 1]
    u_oods = [m.u_ood for m in ev_result.metrics]
    ax.plot(frames_x, u_oods, "r.-", label="U_OOD")
    p_knowns = [m.p_known for m in ev_result.metrics]
    ax.plot(frames_x, p_knowns, "b.-", label="P_known")
    ax.axvline(cfg.transient_start_frame, color="g", linestyle="--", alpha=0.7)
    ax.axvline(cfg.transient_detect_frame, color="r", linestyle="--", alpha=0.7)
    ax.set_xlabel("Frame")
    ax.set_ylabel("Score")
    ax.set_title("Uncertainty Estimation")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plot_path = os.path.join(output_dir, "saved_discovery_results.png")
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    print(f"  Saved: {plot_path}")
    plt.close()

    print("\nExperiment complete.")
    return ev_recovery_rate, naive_recovery_rate


if __name__ == "__main__":
    run_saved_discovery()
