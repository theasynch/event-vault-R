"""
Uncertainty and OOD estimation for EventVault-R.

Implements three uncertainty estimation approaches from
Section VII.B of the proposal:

1. Softmax entropy (simplest baseline)
2. Mahalanobis distance in feature space
3. Ensemble disagreement

The key property (Eq. 17) is that ∂U/∂U_OOD > 0:
uncertainty is NOT evidence that an image is useless.
High uncertainty causes the system to preserve MORE information.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

import numpy as np
from numpy.typing import NDArray


class UncertaintyEstimator(ABC):
    """Base class for uncertainty estimation methods."""

    @abstractmethod
    def estimate(
        self,
        image: NDArray[np.float64],
        features: Optional[NDArray] = None,
    ) -> Tuple[float, float]:
        """
        Estimate known-event probability and OOD score.

        Parameters
        ----------
        image : 2-D ndarray
            Input image (calibrated).
        features : ndarray, optional
            Pre-extracted feature vector.

        Returns
        -------
        p_known : float
            Estimated probability [0, 1] that the observation
            contains a known-class event.
        u_ood : float
            Normalized OOD uncertainty score [0, 1].
            Higher = more uncertain / more out-of-distribution.
        """
        ...


class SoftmaxEntropyEstimator(UncertaintyEstimator):
    """
    Uncertainty estimation via softmax entropy.

    The simplest baseline from Section VII.B. Uses image
    statistics as lightweight features and computes entropy
    of a simple classification score.

    For the reference implementation, this uses heuristic
    features rather than a trained CNN, allowing the system
    to work without training data while still providing
    meaningful uncertainty ordering.
    """

    def __init__(
        self,
        baseline_stats: Optional[dict] = None,
        novelty_threshold: float = 3.0,
    ):
        """
        Parameters
        ----------
        baseline_stats : dict, optional
            Expected statistics for "normal" observations.
            Keys: 'mean', 'std', 'max_gradient', 'source_density'.
        novelty_threshold : float
            Number of standard deviations from baseline to consider OOD.
        """
        self.baseline_stats = baseline_stats or {
            "mean": 200.0,
            "std": 50.0,
            "max_gradient": 100.0,
            "source_density": 0.001,
        }
        self.novelty_threshold = novelty_threshold
        self._seen_stats: List[dict] = []

    def _extract_features(self, image: NDArray[np.float64]) -> dict:
        """Extract lightweight statistical features from an image."""
        features = {
            "mean": float(np.mean(image)),
            "std": float(np.std(image)),
            "median": float(np.median(image)),
            "max": float(np.max(image)),
            "min": float(np.min(image)),
            "skewness": float(_skewness(image)),
            "kurtosis": float(_kurtosis(image)),
        }

        # Gradient magnitude (proxy for source activity)
        gy, gx = np.gradient(image)
        grad_mag = np.sqrt(gx**2 + gy**2)
        features["max_gradient"] = float(np.max(grad_mag))
        features["mean_gradient"] = float(np.mean(grad_mag))

        # High-pixel density (proxy for source density)
        threshold = np.median(image) + 5 * np.std(image)
        features["bright_fraction"] = float(np.mean(image > threshold))

        return features

    def estimate(
        self,
        image: NDArray[np.float64],
        features: Optional[NDArray] = None,
    ) -> Tuple[float, float]:
        """
        Estimate uncertainty via softmax entropy of image statistics.

        Returns
        -------
        p_known : float
            Probability that this is a "normal" observation.
        u_ood : float
            OOD score (higher = more anomalous).
        """
        feats = self._extract_features(image)

        # Compute deviation from baseline statistics
        deviations = []
        for key in ["mean", "std", "max_gradient"]:
            if key in self.baseline_stats:
                expected = self.baseline_stats[key]
                actual = feats.get(key, expected)
                if expected > 0:
                    dev = abs(actual - expected) / expected
                else:
                    dev = abs(actual)
                deviations.append(dev)

        # Add novelty from bright-pixel fraction
        if feats["bright_fraction"] > 0.01:
            deviations.append(feats["bright_fraction"] * 10)

        # Aggregate deviation as OOD score
        if deviations:
            raw_ood = np.mean(deviations)
        else:
            raw_ood = 0.0

        # Sigmoid normalization to [0, 1]
        u_ood = float(1.0 / (1.0 + np.exp(-2.0 * (raw_ood - 0.5))))

        # P_known is complementary
        p_known = 1.0 - u_ood

        # Update running statistics
        self._seen_stats.append(feats)
        if len(self._seen_stats) > 10:
            self._update_baseline()

        return p_known, u_ood

    def _update_baseline(self) -> None:
        """Update baseline statistics from running observations."""
        if len(self._seen_stats) < 5:
            return
        for key in ["mean", "std", "max_gradient"]:
            values = [s[key] for s in self._seen_stats if key in s]
            if values:
                self.baseline_stats[key] = float(np.median(values))


class MahalanobisEstimator(UncertaintyEstimator):
    """
    Uncertainty estimation via Mahalanobis distance in feature space.

    Uses the squared Mahalanobis distance from the mean of
    previously seen observations as an OOD score.
    """

    def __init__(self, feature_dim: int = 8):
        self.feature_dim = feature_dim
        self._feature_buffer: List[NDArray] = []
        self._mean: Optional[NDArray] = None
        self._cov_inv: Optional[NDArray] = None

    def _extract_feature_vector(self, image: NDArray[np.float64]) -> NDArray:
        """Extract a fixed-length feature vector."""
        features = [
            np.mean(image),
            np.std(image),
            np.median(image),
            float(np.max(image)),
            float(_skewness(image)),
            float(_kurtosis(image)),
        ]
        # Add gradient statistics
        gy, gx = np.gradient(image)
        grad_mag = np.sqrt(gx**2 + gy**2)
        features.append(float(np.mean(grad_mag)))
        features.append(float(np.max(grad_mag)))
        return np.array(features[:self.feature_dim], dtype=np.float64)

    def estimate(
        self,
        image: NDArray[np.float64],
        features: Optional[NDArray] = None,
    ) -> Tuple[float, float]:
        fv = features if features is not None else self._extract_feature_vector(image)
        self._feature_buffer.append(fv)

        if len(self._feature_buffer) < 5:
            # Not enough data for Mahalanobis — return moderate uncertainty
            return 0.5, 0.5

        # Update statistics
        all_features = np.array(self._feature_buffer)
        self._mean = np.mean(all_features, axis=0)
        cov = np.cov(all_features.T)
        try:
            self._cov_inv = np.linalg.inv(cov + 1e-6 * np.eye(len(self._mean)))
        except np.linalg.LinAlgError:
            self._cov_inv = np.eye(len(self._mean))

        # Mahalanobis distance
        diff = fv - self._mean
        dist_sq = float(diff @ self._cov_inv @ diff)

        # Normalize via chi-squared CDF approximation
        # For feature_dim degrees of freedom
        u_ood = float(1.0 - np.exp(-dist_sq / (2.0 * self.feature_dim)))
        p_known = 1.0 - u_ood

        return p_known, u_ood


class EnsembleEstimator(UncertaintyEstimator):
    """
    Uncertainty via ensemble disagreement.

    Uses multiple simple estimators with different random
    perturbations and measures their disagreement as uncertainty.
    """

    def __init__(self, n_members: int = 5, seed: int = 42):
        self.n_members = n_members
        self.rng = np.random.default_rng(seed)
        # Create ensemble members with different baseline perturbations
        self.members = []
        for i in range(n_members):
            noise = self.rng.normal(0, 0.1, size=3)
            member = SoftmaxEntropyEstimator(
                baseline_stats={
                    "mean": 200.0 * (1 + noise[0]),
                    "std": 50.0 * (1 + noise[1]),
                    "max_gradient": 100.0 * (1 + noise[2]),
                }
            )
            self.members.append(member)

    def estimate(
        self,
        image: NDArray[np.float64],
        features: Optional[NDArray] = None,
    ) -> Tuple[float, float]:
        p_knowns = []
        u_oods = []
        for member in self.members:
            p, u = member.estimate(image, features)
            p_knowns.append(p)
            u_oods.append(u)

        # Mean estimates
        p_known = float(np.mean(p_knowns))
        u_ood_mean = float(np.mean(u_oods))

        # Disagreement increases uncertainty
        disagreement = float(np.std(u_oods))
        u_ood = min(1.0, u_ood_mean + disagreement)

        return p_known, u_ood


def create_estimator(method: str = "softmax_entropy", **kwargs) -> UncertaintyEstimator:
    """
    Factory function for uncertainty estimators.

    Parameters
    ----------
    method : str
        One of: 'softmax_entropy', 'mahalanobis', 'ensemble'.
    **kwargs
        Additional arguments passed to the estimator constructor.

    Returns
    -------
    UncertaintyEstimator instance.
    """
    estimators = {
        "softmax_entropy": SoftmaxEntropyEstimator,
        "mahalanobis": MahalanobisEstimator,
        "ensemble": EnsembleEstimator,
    }
    cls = estimators.get(method)
    if cls is None:
        raise ValueError(
            f"Unknown uncertainty method: {method}. "
            f"Choose from: {list(estimators.keys())}"
        )
    return cls(**kwargs)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _skewness(data: NDArray) -> float:
    """Compute skewness of a flat array."""
    flat = data.ravel().astype(np.float64)
    n = len(flat)
    if n < 3:
        return 0.0
    mean = np.mean(flat)
    std = np.std(flat)
    if std < 1e-10:
        return 0.0
    return float(np.mean(((flat - mean) / std) ** 3))


def _kurtosis(data: NDArray) -> float:
    """Compute excess kurtosis of a flat array."""
    flat = data.ravel().astype(np.float64)
    n = len(flat)
    if n < 4:
        return 0.0
    mean = np.mean(flat)
    std = np.std(flat)
    if std < 1e-10:
        return 0.0
    return float(np.mean(((flat - mean) / std) ** 4) - 3.0)
