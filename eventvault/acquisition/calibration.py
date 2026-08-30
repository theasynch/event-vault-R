"""
Calibration pipeline for detector frames.

Implements dark-frame subtraction, flat-field correction,
malformed-frame detection, and metadata attachment as
described in Section IV.A of the EventVault-R proposal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
from numpy.typing import NDArray


@dataclass
class CalibrationFrames:
    """
    Pre-computed calibration reference frames.

    Attributes
    ----------
    dark : ndarray or None
        Master dark frame (same shape as science frames).
    flat : ndarray or None
        Normalized master flat field (values near 1.0).
    """
    dark: Optional[NDArray[np.float64]] = None
    flat: Optional[NDArray[np.float64]] = None


@dataclass
class QualityReport:
    """Result of frame quality checks."""
    is_valid: bool = True
    has_nan: bool = False
    saturated_fraction: float = 0.0
    shape_mismatch: bool = False
    message: str = "OK"


def create_synthetic_calibration(
    frame_shape: Tuple[int, int],
    dark_level: float = 50.0,
    flat_variation: float = 0.05,
    seed: int = 123,
) -> CalibrationFrames:
    """
    Generate synthetic calibration frames for testing.

    Parameters
    ----------
    frame_shape : (rows, cols)
    dark_level : float
        Mean dark current in ADU.
    flat_variation : float
        Peak-to-valley flat field variation (fraction).
    seed : int
        Random seed.

    Returns
    -------
    CalibrationFrames with synthetic dark and flat.
    """
    rng = np.random.default_rng(seed)

    # Dark frame: smooth gradient + noise
    rows, cols = frame_shape
    yy, xx = np.mgrid[0:rows, 0:cols]
    dark = dark_level + 5.0 * (yy / rows) + rng.normal(0, 2, frame_shape)
    dark = np.clip(dark, 0, None)

    # Flat field: smooth vignetting pattern
    cy, cx = rows / 2, cols / 2
    r2 = ((yy - cy) / rows) ** 2 + ((xx - cx) / cols) ** 2
    flat = 1.0 - flat_variation * r2 / r2.max()
    flat += rng.normal(0, 0.005, frame_shape)
    flat = np.clip(flat, 0.5, 1.5)
    flat /= flat.mean()  # Normalize to mean = 1

    return CalibrationFrames(dark=dark, flat=flat)


def check_frame_quality(
    frame: NDArray,
    expected_shape: Optional[Tuple[int, int]] = None,
    saturation_value: int = 65535,
    saturation_threshold: float = 0.01,
) -> QualityReport:
    """
    Perform quality checks on a detector frame.

    Checks for:
    - NaN or Inf values
    - Excessive saturation (>1% of pixels)
    - Shape mismatch with expected dimensions

    Parameters
    ----------
    frame : ndarray
        Input detector frame.
    expected_shape : (rows, cols), optional
        Expected frame dimensions.
    saturation_value : int
        Pixel value considered saturated.
    saturation_threshold : float
        Maximum fraction of saturated pixels.

    Returns
    -------
    QualityReport
    """
    report = QualityReport()

    # Check for NaN/Inf
    if np.any(~np.isfinite(frame)):
        report.has_nan = True
        report.is_valid = False
        report.message = "Frame contains NaN or Inf values"
        return report

    # Check shape
    if expected_shape is not None and frame.shape != expected_shape:
        report.shape_mismatch = True
        report.is_valid = False
        report.message = (
            f"Shape mismatch: expected {expected_shape}, got {frame.shape}"
        )
        return report

    # Check saturation
    sat_frac = np.mean(frame >= saturation_value)
    report.saturated_fraction = float(sat_frac)
    if sat_frac > saturation_threshold:
        report.is_valid = False
        report.message = (
            f"Excessive saturation: {sat_frac:.2%} of pixels "
            f"(threshold: {saturation_threshold:.2%})"
        )
        return report

    return report


def calibrate_frame(
    frame: NDArray,
    cal: CalibrationFrames,
    clip_negative: bool = True,
) -> NDArray[np.float64]:
    """
    Apply calibration to a raw detector frame.

    Performs:
    1. Dark-frame subtraction
    2. Flat-field correction
    3. Optional negative-value clipping

    Parameters
    ----------
    frame : ndarray
        Raw detector frame.
    cal : CalibrationFrames
        Calibration reference frames.
    clip_negative : bool
        If True, clip negative values to zero after calibration.

    Returns
    -------
    Calibrated frame as float64.
    """
    result = frame.astype(np.float64)

    # Dark subtraction
    if cal.dark is not None:
        result -= cal.dark

    # Flat-field correction
    if cal.flat is not None:
        # Avoid division by zero
        safe_flat = np.where(cal.flat > 0.01, cal.flat, 1.0)
        result /= safe_flat

    if clip_negative:
        result = np.clip(result, 0, None)

    return result
