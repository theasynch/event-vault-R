"""
Progressive 3-level 2-D Discrete Wavelet Transform codec.

Implements the wavelet decomposition/reconstruction described in
Section V of the EventVault-R proposal:

    {L0, H1, H2, H3} = DWT^(3)_2D(I)

where L0 is the coarse approximation and Hk = {LHk, HLk, HHk}
are directional detail coefficients at decomposition level k.

Key requirement: every prefix of the encoded stream must produce
a valid reconstruction (Eq. 9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pywt
from numpy.typing import NDArray


@dataclass
class WaveletDecomposition:
    """
    Result of a multi-level 2-D wavelet decomposition.

    Attributes
    ----------
    base_layer : ndarray
        L0 — the coarse approximation coefficients.
    residual_layers : dict
        {level: (LH, HL, HH)} detail coefficient tuples
        for levels 1 through decomposition_levels.
    wavelet : str
        Wavelet name used.
    mode : str
        Boundary extension mode.
    levels : int
        Number of decomposition levels.
    original_shape : tuple
        Shape of the original image.
    coeff_slices : list
        PyWavelets coefficient slices for reconstruction.
    """
    base_layer: NDArray[np.float64]
    residual_layers: Dict[int, Tuple[NDArray, NDArray, NDArray]]
    wavelet: str
    mode: str
    levels: int
    original_shape: Tuple[int, int]
    coeff_slices: list = field(default_factory=list)
    # Internal: full coefficient list for reconstruction
    _pywt_coeffs: list = field(default_factory=list, repr=False)


def decompose(
    image: NDArray,
    wavelet: str = "bior4.4",
    levels: int = 3,
    mode: str = "symmetric",
) -> WaveletDecomposition:
    """
    Perform a multi-level 2-D DWT decomposition.

    Parameters
    ----------
    image : ndarray
        Input 2-D image (M×N).
    wavelet : str
        Wavelet name (e.g., 'bior4.4', 'db4', 'haar').
    levels : int
        Number of decomposition levels (default: 3).
    mode : str
        Signal extension mode for boundary handling.

    Returns
    -------
    WaveletDecomposition
        Contains base layer L0 and residual layers H1..H3.

    Notes
    -----
    Uses PyWavelets' wavedec2 which returns coefficients in the format:
        [cA_n, (cH_n, cV_n, cD_n), ..., (cH_1, cV_1, cD_1)]
    where n = number of levels.

    We map this to our notation:
        L0 = cA_n (coarse approximation)
        H_k = (LH_k, HL_k, HH_k) = (cH_k, cV_k, cD_k)
    """
    image = image.astype(np.float64)
    original_shape = image.shape

    # Perform multi-level 2-D DWT
    coeffs = pywt.wavedec2(image, wavelet, mode=mode, level=levels)

    # coeffs[0] = approximation at deepest level (L0)
    # coeffs[1] = (LH_deepest, HL_deepest, HH_deepest) = H_deepest
    # ...
    # coeffs[levels] = (LH_1, HL_1, HH_1) = H_1

    base_layer = coeffs[0]

    # Map PyWavelets ordering to our level numbering:
    # PyWavelets: [cA_n, details_n, details_{n-1}, ..., details_1]
    # Our notation: H1 = finest detail, H3 = coarsest detail (for levels=3)
    # PyWavelets details_n (index 1) = coarsest = our H_levels
    # PyWavelets details_1 (index levels) = finest = our H_1
    residual_layers = {}
    for i in range(1, levels + 1):
        # PyWavelets index i corresponds to our level (levels - i + 1)
        # But for simplicity, let's use: level k where k=1 is coarsest detail
        # k=1 -> pywt index 1 (coarsest detail, closest to approx)
        # k=2 -> pywt index 2
        # k=3 -> pywt index 3 (finest detail)
        detail_tuple = coeffs[i]  # (LH, HL, HH) at this level
        residual_layers[i] = detail_tuple

    return WaveletDecomposition(
        base_layer=base_layer,
        residual_layers=residual_layers,
        wavelet=wavelet,
        mode=mode,
        levels=levels,
        original_shape=original_shape,
        _pywt_coeffs=coeffs,
    )


def reconstruct(
    decomp: WaveletDecomposition,
    max_depth: Optional[int] = None,
) -> NDArray[np.float64]:
    """
    Reconstruct an image from wavelet coefficients up to a given depth.

    Implements Eq. 9 from the proposal:
        Î_D = IDWT_2D(L0 + Σ_{k=1}^{D} R_k)

    Parameters
    ----------
    decomp : WaveletDecomposition
        Wavelet decomposition result.
    max_depth : int, optional
        Maximum detail level to include (1-indexed).
        - None or levels: full reconstruction (all detail)
        - 0: base layer only (coarsest approximation)
        - D: include detail levels 1 through D

    Returns
    -------
    Reconstructed 2-D image.

    Notes
    -----
    For progressive reconstruction:
        depth=0: reconstruct from L0 only (very coarse)
        depth=1: L0 + H1 (coarse detail added)
        depth=2: L0 + H1 + H2
        depth=3: L0 + H1 + H2 + H3 (full reconstruction)

    Every prefix produces a valid image — this is the key
    progressive property.
    """
    if max_depth is None:
        max_depth = decomp.levels

    max_depth = min(max_depth, decomp.levels)

    if max_depth == decomp.levels:
        # Full reconstruction — use all coefficients
        return pywt.waverec2(decomp._pywt_coeffs, decomp.wavelet, mode=decomp.mode)

    if max_depth == 0:
        # Base-layer-only reconstruction
        # Create coefficient list with only the approximation,
        # zeroing out all detail levels
        coeffs = [decomp.base_layer]
        for k in range(1, decomp.levels + 1):
            lh, hl, hh = decomp.residual_layers[k]
            coeffs.append((
                np.zeros_like(lh),
                np.zeros_like(hl),
                np.zeros_like(hh),
            ))
        return pywt.waverec2(coeffs, decomp.wavelet, mode=decomp.mode)

    # Partial reconstruction: include levels 1..max_depth, zero the rest
    coeffs = [decomp.base_layer]
    for k in range(1, decomp.levels + 1):
        if k <= max_depth:
            # Include this detail level
            coeffs.append(decomp.residual_layers[k])
        else:
            # Zero out this detail level
            lh, hl, hh = decomp.residual_layers[k]
            coeffs.append((
                np.zeros_like(lh),
                np.zeros_like(hl),
                np.zeros_like(hh),
            ))

    return pywt.waverec2(coeffs, decomp.wavelet, mode=decomp.mode)


def get_layer_sizes(decomp: WaveletDecomposition) -> Dict[str, int]:
    """
    Compute the byte sizes of each layer in the decomposition.

    Returns
    -------
    Dict mapping layer name to size in bytes.
        'base': size of L0
        'H1', 'H2', 'H3': size of each residual layer
        'total': sum of all layers
    """
    sizes = {}
    sizes["base"] = decomp.base_layer.nbytes

    total = sizes["base"]
    for k in range(1, decomp.levels + 1):
        lh, hl, hh = decomp.residual_layers[k]
        layer_size = lh.nbytes + hl.nbytes + hh.nbytes
        sizes[f"H{k}"] = layer_size
        total += layer_size

    sizes["total"] = total
    return sizes


def compute_compression_ratio(
    original_image: NDArray,
    decomp: WaveletDecomposition,
    retained_depth: int,
) -> float:
    """
    Compute the compression ratio for a given retained depth.

    CR = B_raw / B_encoded  (Eq. 21)

    Parameters
    ----------
    original_image : ndarray
        Original image for raw size reference.
    decomp : WaveletDecomposition
        Wavelet decomposition.
    retained_depth : int
        Number of detail levels retained (0 = base only).

    Returns
    -------
    Compression ratio (>1 means compression).
    """
    raw_bytes = original_image.nbytes

    # Encoded size = base layer + retained detail layers
    encoded_bytes = decomp.base_layer.nbytes
    for k in range(1, min(retained_depth, decomp.levels) + 1):
        lh, hl, hh = decomp.residual_layers[k]
        encoded_bytes += lh.nbytes + hl.nbytes + hh.nbytes

    if encoded_bytes == 0:
        return float("inf")
    return raw_bytes / encoded_bytes
