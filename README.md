# EventVault-R

**Progressive, Uncertainty-Bounded Science-Data Escrow Architecture for Resource-Constrained CubeSat Astronomy**

*Om Awthankar, Dax Shah — VIT Vellore*

## Overview

EventVault-R is the core data-management algorithm of the AstraVault architecture. It treats high-resolution scientific information as a temporary **escrow asset** rather than an immediately disposable resource.

Each astronomical image is decomposed into progressively refinable wavelet layers:
- A **compact base layer** is retained permanently for situational awareness
- **Fine residual layers** are held in a finite circular escrow buffer
- A **Science Guardrail** evaluates deletion using scientific observables (photometric flux ε_F ≤ 0.5%, centroid accuracy ε_x ≤ 0.1 pixel)
- An **uncertainty-weighted controller** increases retention when inference is uncertain or OOD
- **Retroactive promotion** recovers pre-event residuals when a transient is later confirmed

## Architecture

```
Observe → Encode → Escrow → Observe Again → Promote or Purge
```

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run the Saved Discovery experiment
python experiments/saved_discovery.py

# Run rate-distortion analysis
python experiments/rate_distortion.py
```

## Project Structure

```
eventvault/
├── config.py          # Configuration loader
├── pipeline.py        # Core control loop (Algorithm 1)
├── acquisition/       # Frame ingestion & calibration
├── codec/             # Progressive 3-level DWT encoder
├── science/           # Science Guardrail (flux + centroid)
├── escrow/            # Circular escrow buffer & promotion
├── uncertainty/       # OOD/uncertainty estimation
├── resource/          # Joint resource controller
└── telemetry/         # Throttled downlink queue
```

## Key Parameters

| Parameter | Target | Description |
|-----------|--------|-------------|
| ε_F | ≤ 0.5% | Photometric flux error bound |
| ε_x | ≤ 0.1 px | Centroid position error bound |
| Compression | ≥ 50% | Data reduction vs lossless baseline |
| Buffer loss | 0 | Zero uncontrolled escrow overflow |

## References

1. O. Awthankar and D. Shah, "EventVault-R — Build Plan, Novelty Notes & TRL4 Roadmap," 2026.
2. S. A. Chien et al., "The Autonomous Sciencecraft Experiment aboard the EO-1 Spacecraft," AAMAS, 2005.
3. M. Antonini et al., "Image coding using wavelet transform," IEEE TIP, 1992.
