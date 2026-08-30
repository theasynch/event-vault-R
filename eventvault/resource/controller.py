"""
Joint Resource Controller for EventVault-R.

Implements Section IX of the proposal. Maintains the spacecraft
state vector C(t) = [M_free, B_downlink, E_batt] (Eq. 19)
and maps it to operating parameters (Eq. 20):

    (T_h, D_min, τ_snr) = g(C(t))

When memory pressure rises, the controller shortens the escrow
horizon or reduces the minimum retained detail. This is a
deterministic rule-based controller for verifiability (Section IX).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ResourceState:
    """
    Spacecraft resource state vector C(t).

    Attributes
    ----------
    memory_free_fraction : float
        Fraction of escrow buffer that is free [0, 1].
    downlink_available : float
        Estimated available downlink bandwidth [0, 1] normalized.
    battery_fraction : float
        Battery state of charge [0, 1].
    """
    memory_free_fraction: float = 1.0
    downlink_available: float = 1.0
    battery_fraction: float = 1.0


@dataclass
class OperatingParameters:
    """
    Operating parameters derived from resource state.

    Attributes
    ----------
    trigger_horizon : float
        Escrow horizon in seconds (T_h).
    min_detail_level : int
        Minimum DWT detail level to retain (D_min).
    snr_threshold : float
        SNR threshold for source detection (τ_snr).
    allow_new_escrow : bool
        Whether new frames can enter escrow.
    force_purge : bool
        Whether to force-purge unlocked entries.
    """
    trigger_horizon: float = 1800.0
    min_detail_level: int = 1
    snr_threshold: float = 5.0
    allow_new_escrow: bool = True
    force_purge: bool = False


class ResourceController:
    """
    Deterministic rule-based resource controller.

    Maps the resource state vector to operating parameters
    using configurable thresholds.

    Parameters
    ----------
    default_horizon : float
        Default escrow horizon in seconds.
    min_horizon : float
        Minimum horizon under memory pressure.
    warning_fraction : float
        Memory usage fraction triggering warning mode.
    critical_fraction : float
        Memory usage fraction triggering critical mode.
    min_detail_level : int
        Minimum detail level retained under pressure.
    """

    def __init__(
        self,
        default_horizon: float = 1800.0,
        min_horizon: float = 300.0,
        warning_fraction: float = 0.7,
        critical_fraction: float = 0.9,
        min_detail_level: int = 1,
    ):
        self.default_horizon = default_horizon
        self.min_horizon = min_horizon
        self.warning_fraction = warning_fraction
        self.critical_fraction = critical_fraction
        self.min_detail_level = min_detail_level

        # Simulated resource state
        self._state = ResourceState()
        self._params = OperatingParameters(trigger_horizon=default_horizon)

    def update_state(
        self,
        memory_free_fraction: Optional[float] = None,
        downlink_available: Optional[float] = None,
        battery_fraction: Optional[float] = None,
    ) -> OperatingParameters:
        """
        Update resource state and recompute operating parameters.

        Parameters
        ----------
        memory_free_fraction : float, optional
            Updated memory availability.
        downlink_available : float, optional
            Updated downlink availability.
        battery_fraction : float, optional
            Updated battery state.

        Returns
        -------
        OperatingParameters
            New operating parameters for the pipeline.
        """
        if memory_free_fraction is not None:
            self._state.memory_free_fraction = memory_free_fraction
        if downlink_available is not None:
            self._state.downlink_available = downlink_available
        if battery_fraction is not None:
            self._state.battery_fraction = battery_fraction

        self._params = self._compute_parameters(self._state)
        return self._params

    def _compute_parameters(self, state: ResourceState) -> OperatingParameters:
        """
        Deterministic rule-based mapping g(C(t)).

        Three operating modes:
        - NOMINAL: memory_used < warning → default parameters
        - WARNING: warning ≤ memory_used < critical → reduced horizon
        - CRITICAL: memory_used ≥ critical → minimum settings + force purge
        """
        memory_used = 1.0 - state.memory_free_fraction

        if memory_used < self.warning_fraction:
            # NOMINAL mode
            mode = "NOMINAL"
            params = OperatingParameters(
                trigger_horizon=self.default_horizon,
                min_detail_level=1,
                snr_threshold=5.0,
                allow_new_escrow=True,
                force_purge=False,
            )
        elif memory_used < self.critical_fraction:
            # WARNING mode: linearly reduce horizon
            mode = "WARNING"
            pressure = (memory_used - self.warning_fraction) / (
                self.critical_fraction - self.warning_fraction
            )
            horizon = self.default_horizon - pressure * (
                self.default_horizon - self.min_horizon
            )
            params = OperatingParameters(
                trigger_horizon=max(horizon, self.min_horizon),
                min_detail_level=self.min_detail_level,
                snr_threshold=5.0 + 2.0 * pressure,  # Raise SNR threshold
                allow_new_escrow=True,
                force_purge=False,
            )
        else:
            # CRITICAL mode
            mode = "CRITICAL"
            params = OperatingParameters(
                trigger_horizon=self.min_horizon,
                min_detail_level=self.min_detail_level + 1,
                snr_threshold=10.0,
                allow_new_escrow=state.battery_fraction > 0.2,
                force_purge=True,
            )

        # Battery override: if battery is very low, reduce processing
        if state.battery_fraction < 0.1:
            params.allow_new_escrow = False
            params.min_detail_level = max(params.min_detail_level, 2)

        logger.debug(
            "Resource controller: mode=%s, memory=%.1f%%, horizon=%.0fs, "
            "min_detail=%d, snr_thresh=%.1f",
            mode, memory_used * 100,
            params.trigger_horizon, params.min_detail_level,
            params.snr_threshold,
        )

        return params

    @property
    def state(self) -> ResourceState:
        """Current resource state."""
        return self._state

    @property
    def parameters(self) -> OperatingParameters:
        """Current operating parameters."""
        return self._params

    def get_mode(self) -> str:
        """Return current operating mode as string."""
        memory_used = 1.0 - self._state.memory_free_fraction
        if memory_used < self.warning_fraction:
            return "NOMINAL"
        elif memory_used < self.critical_fraction:
            return "WARNING"
        else:
            return "CRITICAL"
