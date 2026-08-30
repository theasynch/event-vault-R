"""
Source extraction for astronomical images.

Detects point sources from (potentially coarse) wavelet reconstructions,
performs aperture photometry to measure background-subtracted flux,
and computes source centroids.

Implements the scientific observables from Section VI of the proposal:
    F = Σ_{(x,y)∈Ω} [I(x,y) - B(x,y)]     (Eq. 11)
    x̄ = Σ_Ω x[I(x,y) - B(x,y)] / F         (Eq. 12)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import label, maximum_filter, uniform_filter


@dataclass
class SourceMeasurement:
    """
    Measured properties of a detected astronomical source.

    Attributes
    ----------
    x_centroid : float
        x-position centroid (sub-pixel).
    y_centroid : float
        y-position centroid (sub-pixel).
    flux : float
        Background-subtracted aperture flux.
    snr : float
        Signal-to-noise ratio estimate.
    peak_value : float
        Peak pixel value in the aperture.
    aperture_npix : int
        Number of pixels in the aperture.
    background_mean : float
        Estimated local background per pixel.
    """
    x_centroid: float
    y_centroid: float
    flux: float
    snr: float
    peak_value: float
    aperture_npix: int
    background_mean: float


def estimate_background(
    image: NDArray[np.float64],
    box_size: int = 64,
) -> NDArray[np.float64]:
    """
    Estimate a smooth background map using local median filtering.

    Parameters
    ----------
    image : 2-D ndarray
        Input image.
    box_size : int
        Size of the local estimation box.

    Returns
    -------
    Background estimate, same shape as input.
    """
    # Use uniform filter as a fast approximation to local background
    # A more sophisticated approach would use sigma-clipped statistics
    bg = uniform_filter(image.astype(np.float64), size=box_size)
    return bg


def detect_sources(
    image: NDArray[np.float64],
    background: Optional[NDArray[np.float64]] = None,
    threshold_sigma: float = 5.0,
    min_separation: int = 5,
) -> List[Tuple[int, int]]:
    """
    Detect point sources above a threshold.

    Uses local maximum detection on the background-subtracted image.

    Parameters
    ----------
    image : 2-D ndarray
        Input image (calibrated).
    background : 2-D ndarray, optional
        Background estimate. If None, computed automatically.
    threshold_sigma : float
        Detection threshold in units of background noise.
    min_separation : int
        Minimum pixel separation between detected sources.

    Returns
    -------
    List of (y, x) pixel positions of detected sources.
    """
    if background is None:
        background = estimate_background(image)

    # Background-subtracted image
    subtracted = image - background

    # Estimate noise from background RMS
    # Use median absolute deviation for robustness
    noise = np.median(np.abs(subtracted)) * 1.4826  # MAD → σ
    if noise <= 0:
        noise = 1.0

    threshold = threshold_sigma * noise

    # Find local maxima
    local_max = maximum_filter(subtracted, size=min_separation)
    detected = (subtracted == local_max) & (subtracted > threshold)

    # Get positions
    positions = np.argwhere(detected)  # (y, x) format
    return [(int(y), int(x)) for y, x in positions]


def measure_source(
    image: NDArray[np.float64],
    position: Tuple[int, int],
    aperture_radius: float = 5.0,
    annulus_inner: float = 7.0,
    annulus_outer: float = 12.0,
) -> SourceMeasurement:
    """
    Perform aperture photometry and centroid measurement on a source.

    Implements Equations 11-12 from the proposal:
    - Flux: F = Σ_{Ω} [I(x,y) - B(x,y)]
    - Centroid: x̄ = Σ_Ω x·[I(x,y) - B(x,y)] / F

    Parameters
    ----------
    image : 2-D ndarray
        Input image.
    position : (y, x)
        Approximate source position.
    aperture_radius : float
        Circular aperture radius in pixels.
    annulus_inner : float
        Inner radius of background annulus.
    annulus_outer : float
        Outer radius of background annulus.

    Returns
    -------
    SourceMeasurement with flux, centroid, and SNR.
    """
    cy, cx = position
    rows, cols = image.shape

    # Create coordinate grids relative to source center
    y_grid, x_grid = np.mgrid[
        max(0, int(cy - annulus_outer - 1)):min(rows, int(cy + annulus_outer + 2)),
        max(0, int(cx - annulus_outer - 1)):min(cols, int(cx + annulus_outer + 2)),
    ]

    # Distance from center
    r = np.sqrt((x_grid - cx) ** 2 + (y_grid - cy) ** 2)

    # Extract sub-image
    y_slice = slice(
        max(0, int(cy - annulus_outer - 1)),
        min(rows, int(cy + annulus_outer + 2))
    )
    x_slice = slice(
        max(0, int(cx - annulus_outer - 1)),
        min(cols, int(cx + annulus_outer + 2))
    )
    sub_image = image[y_slice, x_slice].astype(np.float64)

    # Background estimation from annulus
    annulus_mask = (r >= annulus_inner) & (r <= annulus_outer)
    if annulus_mask.any():
        bg_values = sub_image[annulus_mask]
        # Sigma-clipped mean
        bg_mean = np.median(bg_values)
        bg_std = np.std(bg_values)
    else:
        bg_mean = 0.0
        bg_std = 1.0

    # Aperture mask
    aperture_mask = r <= aperture_radius
    aperture_npix = int(aperture_mask.sum())

    if aperture_npix == 0:
        return SourceMeasurement(
            x_centroid=float(cx),
            y_centroid=float(cy),
            flux=0.0,
            snr=0.0,
            peak_value=0.0,
            aperture_npix=0,
            background_mean=bg_mean,
        )

    # Background-subtracted values in aperture
    aperture_values = sub_image[aperture_mask] - bg_mean

    # Total flux (Eq. 11)
    flux = float(np.sum(aperture_values))

    # Peak value
    peak_value = float(np.max(sub_image[aperture_mask]))

    # Centroid (Eq. 12)
    if flux > 0:
        weights = np.clip(aperture_values, 0, None)  # Use only positive values
        w_sum = weights.sum()
        if w_sum > 0:
            x_centroid = float(np.sum(x_grid[aperture_mask] * weights) / w_sum)
            y_centroid = float(np.sum(y_grid[aperture_mask] * weights) / w_sum)
        else:
            x_centroid = float(cx)
            y_centroid = float(cy)
    else:
        x_centroid = float(cx)
        y_centroid = float(cy)

    # SNR estimation
    noise_sq = aperture_npix * (bg_std ** 2 + bg_mean)  # Poisson + read noise
    snr = flux / np.sqrt(noise_sq) if noise_sq > 0 else 0.0

    return SourceMeasurement(
        x_centroid=x_centroid,
        y_centroid=y_centroid,
        flux=flux,
        snr=float(snr),
        peak_value=peak_value,
        aperture_npix=aperture_npix,
        background_mean=bg_mean,
    )


def extract_sources(
    image: NDArray[np.float64],
    min_snr: float = 5.0,
    aperture_radius: float = 5.0,
    annulus_inner: float = 7.0,
    annulus_outer: float = 12.0,
    threshold_sigma: float = 5.0,
) -> List[SourceMeasurement]:
    """
    Full source extraction pipeline: detect + measure.

    Parameters
    ----------
    image : 2-D ndarray
        Calibrated image.
    min_snr : float
        Minimum SNR to include a source.
    aperture_radius, annulus_inner, annulus_outer : float
        Photometry aperture parameters.
    threshold_sigma : float
        Detection threshold.

    Returns
    -------
    List of SourceMeasurement for all detected sources above min_snr.
    """
    background = estimate_background(image)
    positions = detect_sources(image, background, threshold_sigma)

    sources = []
    for pos in positions:
        meas = measure_source(
            image, pos,
            aperture_radius=aperture_radius,
            annulus_inner=annulus_inner,
            annulus_outer=annulus_outer,
        )
        if meas.snr >= min_snr:
            sources.append(meas)

    return sources
