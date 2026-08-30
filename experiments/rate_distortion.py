"""
Rate-Distortion Analysis Experiment.

Implements Section XIII.C of the proposal:
For each compression configuration, calculate:
    CR = B_raw / B_encoded  (Eq. 21)
and measure:
    ΔF = |F̂ - F_ref| / |F_ref|  (Eq. 22)
    Δx = ‖x̂_c - x_{c,ref}‖₂    (Eq. 23)

Generates rate-distortion curves in (CR, ΔF, Δx) space,
matching the illustrative template in Fig. 4 of the proposal.

Usage:
    python experiments/rate_distortion.py
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from eventvault.acquisition.synthetic import generate_frame, generate_static_sources, SourceInfo
from eventvault.codec.dwt import decompose, reconstruct, compute_compression_ratio, get_layer_sizes
from eventvault.science.source_extraction import extract_sources, measure_source


def run_rate_distortion():
    """Run the rate-distortion analysis experiment."""
    print("=" * 70)
    print("EventVault-R: Rate-Distortion Analysis")
    print("Section XIII.C — Compression vs Science Fidelity")
    print("=" * 70)

    frame_shape = (256, 256)
    num_images = 10
    wavelet_bases = ["haar", "db4", "bior4.4"]
    epsilon_F_target = 0.005  # 0.5%
    epsilon_x_target = 0.1   # 0.1 pixel

    results = {wb: {"CR": [], "delta_F": [], "delta_x": []}
               for wb in wavelet_bases}

    rng = np.random.default_rng(42)
    static_sources = generate_static_sources(30, frame_shape, rng=rng)

    print(f"\nConfiguration:")
    print(f"  Frame shape:  {frame_shape}")
    print(f"  Images:       {num_images}")
    print(f"  Wavelets:     {wavelet_bases}")
    print(f"  Target εF:    {epsilon_F_target}")
    print(f"  Target εx:    {epsilon_x_target}")

    for wavelet in wavelet_bases:
        print(f"\n{'─' * 50}")
        print(f"Wavelet: {wavelet}")

        all_cr = {d: [] for d in range(4)}  # depth 0, 1, 2, 3
        all_df = {d: [] for d in range(4)}
        all_dx = {d: [] for d in range(4)}

        for img_idx in range(num_images):
            # Generate a test image
            frame, metadata = generate_frame(
                frame_id=img_idx,
                timestamp=float(img_idx * 30),
                frame_shape=frame_shape,
                static_sources=static_sources,
                rng=np.random.default_rng(img_idx + 1000),
            )
            image = frame.astype(np.float64)

            # Full decomposition
            decomp = decompose(image, wavelet=wavelet)

            # Reference measurements from full reconstruction
            full_recon = reconstruct(decomp)
            h, w = image.shape
            full_recon = full_recon[:h, :w]
            ref_sources = extract_sources(full_recon, min_snr=5.0)

            if len(ref_sources) == 0:
                continue

            # Evaluate each reconstruction depth
            for depth in range(decomp.levels + 1):
                cr = compute_compression_ratio(image, decomp, depth)
                recon = reconstruct(decomp, max_depth=depth)
                recon = recon[:h, :w]

                # Measure all sources in the reduced reconstruction
                flux_errors = []
                centroid_errors = []

                for ref_src in ref_sources:
                    pos = (int(round(ref_src.y_centroid)),
                           int(round(ref_src.x_centroid)))
                    if (0 <= pos[0] < h and 0 <= pos[1] < w):
                        meas = measure_source(recon, pos)

                        # ΔF (Eq. 22)
                        if abs(ref_src.flux) > 1e-10:
                            df = abs(meas.flux - ref_src.flux) / abs(ref_src.flux)
                        else:
                            df = 0.0
                        flux_errors.append(df)

                        # Δx (Eq. 23)
                        dx = np.sqrt(
                            (meas.x_centroid - ref_src.x_centroid) ** 2 +
                            (meas.y_centroid - ref_src.y_centroid) ** 2
                        )
                        centroid_errors.append(dx)

                if flux_errors:
                    all_cr[depth].append(cr)
                    all_df[depth].append(np.mean(flux_errors) * 100)  # as %
                    all_dx[depth].append(np.mean(centroid_errors))

        # Aggregate results
        for depth in range(4):
            if all_cr[depth]:
                results[wavelet]["CR"].append(np.mean(all_cr[depth]))
                results[wavelet]["delta_F"].append(np.mean(all_df[depth]))
                results[wavelet]["delta_x"].append(np.mean(all_dx[depth]))

        print(f"  {'Depth':<8} {'CR':>8} {'ΔF (%)':>10} {'Δx (px)':>10}")
        print(f"  {'─' * 38}")
        for i, depth in enumerate(range(len(results[wavelet]["CR"]))):
            cr = results[wavelet]["CR"][i]
            df = results[wavelet]["delta_F"][i]
            dx = results[wavelet]["delta_x"][i]
            print(f"  {depth:<8} {cr:>8.2f} {df:>10.4f} {dx:>10.4f}")

    # ─────────────────────────────────────────────────────────
    # Generate plots (matching Fig. 4 template)
    # ─────────────────────────────────────────────────────────
    print("\nGenerating rate-distortion plots...")
    output_dir = os.path.join(os.path.dirname(__file__), "..", "results")
    os.makedirs(output_dir, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("EventVault-R: Rate-Distortion Analysis", fontsize=14, fontweight="bold")

    colors = {"haar": "#e74c3c", "db4": "#3498db", "bior4.4": "#2ecc71"}
    markers = {"haar": "o", "db4": "s", "bior4.4": "^"}

    # Plot 1: CR vs ΔF (matching Fig. 4)
    ax = axes[0]
    for wavelet in wavelet_bases:
        if results[wavelet]["CR"]:
            ax.plot(
                results[wavelet]["CR"],
                results[wavelet]["delta_F"],
                f"{markers[wavelet]}-",
                color=colors[wavelet],
                label=wavelet,
                markersize=8,
                linewidth=2,
            )

    ax.axhline(epsilon_F_target * 100, color="red", linestyle=":",
               linewidth=2, alpha=0.7, label=f"Target εF = {epsilon_F_target * 100}%")
    ax.set_xlabel("Compression Ratio", fontsize=12)
    ax.set_ylabel("Photometric Error ΔF (%)", fontsize=12)
    ax.set_title("Rate-Distortion: Flux Error")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)

    # Shade the guardrail envelope
    xlim = ax.get_xlim()
    ax.fill_between(
        [xlim[0], xlim[1]], 0, epsilon_F_target * 100,
        alpha=0.1, color="green", label="Guardrail safe zone"
    )

    # Plot 2: CR vs Δx
    ax = axes[1]
    for wavelet in wavelet_bases:
        if results[wavelet]["CR"]:
            ax.plot(
                results[wavelet]["CR"],
                results[wavelet]["delta_x"],
                f"{markers[wavelet]}-",
                color=colors[wavelet],
                label=wavelet,
                markersize=8,
                linewidth=2,
            )

    ax.axhline(epsilon_x_target, color="red", linestyle=":",
               linewidth=2, alpha=0.7, label=f"Target εx = {epsilon_x_target} px")
    ax.set_xlabel("Compression Ratio", fontsize=12)
    ax.set_ylabel("Centroid Error Δx (pixels)", fontsize=12)
    ax.set_title("Rate-Distortion: Centroid Error")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)

    xlim = ax.get_xlim()
    ax.fill_between(
        [xlim[0], xlim[1]], 0, epsilon_x_target,
        alpha=0.1, color="green"
    )

    plt.tight_layout()
    plot_path = os.path.join(output_dir, "rate_distortion.png")
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    print(f"  Saved: {plot_path}")
    plt.close()

    # ─────────────────────────────────────────────────────────
    # Summary table
    # ─────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RATE-DISTORTION SUMMARY")
    print("=" * 70)
    print(f"\n  {'Wavelet':<12} {'Depth':<8} {'CR':>8} {'ΔF (%)':>10} {'Δx (px)':>10} {'εF OK':>8} {'εx OK':>8}")
    print(f"  {'─' * 66}")
    for wavelet in wavelet_bases:
        for i in range(len(results[wavelet]["CR"])):
            cr = results[wavelet]["CR"][i]
            df = results[wavelet]["delta_F"][i]
            dx = results[wavelet]["delta_x"][i]
            ef_ok = "✓" if df <= epsilon_F_target * 100 else "✗"
            ex_ok = "✓" if dx <= epsilon_x_target else "✗"
            print(f"  {wavelet:<12} {i:<8} {cr:>8.2f} {df:>10.4f} {dx:>10.4f} {ef_ok:>8} {ex_ok:>8}")

    print(f"\n  Targets: εF ≤ {epsilon_F_target * 100}%, εx ≤ {epsilon_x_target} px")
    print(f"  Minimum compression target: ≥ 50% data reduction (CR ≥ 2.0)")
    print("\nExperiment complete.")


if __name__ == "__main__":
    run_rate_distortion()
