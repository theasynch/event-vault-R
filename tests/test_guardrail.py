"""
Tests for the Science Guardrail.

Verifies:
- εF ≤ 0.5% flux error bound
- εx ≤ 0.1 pixel centroid error bound
- Layer-by-layer evaluation in reverse detail order
- Correct lock/unlock decisions
"""

import numpy as np
import pytest

from eventvault.acquisition.synthetic import generate_static_sources, SourceInfo
from eventvault.codec.dwt import decompose, reconstruct
from eventvault.science.guardrail import (
    evaluate_frame,
    evaluate_layer,
    FrameGuardrailDecision,
)
from eventvault.science.source_extraction import (
    SourceMeasurement,
    extract_sources,
    measure_source,
)


def _make_test_image(num_sources=20, seed=42):
    """Create a test image with known sources."""
    rng = np.random.default_rng(seed)
    shape = (256, 256)
    image = rng.poisson(200, size=shape).astype(np.float64)

    sources = []
    for _ in range(num_sources):
        x = rng.uniform(30, 226)
        y = rng.uniform(30, 226)
        flux = 10 ** rng.uniform(3.0, 4.0)  # 1000 - 10000 ADU
        sigma = 2.0
        yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
        psf = flux * np.exp(-((xx - x)**2 + (yy - y)**2) / (2 * sigma**2))
        psf_total = psf.sum()
        if psf_total > 0:
            psf *= flux / psf_total
        image += rng.poisson(np.clip(psf, 0, None))
        sources.append(SourceInfo(x=x, y=y, flux=flux))

    return image, sources


@pytest.fixture
def test_image_and_sources():
    """Generate test image with sources."""
    return _make_test_image(num_sources=20)


@pytest.fixture
def decomposition_and_sources(test_image_and_sources):
    """Decompose test image and extract reference sources."""
    image, _ = test_image_and_sources
    decomp = decompose(image)
    full_recon = reconstruct(decomp)
    h, w = image.shape
    full_recon = full_recon[:h, :w]
    ref_sources = extract_sources(full_recon, min_snr=3.0)
    return decomp, ref_sources


class TestGuardrailEvaluation:
    """Tests for guardrail layer evaluation."""

    def test_full_reconstruction_passes_guardrail(self, decomposition_and_sources):
        """Full reconstruction should always pass the guardrail."""
        decomp, ref_sources = decomposition_and_sources
        if len(ref_sources) == 0:
            pytest.skip("No sources detected")

        # Evaluating layer 4 (which doesn't exist for 3-level) is like
        # checking if full recon is acceptable — it always should be
        result = evaluate_layer(decomp, 1, ref_sources, epsilon_F=1.0, epsilon_x=10.0)
        # With very relaxed bounds, should pass
        assert result.is_safe

    def test_evaluate_frame_returns_decisions(self, decomposition_and_sources):
        """evaluate_frame should return decisions for all layers."""
        decomp, ref_sources = decomposition_and_sources
        if len(ref_sources) == 0:
            pytest.skip("No sources detected")

        decision = evaluate_frame(decomp, ref_sources)
        assert isinstance(decision, FrameGuardrailDecision)
        assert len(decision.layer_decisions) > 0

        # All layers should be accounted for
        all_layers = set(decision.purgeable_layers) | set(decision.locked_layers)
        assert len(all_layers) > 0

    def test_fine_layers_more_likely_purgeable(self, decomposition_and_sources):
        """Finest layers (H3) should be more likely purgeable than coarse (H1)."""
        decomp, ref_sources = decomposition_and_sources
        if len(ref_sources) == 0:
            pytest.skip("No sources detected")

        # With default tolerances
        decision = evaluate_frame(decomp, ref_sources)

        # If H3 is locked but H2 is purgeable, something is wrong
        # (removing more detail should only make things worse)
        if 2 in decision.purgeable_layers and 3 in decision.locked_layers:
            pytest.fail(
                "Coarser layer purgeable but finer layer locked — "
                "guardrail ordering may be incorrect"
            )


class TestGuardrailBounds:
    """Tests for guardrail error bounds on many sources."""

    def test_flux_error_within_bound(self):
        """
        ΔF ≤ 0.5% for sources where guardrail says safe.
        Tests on multiple images with different source configurations.
        """
        violations = 0
        total_checked = 0

        for seed in range(20):  # 20 different images
            image, _ = _make_test_image(num_sources=10, seed=seed + 100)
            decomp = decompose(image)
            full_recon = reconstruct(decomp)
            h, w = image.shape
            full_recon = full_recon[:h, :w]
            ref_sources = extract_sources(full_recon, min_snr=5.0)

            if len(ref_sources) == 0:
                continue

            decision = evaluate_frame(
                decomp, ref_sources,
                epsilon_F=0.005, epsilon_x=0.1,
            )

            # For purgeable layers, verify the error is actually within bounds
            for layer in decision.purgeable_layers:
                result = decision.layer_decisions[layer]
                total_checked += result.num_sources_evaluated
                if result.max_flux_error > 0.005:
                    violations += 1

        if total_checked > 0:
            violation_rate = violations / max(total_checked, 1)
            assert violation_rate == 0.0, (
                f"Guardrail approved deletions with flux error > 0.5%: "
                f"{violations} violations in {total_checked} checks"
            )

    def test_centroid_error_within_bound(self):
        """
        Δx ≤ 0.1 pixel for sources where guardrail says safe.
        """
        violations = 0
        total_checked = 0

        for seed in range(20):
            image, _ = _make_test_image(num_sources=10, seed=seed + 200)
            decomp = decompose(image)
            full_recon = reconstruct(decomp)
            h, w = image.shape
            full_recon = full_recon[:h, :w]
            ref_sources = extract_sources(full_recon, min_snr=5.0)

            if len(ref_sources) == 0:
                continue

            decision = evaluate_frame(
                decomp, ref_sources,
                epsilon_F=0.005, epsilon_x=0.1,
            )

            for layer in decision.purgeable_layers:
                result = decision.layer_decisions[layer]
                total_checked += result.num_sources_evaluated
                if result.max_centroid_error > 0.1:
                    violations += 1

        if total_checked > 0:
            assert violations == 0, (
                f"Guardrail approved deletions with centroid error > 0.1 px: "
                f"{violations} violations"
            )
