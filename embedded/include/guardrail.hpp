#pragma once

#include "dwt.hpp"
#include <vector>
#include <string>
#include <map>

namespace eventvault {
namespace science {

struct SourceMeasurement {
    double x_centroid;
    double y_centroid;
    double flux;
    double snr;
    double peak_value;
    int aperture_npix;
    double background_mean;
};

struct GuardrailViolation {
    double source_x;
    double source_y;
    double ref_flux;
    double meas_flux;
    double flux_error;
    double centroid_error;
    std::string reason;
};

struct GuardrailResult {
    int layer;
    bool is_safe;
    double max_flux_error;
    double max_centroid_error;
    int num_sources_evaluated;
    std::vector<GuardrailViolation> violations;
};

struct FrameGuardrailDecision {
    int frame_id;
    std::map<int, GuardrailResult> layer_decisions;
    std::vector<int> purgeable_layers; // Sorted highest to lowest
    std::vector<int> locked_layers;    // Sorted lowest to highest
};

// Computes background-subtracted flux and centroid via aperture photometry
SourceMeasurement measure_source(
    const codec::Matrix2D& image,
    int cx, int cy,
    double aperture_radius = 5.0,
    double annulus_inner = 7.0,
    double annulus_outer = 12.0
);

// Extracts sources from an image
std::vector<SourceMeasurement> extract_sources(
    const codec::Matrix2D& image,
    double min_snr = 5.0,
    double aperture_radius = 5.0,
    double annulus_inner = 7.0,
    double annulus_outer = 12.0,
    double threshold_sigma = 5.0
);

// Evaluates a single layer for removal
GuardrailResult evaluate_layer(
    const codec::WaveletDecomposition& decomp,
    int layer,
    const std::vector<SourceMeasurement>& reference_sources,
    double epsilon_F = 0.005,
    double epsilon_x = 0.1,
    double aperture_radius = 5.0,
    double annulus_inner = 7.0,
    double annulus_outer = 12.0
);

// Evaluates all layers in a frame
FrameGuardrailDecision evaluate_frame(
    const codec::WaveletDecomposition& decomp,
    const std::vector<SourceMeasurement>& reference_sources,
    double epsilon_F = 0.005,
    double epsilon_x = 0.1,
    double aperture_radius = 5.0,
    double annulus_inner = 7.0,
    double annulus_outer = 12.0
);

} // namespace science
} // namespace eventvault
