"""
Configuration loader for EventVault-R.

Loads parameters from YAML config files into typed dataclasses
for compile-time-like safety and IDE autocomplete.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

import yaml


# ---------------------------------------------------------------------------
# Dataclass hierarchy — mirrors config/default.yaml
# ---------------------------------------------------------------------------

@dataclass
class CodecConfig:
    """Progressive encoder parameters (Section V)."""
    wavelet: str = "bior4.4"
    decomposition_levels: int = 3
    mode: str = "symmetric"
    use_integer_lifting: bool = False


@dataclass
class GuardrailConfig:
    """Science Guardrail parameters (Section VI)."""
    epsilon_F: float = 0.005
    epsilon_x: float = 0.1
    min_source_snr: float = 5.0
    aperture_radius: float = 5.0
    annulus_inner: float = 7.0
    annulus_outer: float = 12.0


@dataclass
class EscrowConfig:
    """Escrow buffer parameters (Section IV.D)."""
    capacity: int = 100
    trigger_horizon_seconds: float = 1800.0
    ecc_enabled: bool = True


@dataclass
class UncertaintyConfig:
    """Uncertainty & retention parameters (Section VII)."""
    method: str = "softmax_entropy"
    alpha: float = 1.0
    beta: float = 1.5
    temporal_decay_lambda: float = 0.01


@dataclass
class ResourceConfig:
    """Joint resource controller parameters (Section IX)."""
    memory_warning_fraction: float = 0.7
    memory_critical_fraction: float = 0.9
    min_horizon_seconds: float = 300.0
    min_detail_level: int = 1


@dataclass
class TelemetryConfig:
    """Telemetry & downlink parameters."""
    downlink_bandwidth_bps: int = 9600
    max_queue_depth: int = 50


@dataclass
class AcquisitionConfig:
    """Acquisition & calibration parameters (Section IV.A)."""
    frame_shape: Tuple[int, int] = (1024, 1024)
    bit_depth: int = 16
    cadence_seconds: float = 30.0


@dataclass
class SyntheticConfig:
    """Synthetic data generation parameters (Section XII)."""
    sky_background_mean: float = 200.0
    read_noise_std: float = 10.0
    num_static_sources: int = 50
    psf_fwhm: float = 3.0
    cosmic_ray_rate: float = 0.001


@dataclass
class SavedDiscoveryConfig:
    """Saved Discovery test parameters (Section XIII.B)."""
    num_frames: int = 60
    cadence_seconds: float = 30.0
    transient_start_frame: int = 10
    transient_detect_frame: int = 25
    transient_peak_flux: float = 5000.0
    transient_rise_time_frames: int = 15
    transient_position: Tuple[int, int] = (512, 512)


@dataclass
class EventVaultConfig:
    """Top-level configuration container."""
    codec: CodecConfig = field(default_factory=CodecConfig)
    guardrail: GuardrailConfig = field(default_factory=GuardrailConfig)
    escrow: EscrowConfig = field(default_factory=EscrowConfig)
    uncertainty: UncertaintyConfig = field(default_factory=UncertaintyConfig)
    resource: ResourceConfig = field(default_factory=ResourceConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    acquisition: AcquisitionConfig = field(default_factory=AcquisitionConfig)
    synthetic: SyntheticConfig = field(default_factory=SyntheticConfig)
    saved_discovery: SavedDiscoveryConfig = field(default_factory=SavedDiscoveryConfig)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "default.yaml"


def _dict_to_dataclass(cls, data: dict):
    """Recursively convert a dictionary to a dataclass instance."""
    if data is None:
        return cls()
    field_names = {f.name for f in cls.__dataclass_fields__.values()}
    filtered = {}
    for k, v in data.items():
        if k in field_names:
            ft = cls.__dataclass_fields__[k].type
            # Handle tuple fields stored as lists in YAML
            if isinstance(v, list):
                v = tuple(v)
            filtered[k] = v
    return cls(**filtered)


def load_config(path: str | Path | None = None) -> EventVaultConfig:
    """
    Load configuration from a YAML file.

    Parameters
    ----------
    path : str or Path, optional
        Path to the YAML config file.  Falls back to
        ``config/default.yaml`` relative to the project root.

    Returns
    -------
    EventVaultConfig
        Fully populated configuration dataclass.
    """
    if path is None:
        path = os.environ.get("EVENTVAULT_CONFIG", _DEFAULT_CONFIG_PATH)
    path = Path(path)

    if not path.exists():
        # Return defaults if no config file found
        return EventVaultConfig()

    with open(path, "r") as f:
        raw = yaml.safe_load(f) or {}

    return EventVaultConfig(
        codec=_dict_to_dataclass(CodecConfig, raw.get("codec")),
        guardrail=_dict_to_dataclass(GuardrailConfig, raw.get("guardrail")),
        escrow=_dict_to_dataclass(EscrowConfig, raw.get("escrow")),
        uncertainty=_dict_to_dataclass(UncertaintyConfig, raw.get("uncertainty")),
        resource=_dict_to_dataclass(ResourceConfig, raw.get("resource")),
        telemetry=_dict_to_dataclass(TelemetryConfig, raw.get("telemetry")),
        acquisition=_dict_to_dataclass(AcquisitionConfig, raw.get("acquisition")),
        synthetic=_dict_to_dataclass(SyntheticConfig, raw.get("synthetic")),
        saved_discovery=_dict_to_dataclass(
            SavedDiscoveryConfig, raw.get("saved_discovery")
        ),
    )
