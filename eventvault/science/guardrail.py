"""
Science Guardrail for EventVault-R.

Implements the deletion condition from Section VI of the proposal:

    |F̂_D - F_ref| / |F_ref| ≤ ε_F  AND  ‖x̂_{c,D} - x_{c,ref}‖₂ ≤ ε_x
    (Eq. 13)

The guardrail evaluates residual layers in reverse detail order
(Section VI.C): if removing H3 is safe but removing H2 violates
the error bound, H3 may be purged while H2 remains locked.

This gives the controller fine-grained control rather than a
binary frame-level deletion decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
from numpy.typing import NDArray

from eventvault.codec.dwt import WaveletDecomposition, reconstruct
from eventvault.science.source_extraction import (
    SourceMeasurement,
    extract_sources,
    measure_source,
)


@dataclass
class GuardrailResult:
    """
    Result of the Science Guardrail evaluation for a single layer.

    Attributes
    ----------
    layer : int
        Layer index evaluated (1-indexed detail level).
    is_safe : bool
        True if removing this layer maintains science bounds.
    max_flux_error : float
        Maximum relative flux error across all sources.
    max_centroid_error : float
        Maximum centroid displacement across all sources.
    num_sources_evaluated : int
        Number of sources used in the evaluation.
    violations : list
        Details of sources that violated bounds.
    """
    layer: int
    is_safe: bool
    max_flux_error: float
    max_centroid_error: float
    num_sources_evaluated: int
    violations: List[dict]


@dataclass
class FrameGuardrailDecision:
    """
    Complete guardrail decision for one frame.

    Attributes
    ----------
    frame_id : int
        Frame identifier.
    layer_decisions : dict
        {layer_idx: GuardrailResult} for each evaluated layer.
    purgeable_layers : list
        Layer indices that can be safely purged.
    locked_layers : list
        Layer indices that must be retained.
    """
    frame_id: int
    layer_decisions: Dict[int, GuardrailResult]
    purgeable_layers: List[int]
    locked_layers: List[int]


def _compute_flux_error(measured: float, reference: float) -> float:
    """Relative flux error: |F̂ - F_ref| / |F_ref|."""
    if abs(reference) < 1e-10:
        return 0.0 if abs(measured) < 1e-10 else float("inf")
    return abs(measured - reference) / abs(reference)


def _compute_centroid_error(
    measured: Tuple[float, float],
    reference: Tuple[float, float],
) -> float:
    """Centroid error: ‖x̂_c - x_{c,ref}‖₂."""
    dx = measured[0] - reference[0]
    dy = measured[1] - reference[1]
    return np.sqrt(dx ** 2 + dy ** 2)


def evaluate_layer(
    decomp: WaveletDecomposition,
    layer: int,
    reference_sources: List[SourceMeasurement],
    epsilon_F: float = 0.005,
    epsilon_x: float = 0.1,
    aperture_radius: float = 5.0,
    annulus_inner: float = 7.0,
    annulus_outer: float = 12.0,
) -> GuardrailResult:
    """
    Evaluate whether a specific residual layer can be safely removed.

    Reconstructs the image without the specified layer (and finer layers),
    then measures all reference sources and checks the science bounds.

    Parameters
    ----------
    decomp : WaveletDecomposition
        Full wavelet decomposition.
    layer : int
        Layer to evaluate for removal (1-indexed).
        Evaluating layer D means: "is reconstruction with
        only layers 1..D-1 (without D and finer) acceptable?"
    reference_sources : list of SourceMeasurement
        Source measurements from the full-fidelity reconstruction.
    epsilon_F : float
        Maximum allowed relative flux error (default 0.5%).
    epsilon_x : float
        Maximum allowed centroid error in pixels (default 0.1).

    Returns
    -------
    GuardrailResult
    """
    # Reconstruct with depth = layer-1 (excluding this layer and finer)
    recon_depth = layer - 1
    reconstructed = reconstruct(decomp, max_depth=recon_depth)

    violations = []
    max_flux_err = 0.0
    max_centroid_err = 0.0

    for ref_src in reference_sources:
        # Measure the same source in the reduced reconstruction
        position = (int(round(ref_src.y_centroid)), int(round(ref_src.x_centroid)))

        # Bounds check
        if (position[0] < 0 or position[0] >= reconstructed.shape[0] or
                position[1] < 0 or position[1] >= reconstructed.shape[1]):
            continue

        meas = measure_source(
            reconstructed, position,
            aperture_radius=aperture_radius,
            annulus_inner=annulus_inner,
            annulus_outer=annulus_outer,
        )

        flux_err = _compute_flux_error(meas.flux, ref_src.flux)
        centroid_err = _compute_centroid_error(
            (meas.x_centroid, meas.y_centroid),
            (ref_src.x_centroid, ref_src.y_centroid),
        )

        max_flux_err = max(max_flux_err, flux_err)
        max_centroid_err = max(max_centroid_err, centroid_err)

        # Check bounds (Eq. 13)
        if flux_err > epsilon_F or centroid_err > epsilon_x:
            violations.append({
                "source_x": ref_src.x_centroid,
                "source_y": ref_src.y_centroid,
                "ref_flux": ref_src.flux,
                "meas_flux": meas.flux,
                "flux_error": flux_err,
                "centroid_error": centroid_err,
            })

    is_safe = len(violations) == 0

    return GuardrailResult(
        layer=layer,
        is_safe=is_safe,
        max_flux_error=max_flux_err,
        max_centroid_error=max_centroid_err,
        num_sources_evaluated=len(reference_sources),
        violations=violations,
    )


def evaluate_frame(
    decomp: WaveletDecomposition,
    reference_sources: List[SourceMeasurement],
    epsilon_F: float = 0.005,
    epsilon_x: float = 0.1,
    aperture_radius: float = 5.0,
    annulus_inner: float = 7.0,
    annulus_outer: float = 12.0,
) -> FrameGuardrailDecision:
    """
    Evaluate all residual layers for a single frame.

    Layers are evaluated in reverse detail order (Section VI.C):
    finest first (H3 → H2 → H1). This allows fine-grained control
    where the outermost layer might be purgeable while inner layers
    must be retained.

    Parameters
    ----------
    decomp : WaveletDecomposition
        Full wavelet decomposition of the frame.
    reference_sources : list of SourceMeasurement
        Source measurements from the full-fidelity reconstruction.
    epsilon_F : float
        Flux error bound.
    epsilon_x : float
        Centroid error bound.

    Returns
    -------
    FrameGuardrailDecision
    """
    layer_decisions = {}
    purgeable = []
    locked = []

    # Evaluate from finest (outermost) to coarsest
    # For 3-level decomposition: evaluate H3, H2, H1
    for layer in range(decomp.levels, 0, -1):
        result = evaluate_layer(
            decomp, layer, reference_sources,
            epsilon_F=epsilon_F,
            epsilon_x=epsilon_x,
            aperture_radius=aperture_radius,
            annulus_inner=annulus_inner,
            annulus_outer=annulus_outer,
        )
        layer_decisions[layer] = result

        if result.is_safe:
            purgeable.append(layer)
        else:
            locked.append(layer)
            # If removing layer D is not safe, all finer layers
            # (D+1, D+2, ...) that were marked purgeable remain so,
            # but we lock everything from D down to 1
            for inner_layer in range(layer - 1, 0, -1):
                if inner_layer not in layer_decisions:
                    # Don't need to evaluate: it's automatically locked
                    layer_decisions[inner_layer] = GuardrailResult(
                        layer=inner_layer,
                        is_safe=False,
                        max_flux_error=float("inf"),
                        max_centroid_error=float("inf"),
                        num_sources_evaluated=0,
                        violations=[{"reason": "locked by parent layer"}],
                    )
                    locked.append(inner_layer)
            break

    return FrameGuardrailDecision(
        frame_id=0,  # Set by caller
        layer_decisions=layer_decisions,
        purgeable_layers=sorted(purgeable, reverse=True),
        locked_layers=sorted(locked),
    )
