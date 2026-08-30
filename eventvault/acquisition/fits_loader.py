"""
FITS file loader for EventVault-R.

Provides ingestion of FITS astronomical images with metadata
extraction. Supports both single-extension and multi-extension
FITS files.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from numpy.typing import NDArray

try:
    from astropy.io import fits as astropy_fits
    HAS_ASTROPY = True
except ImportError:
    HAS_ASTROPY = False

from eventvault.acquisition.synthetic import FrameMetadata, SourceInfo


def load_fits_frame(
    filepath: str | Path,
    extension: int = 0,
) -> Tuple[NDArray, FrameMetadata]:
    """
    Load a single FITS image and extract metadata.

    Parameters
    ----------
    filepath : str or Path
        Path to the FITS file.
    extension : int
        HDU extension index.

    Returns
    -------
    frame : ndarray
        Image data as a 2-D array.
    metadata : FrameMetadata
        Extracted metadata from FITS headers.

    Raises
    ------
    ImportError
        If astropy is not installed.
    FileNotFoundError
        If the FITS file does not exist.
    """
    if not HAS_ASTROPY:
        raise ImportError(
            "astropy is required for FITS loading. "
            "Install with: pip install astropy"
        )

    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"FITS file not found: {filepath}")

    with astropy_fits.open(filepath) as hdul:
        data = hdul[extension].data.astype(np.float64)
        header = hdul[extension].header

        # Extract metadata from FITS header
        metadata = FrameMetadata(
            frame_id=header.get("FRAMEID", 0),
            timestamp=header.get("MJD-OBS", 0.0),
            exposure_seconds=header.get("EXPTIME", 0.0),
            detector_temp_K=header.get("DETTEMP", 253.0),
        )

    return data, metadata


def load_fits_sequence(
    directory: str | Path,
    pattern: str = "*.fits",
    max_frames: Optional[int] = None,
) -> List[Tuple[NDArray, FrameMetadata]]:
    """
    Load a sequence of FITS files from a directory.

    Parameters
    ----------
    directory : str or Path
        Directory containing FITS files.
    pattern : str
        Glob pattern for FITS files.
    max_frames : int, optional
        Maximum number of frames to load.

    Returns
    -------
    List of (frame, metadata) tuples, sorted by filename.
    """
    directory = Path(directory)
    fits_files = sorted(directory.glob(pattern))

    if max_frames is not None:
        fits_files = fits_files[:max_frames]

    sequence = []
    for i, fp in enumerate(fits_files):
        frame, meta = load_fits_frame(fp)
        # Override frame_id with sequential index
        meta.frame_id = i
        sequence.append((frame, meta))

    return sequence
