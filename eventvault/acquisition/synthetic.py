"""
Synthetic astronomical frame generator.

Generates 16-bit detector frames with Poisson sky background,
Gaussian read noise, injected point sources, and synthetic
transient events for controlled testing.

Implements the dataset and signal-injection strategy from Section XII
of the EventVault-R proposal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
from numpy.typing import NDArray


@dataclass
class SourceInfo:
    """Ground-truth information for a single point source."""
    x: float                  # Sub-pixel x position
    y: float                  # Sub-pixel y position
    flux: float               # Total integrated flux (ADU)
    is_transient: bool = False
    label: str = "static"


@dataclass
class FrameMetadata:
    """Metadata attached to each synthetic detector frame."""
    frame_id: int
    timestamp: float          # Seconds since start
    exposure_seconds: float
    detector_temp_K: float = 253.0
    sources: List[SourceInfo] = field(default_factory=list)


def _gaussian_psf(
    shape: Tuple[int, int],
    center: Tuple[float, float],
    fwhm: float,
    flux: float,
) -> NDArray[np.float64]:
    """
    Render a 2-D Gaussian PSF onto a grid.

    Parameters
    ----------
    shape : (rows, cols)
    center : (y, x) sub-pixel center
    fwhm : Full-width at half-maximum in pixels
    flux : Total integrated flux

    Returns
    -------
    2-D array with the rendered PSF.
    """
    sigma = fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    cy, cx = center
    r2 = (xx - cx) ** 2 + (yy - cy) ** 2
    psf = np.exp(-r2 / (2.0 * sigma ** 2))
    total = psf.sum()
    if total > 0:
        psf *= flux / total
    return psf


def generate_static_sources(
    num_sources: int,
    frame_shape: Tuple[int, int],
    flux_range: Tuple[float, float] = (500.0, 20000.0),
    rng: np.random.Generator | None = None,
) -> List[SourceInfo]:
    """
    Generate random static point sources with sub-pixel positions.

    Parameters
    ----------
    num_sources : int
        Number of sources to place.
    frame_shape : (rows, cols)
    flux_range : (min_flux, max_flux)
        Log-uniform flux distribution.
    rng : numpy Generator, optional

    Returns
    -------
    List of SourceInfo with positions and fluxes.
    """
    if rng is None:
        rng = np.random.default_rng()

    margin = 20  # Keep sources away from edges
    rows, cols = frame_shape
    sources = []
    for _ in range(num_sources):
        x = rng.uniform(margin, cols - margin)
        y = rng.uniform(margin, rows - margin)
        log_flux = rng.uniform(np.log10(flux_range[0]), np.log10(flux_range[1]))
        flux = 10.0 ** log_flux
        sources.append(SourceInfo(x=x, y=y, flux=flux, label="static"))
    return sources


def _transient_flux_at_frame(
    frame_idx: int,
    start_frame: int,
    peak_flux: float,
    rise_time_frames: int,
) -> float:
    """
    Compute transient flux at a given frame using a fast-rise profile.

    The transient rises as a half-Gaussian from start_frame,
    reaching peak_flux after rise_time_frames, then decays slowly.
    """
    if frame_idx < start_frame:
        return 0.0
    dt = frame_idx - start_frame
    if dt <= rise_time_frames:
        # Rising phase: quadratic rise
        frac = dt / rise_time_frames
        return peak_flux * frac ** 2
    else:
        # Decay phase: exponential decay
        decay_dt = dt - rise_time_frames
        tau = rise_time_frames * 2.0  # Decay timescale
        return peak_flux * np.exp(-decay_dt / tau)


def generate_frame(
    frame_id: int,
    timestamp: float,
    frame_shape: Tuple[int, int],
    static_sources: List[SourceInfo],
    psf_fwhm: float = 3.0,
    sky_background_mean: float = 200.0,
    read_noise_std: float = 10.0,
    cosmic_ray_rate: float = 0.001,
    transient_source: Optional[SourceInfo] = None,
    transient_start_frame: int = 10,
    transient_peak_flux: float = 5000.0,
    transient_rise_time_frames: int = 15,
    bit_depth: int = 16,
    rng: np.random.Generator | None = None,
) -> Tuple[NDArray[np.uint16], FrameMetadata]:
    """
    Generate a single synthetic 16-bit detector frame.

    Parameters
    ----------
    frame_id : int
        Sequential frame number.
    timestamp : float
        Time in seconds since observation start.
    frame_shape : (rows, cols)
        Detector dimensions.
    static_sources : list of SourceInfo
        Permanent point sources.
    psf_fwhm : float
        PSF full-width half-maximum in pixels.
    sky_background_mean : float
        Mean sky background in ADU.
    read_noise_std : float
        Gaussian read noise standard deviation.
    cosmic_ray_rate : float
        Cosmic rays per pixel per frame.
    transient_source : SourceInfo, optional
        If provided, inject a transient at this position.
    transient_start_frame : int
        Frame at which transient begins rising.
    transient_peak_flux : float
        Peak flux of the transient.
    transient_rise_time_frames : int
        Number of frames to reach peak.
    bit_depth : int
        Detector bit depth (for saturation clipping).
    rng : numpy Generator, optional

    Returns
    -------
    frame : uint16 array
        The synthetic detector frame.
    metadata : FrameMetadata
        Ground-truth metadata for the frame.
    """
    if rng is None:
        rng = np.random.default_rng()

    rows, cols = frame_shape
    max_val = 2 ** bit_depth - 1

    # Sky background: Poisson noise around mean
    frame = rng.poisson(lam=sky_background_mean, size=(rows, cols)).astype(np.float64)

    # Add read noise
    frame += rng.normal(0.0, read_noise_std, size=(rows, cols))

    # Build source list for this frame's metadata
    frame_sources: List[SourceInfo] = []

    # Render static sources
    for src in static_sources:
        psf = _gaussian_psf(frame_shape, (src.y, src.x), psf_fwhm, src.flux)
        # Add Poisson shot noise for the source
        psf_noisy = rng.poisson(lam=np.clip(psf, 0, None))
        frame += psf_noisy
        frame_sources.append(SourceInfo(
            x=src.x, y=src.y, flux=src.flux, label="static"
        ))

    # Inject transient
    if transient_source is not None:
        t_flux = _transient_flux_at_frame(
            frame_id, transient_start_frame,
            transient_peak_flux, transient_rise_time_frames
        )
        if t_flux > 0:
            psf = _gaussian_psf(
                frame_shape,
                (transient_source.y, transient_source.x),
                psf_fwhm, t_flux
            )
            psf_noisy = rng.poisson(lam=np.clip(psf, 0, None))
            frame += psf_noisy
            frame_sources.append(SourceInfo(
                x=transient_source.x, y=transient_source.y,
                flux=t_flux, is_transient=True, label="transient"
            ))

    # Cosmic rays: sparse hot pixels
    num_cr = rng.poisson(cosmic_ray_rate * rows * cols)
    if num_cr > 0:
        cr_y = rng.integers(0, rows, size=num_cr)
        cr_x = rng.integers(0, cols, size=num_cr)
        cr_flux = rng.uniform(1000, max_val * 0.5, size=num_cr)
        frame[cr_y, cr_x] += cr_flux

    # Clip and convert to uint16
    frame = np.clip(frame, 0, max_val).astype(np.uint16)

    metadata = FrameMetadata(
        frame_id=frame_id,
        timestamp=timestamp,
        exposure_seconds=30.0,
        sources=frame_sources,
    )

    return frame, metadata


def generate_sequence(
    num_frames: int = 60,
    cadence_seconds: float = 30.0,
    frame_shape: Tuple[int, int] = (1024, 1024),
    num_static_sources: int = 50,
    psf_fwhm: float = 3.0,
    sky_background_mean: float = 200.0,
    read_noise_std: float = 10.0,
    cosmic_ray_rate: float = 0.001,
    transient_position: Optional[Tuple[float, float]] = (512.0, 512.0),
    transient_start_frame: int = 10,
    transient_peak_flux: float = 5000.0,
    transient_rise_time_frames: int = 15,
    seed: int = 42,
) -> List[Tuple[NDArray[np.uint16], FrameMetadata]]:
    """
    Generate a complete time-series of synthetic detector frames.

    This implements the Saved Discovery test sequence (Section XIII.B):
    60 frames at 30-second cadence with a transient rising at frame 10.

    Parameters
    ----------
    num_frames : int
        Total frames in the sequence.
    cadence_seconds : float
        Time between frames.
    frame_shape : (rows, cols)
        Detector dimensions.
    num_static_sources : int
        Number of background point sources.
    transient_position : (x, y) or None
        Position of the injected transient. None = no transient.
    transient_start_frame : int
        Frame at which the transient begins rising.
    transient_peak_flux : float
        Peak transient flux.
    transient_rise_time_frames : int
        Frames to reach peak.
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    List of (frame, metadata) tuples.
    """
    rng = np.random.default_rng(seed)

    # Generate static source catalogue (same across all frames)
    static_sources = generate_static_sources(
        num_static_sources, frame_shape, rng=rng
    )

    # Transient source
    transient_source = None
    if transient_position is not None:
        transient_source = SourceInfo(
            x=transient_position[0], y=transient_position[1],
            flux=0.0, is_transient=True, label="transient"
        )

    sequence = []
    for i in range(num_frames):
        timestamp = i * cadence_seconds
        frame, meta = generate_frame(
            frame_id=i,
            timestamp=timestamp,
            frame_shape=frame_shape,
            static_sources=static_sources,
            psf_fwhm=psf_fwhm,
            sky_background_mean=sky_background_mean,
            read_noise_std=read_noise_std,
            cosmic_ray_rate=cosmic_ray_rate,
            transient_source=transient_source,
            transient_start_frame=transient_start_frame,
            transient_peak_flux=transient_peak_flux,
            transient_rise_time_frames=transient_rise_time_frames,
            rng=rng,
        )
        sequence.append((frame, meta))

    return sequence
