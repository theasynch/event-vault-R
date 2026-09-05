#include "guardrail.hpp"
#include <cmath>
#include <algorithm>
#include <numeric>
#include <limits>

namespace eventvault {
namespace science {

SourceMeasurement measure_source(
    const codec::Matrix2D& image,
    int cx, int cy,
    double aperture_radius,
    double annulus_inner,
    double annulus_outer) 
{
    int rows = image.rows;
    int cols = image.cols;
    
    int y_min = std::max(0, static_cast<int>(cy - annulus_outer - 1));
    int y_max = std::min(rows, static_cast<int>(cy + annulus_outer + 2));
    int x_min = std::max(0, static_cast<int>(cx - annulus_outer - 1));
    int x_max = std::min(cols, static_cast<int>(cx + annulus_outer + 2));
    
    std::vector<double> bg_values;
    
    for (int y = y_min; y < y_max; ++y) {
        for (int x = x_min; x < x_max; ++x) {
            double dy = static_cast<double>(y - cy);
            double dx = static_cast<double>(x - cx);
            double r = std::sqrt(dx*dx + dy*dy);
            
            if (r >= annulus_inner && r <= annulus_outer) {
                bg_values.push_back(image(y, x));
            }
        }
    }
    
    double bg_mean = 0.0;
    double bg_std = 1.0;
    
    if (!bg_values.empty()) {
        std::sort(bg_values.begin(), bg_values.end());
        bg_mean = bg_values[bg_values.size() / 2]; // median
        
        double sum = 0.0, sq_sum = 0.0;
        for (double v : bg_values) {
            sum += v;
            sq_sum += v * v;
        }
        double mean = sum / bg_values.size();
        bg_std = std::sqrt(std::max(0.0, (sq_sum / bg_values.size()) - (mean * mean)));
    }
    
    int aperture_npix = 0;
    double flux = 0.0;
    double peak_value = -1e9;
    double w_sum = 0.0;
    double x_sum = 0.0;
    double y_sum = 0.0;
    
    for (int y = y_min; y < y_max; ++y) {
        for (int x = x_min; x < x_max; ++x) {
            double dy = static_cast<double>(y - cy);
            double dx = static_cast<double>(x - cx);
            double r = std::sqrt(dx*dx + dy*dy);
            
            if (r <= aperture_radius) {
                aperture_npix++;
                double val = image(y, x);
                if (val > peak_value) peak_value = val;
                
                double sub_val = val - bg_mean;
                flux += sub_val;
                
                double weight = std::max(0.0, sub_val);
                w_sum += weight;
                x_sum += weight * static_cast<double>(x);
                y_sum += weight * static_cast<double>(y);
            }
        }
    }
    
    SourceMeasurement meas;
    meas.background_mean = bg_mean;
    meas.aperture_npix = aperture_npix;
    
    if (aperture_npix == 0) {
        meas.x_centroid = static_cast<double>(cx);
        meas.y_centroid = static_cast<double>(cy);
        meas.flux = 0.0;
        meas.snr = 0.0;
        meas.peak_value = 0.0;
        return meas;
    }
    
    meas.flux = flux;
    meas.peak_value = peak_value;
    
    if (flux > 0.0 && w_sum > 0.0) {
        meas.x_centroid = x_sum / w_sum;
        meas.y_centroid = y_sum / w_sum;
    } else {
        meas.x_centroid = static_cast<double>(cx);
        meas.y_centroid = static_cast<double>(cy);
    }
    
    double noise_sq = aperture_npix * (bg_std * bg_std + bg_mean);
    meas.snr = (noise_sq > 0) ? (flux / std::sqrt(noise_sq)) : 0.0;
    
    return meas;
}

std::vector<SourceMeasurement> extract_sources(
    const codec::Matrix2D& image,
    double min_snr,
    double aperture_radius,
    double annulus_inner,
    double annulus_outer,
    double threshold_sigma)
{
    // 1. Estimate background using local mean (approximate uniform filter)
    int box_size = 64;
    int half_box = box_size / 2;
    codec::Matrix2D bg(image.rows, image.cols);
    for (int y = 0; y < image.rows; ++y) {
        for (int x = 0; x < image.cols; ++x) {
            double sum = 0.0;
            int count = 0;
            for (int dy = -half_box; dy <= half_box; ++dy) {
                for (int dx = -half_box; dx <= half_box; ++dx) {
                    int ny = y + dy;
                    int nx = x + dx;
                    if (ny >= 0 && ny < image.rows && nx >= 0 && nx < image.cols) {
                        sum += image(ny, nx);
                        count++;
                    }
                }
            }
            bg(y, x) = sum / count;
        }
    }
    
    codec::Matrix2D sub(image.rows, image.cols);
    std::vector<double> abs_sub;
    abs_sub.reserve(image.rows * image.cols);
    for (size_t i = 0; i < image.data.size(); ++i) {
        double diff = image.data[i] - bg.data[i];
        sub.data[i] = diff;
        abs_sub.push_back(std::abs(diff));
    }
    
    std::sort(abs_sub.begin(), abs_sub.end());
    double mad = abs_sub[abs_sub.size() / 2];
    double noise = mad * 1.4826;
    if (noise <= 0) noise = 1.0;
    
    double threshold = threshold_sigma * noise;
    
    std::vector<std::pair<int, int>> positions;
    int min_sep = 5;
    int half_sep = min_sep / 2;
    
    for (int y = 0; y < image.rows; ++y) {
        for (int x = 0; x < image.cols; ++x) {
            double val = sub(y, x);
            if (val > threshold) {
                bool is_max = true;
                for (int dy = -half_sep; dy <= half_sep && is_max; ++dy) {
                    for (int dx = -half_sep; dx <= half_sep && is_max; ++dx) {
                        if (dy == 0 && dx == 0) continue;
                        int ny = y + dy;
                        int nx = x + dx;
                        if (ny >= 0 && ny < image.rows && nx >= 0 && nx < image.cols) {
                            if (sub(ny, nx) >= val) {
                                is_max = false;
                            }
                        }
                    }
                }
                if (is_max) {
                    positions.push_back({y, x});
                }
            }
        }
    }
    
    std::vector<SourceMeasurement> sources;
    for (const auto& pos : positions) {
        SourceMeasurement meas = measure_source(image, pos.second, pos.first, aperture_radius, annulus_inner, annulus_outer);
        if (meas.snr >= min_snr) {
            sources.push_back(meas);
        }
    }
    
    return sources;
}

static double compute_flux_error(double measured, double reference) {
    if (std::abs(reference) < 1e-10) {
        return (std::abs(measured) < 1e-10) ? 0.0 : std::numeric_limits<double>::infinity();
    }
    return std::abs(measured - reference) / std::abs(reference);
}

static double compute_centroid_error(double mx, double my, double rx, double ry) {
    double dx = mx - rx;
    double dy = my - ry;
    return std::sqrt(dx*dx + dy*dy);
}

GuardrailResult evaluate_layer(
    const codec::WaveletDecomposition& decomp,
    int layer,
    const std::vector<SourceMeasurement>& reference_sources,
    double epsilon_F,
    double epsilon_x,
    double aperture_radius,
    double annulus_inner,
    double annulus_outer)
{
    int recon_depth = layer - 1;
    codec::Matrix2D reconstructed = codec::reconstruct(decomp, recon_depth);
    
    GuardrailResult result;
    result.layer = layer;
    result.max_flux_error = 0.0;
    result.max_centroid_error = 0.0;
    result.num_sources_evaluated = reference_sources.size();
    
    for (const auto& ref_src : reference_sources) {
        int cx = static_cast<int>(std::round(ref_src.x_centroid));
        int cy = static_cast<int>(std::round(ref_src.y_centroid));
        
        if (cx < 0 || cx >= reconstructed.cols || cy < 0 || cy >= reconstructed.rows) {
            continue;
        }
        
        SourceMeasurement meas = measure_source(
            reconstructed, cx, cy, 
            aperture_radius, annulus_inner, annulus_outer
        );
        
        double flux_err = compute_flux_error(meas.flux, ref_src.flux);
        double centroid_err = compute_centroid_error(
            meas.x_centroid, meas.y_centroid, 
            ref_src.x_centroid, ref_src.y_centroid
        );
        
        result.max_flux_error = std::max(result.max_flux_error, flux_err);
        result.max_centroid_error = std::max(result.max_centroid_error, centroid_err);
        
        if (flux_err > epsilon_F || centroid_err > epsilon_x) {
            GuardrailViolation violation;
            violation.source_x = ref_src.x_centroid;
            violation.source_y = ref_src.y_centroid;
            violation.ref_flux = ref_src.flux;
            violation.meas_flux = meas.flux;
            violation.flux_error = flux_err;
            violation.centroid_error = centroid_err;
            violation.reason = "Bounds exceeded";
            result.violations.push_back(violation);
        }
    }
    
    result.is_safe = result.violations.empty();
    return result;
}

FrameGuardrailDecision evaluate_frame(
    const codec::WaveletDecomposition& decomp,
    const std::vector<SourceMeasurement>& reference_sources,
    double epsilon_F,
    double epsilon_x,
    double aperture_radius,
    double annulus_inner,
    double annulus_outer)
{
    FrameGuardrailDecision decision;
    decision.frame_id = 0; // Set by caller
    
    for (int layer = decomp.levels; layer > 0; --layer) {
        GuardrailResult result = evaluate_layer(
            decomp, layer, reference_sources,
            epsilon_F, epsilon_x, aperture_radius, annulus_inner, annulus_outer
        );
        
        decision.layer_decisions[layer] = result;
        
        if (result.is_safe) {
            decision.purgeable_layers.push_back(layer);
        } else {
            decision.locked_layers.push_back(layer);
            
            for (int inner_layer = layer - 1; inner_layer > 0; --inner_layer) {
                if (decision.layer_decisions.find(inner_layer) == decision.layer_decisions.end()) {
                    GuardrailResult auto_locked;
                    auto_locked.layer = inner_layer;
                    auto_locked.is_safe = false;
                    auto_locked.max_flux_error = std::numeric_limits<double>::infinity();
                    auto_locked.max_centroid_error = std::numeric_limits<double>::infinity();
                    auto_locked.num_sources_evaluated = 0;
                    
                    GuardrailViolation v;
                    v.reason = "locked by parent layer";
                    auto_locked.violations.push_back(v);
                    
                    decision.layer_decisions[inner_layer] = auto_locked;
                    decision.locked_layers.push_back(inner_layer);
                }
            }
            break;
        }
    }
    
    std::sort(decision.purgeable_layers.begin(), decision.purgeable_layers.end(), std::greater<int>());
    std::sort(decision.locked_layers.begin(), decision.locked_layers.end());
    
    return decision;
}

} // namespace science
} // namespace eventvault
