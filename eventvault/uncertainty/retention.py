"""
Retention utility function for EventVault-R.

Implements Equation 15 from the proposal:

    U(fi) = [α·P_known(fi) + β·U_OOD(fi)] · ω(ti) / C_bits(fi)

where ω(ti) = exp(-λ(ti - t_event)) is the temporal weighting term (Eq. 16).

Key property (Eq. 17): ∂U/∂U_OOD > 0
→ Uncertainty increases retention priority.
"""

from __future__ import annotations

import numpy as np


def compute_retention_utility(
    p_known: float,
    u_ood: float,
    timestamp: float,
    event_time: float,
    storage_cost_bits: int,
    alpha: float = 1.0,
    beta: float = 1.5,
    temporal_decay_lambda: float = 0.01,
) -> float:
    """
    Compute retention utility for an escrow entry.

    Parameters
    ----------
    p_known : float
        Estimated probability of a known event [0, 1].
    u_ood : float
        OOD uncertainty score [0, 1].
    timestamp : float
        Acquisition time of the frame.
    event_time : float
        Time of the most recent event (or current time if no event).
    storage_cost_bits : int
        Storage cost of the residual data in bits.
    alpha : float
        Weight for P_known component.
    beta : float
        Weight for U_OOD component (should be > alpha for safety).
    temporal_decay_lambda : float
        Decay rate for temporal weighting.

    Returns
    -------
    float
        Retention utility score. Higher = more important to retain.

    Notes
    -----
    The β > α setting ensures that uncertain observations are
    retained with higher priority than observations confidently
    classified as known. This is the safety margin that protects
    against CNN false negatives on novel events.
    """
    # Science value component
    science_value = alpha * p_known + beta * u_ood

    # Temporal weighting (Eq. 16)
    dt = abs(timestamp - event_time)
    omega = np.exp(-temporal_decay_lambda * dt)

    # Storage cost normalization
    if storage_cost_bits > 0:
        cost_factor = 1.0 / storage_cost_bits
    else:
        cost_factor = 1.0

    utility = science_value * omega * cost_factor

    return float(utility)


def rank_entries_by_utility(
    entries: list,
    current_time: float,
    alpha: float = 1.0,
    beta: float = 1.5,
    temporal_decay_lambda: float = 0.01,
) -> list:
    """
    Rank escrow entries by retention utility (highest first).

    Parameters
    ----------
    entries : list of EscrowEntry
        Entries to rank.
    current_time : float
        Current time for temporal weighting.
    alpha, beta, temporal_decay_lambda : float
        Utility function parameters.

    Returns
    -------
    List of (utility, entry) tuples sorted by descending utility.
    """
    ranked = []
    for entry in entries:
        utility = compute_retention_utility(
            p_known=1.0 - entry.uncertainty_score,
            u_ood=entry.uncertainty_score,
            timestamp=entry.timestamp,
            event_time=current_time,
            storage_cost_bits=entry.total_bytes * 8,
            alpha=alpha,
            beta=beta,
            temporal_decay_lambda=temporal_decay_lambda,
        )
        entry.retention_utility = utility
        ranked.append((utility, entry))

    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked
