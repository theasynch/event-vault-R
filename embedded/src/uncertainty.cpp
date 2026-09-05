#include "uncertainty.hpp"
#include <cmath>
#include <algorithm>
#include <numeric>

namespace eventvault {
namespace uncertainty {

static double skewness(const std::vector<double>& flat) {
    if (flat.size() < 3) return 0.0;
    
    double sum = 0.0, sq_sum = 0.0;
    for (double v : flat) {
        sum += v;
        sq_sum += v * v;
    }
    double mean = sum / flat.size();
    double std_dev = std::sqrt(std::max(0.0, (sq_sum / flat.size()) - (mean * mean)));
    
    if (std_dev < 1e-10) return 0.0;
    
    double skew_sum = 0.0;
    for (double v : flat) {
        double z = (v - mean) / std_dev;
        skew_sum += z * z * z;
    }
    return skew_sum / flat.size();
}

static double kurtosis(const std::vector<double>& flat) {
    if (flat.size() < 4) return 0.0;
    
    double sum = 0.0, sq_sum = 0.0;
    for (double v : flat) {
        sum += v;
        sq_sum += v * v;
    }
    double mean = sum / flat.size();
    double std_dev = std::sqrt(std::max(0.0, (sq_sum / flat.size()) - (mean * mean)));
    
    if (std_dev < 1e-10) return 0.0;
    
    double kurt_sum = 0.0;
    for (double v : flat) {
        double z = (v - mean) / std_dev;
        kurt_sum += z * z * z * z;
    }
    return (kurt_sum / flat.size()) - 3.0;
}

SoftmaxEntropyEstimator::SoftmaxEntropyEstimator(double novelty_threshold) 
    : _novelty_threshold(novelty_threshold) 
{
    _baseline_stats["mean"] = 200.0;
    _baseline_stats["std"] = 50.0;
    _baseline_stats["max_gradient"] = 100.0;
    _baseline_stats["source_density"] = 0.001;
}

std::map<std::string, double> SoftmaxEntropyEstimator::extract_features(const codec::Matrix2D& image) {
    std::vector<double> flat = image.data;
    
    double sum = 0.0, sq_sum = 0.0;
    double min_val = 1e9, max_val = -1e9;
    
    for (double v : flat) {
        sum += v;
        sq_sum += v * v;
        if (v < min_val) min_val = v;
        if (v > max_val) max_val = v;
    }
    
    double mean = sum / flat.size();
    double std_dev = std::sqrt(std::max(0.0, (sq_sum / flat.size()) - (mean * mean)));
    
    std::vector<double> sorted = flat;
    std::sort(sorted.begin(), sorted.end());
    double median = sorted[sorted.size() / 2];
    
    std::map<std::string, double> features;
    features["mean"] = mean;
    features["std"] = std_dev;
    features["median"] = median;
    features["max"] = max_val;
    features["min"] = min_val;
    features["skewness"] = skewness(flat);
    features["kurtosis"] = kurtosis(flat);
    
    // Gradient magnitude
    double max_gradient = 0.0;
    double sum_gradient = 0.0;
    
    for (int y = 0; y < image.rows; ++y) {
        for (int x = 0; x < image.cols; ++x) {
            double gx = 0.0;
            if (x > 0 && x < image.cols - 1) {
                gx = (image(y, x+1) - image(y, x-1)) / 2.0;
            }
            double gy = 0.0;
            if (y > 0 && y < image.rows - 1) {
                gy = (image(y+1, x) - image(y-1, x)) / 2.0;
            }
            
            double grad_mag = std::sqrt(gx*gx + gy*gy);
            sum_gradient += grad_mag;
            if (grad_mag > max_gradient) max_gradient = grad_mag;
        }
    }
    
    features["max_gradient"] = max_gradient;
    features["mean_gradient"] = sum_gradient / flat.size();
    
    double threshold = median + 5.0 * std_dev;
    int bright_count = 0;
    for (double v : flat) {
        if (v > threshold) bright_count++;
    }
    
    features["bright_fraction"] = static_cast<double>(bright_count) / flat.size();
    
    return features;
}

void SoftmaxEntropyEstimator::estimate(
    const codec::Matrix2D& image,
    double& p_known,
    double& u_ood)
{
    auto feats = extract_features(image);
    
    std::vector<double> deviations;
    std::vector<std::string> keys = {"mean", "std", "max_gradient"};
    
    for (const auto& key : keys) {
        if (_baseline_stats.find(key) != _baseline_stats.end()) {
            double expected = _baseline_stats[key];
            double actual = expected;
            if (feats.find(key) != feats.end()) actual = feats[key];
            
            double dev = (expected > 0) ? std::abs(actual - expected) / expected : std::abs(actual);
            deviations.push_back(dev);
        }
    }
    
    if (feats["bright_fraction"] > 0.01) {
        deviations.push_back(feats["bright_fraction"] * 10.0);
    }
    
    double raw_ood = 0.0;
    if (!deviations.empty()) {
        double sum = 0.0;
        for (double d : deviations) sum += d;
        raw_ood = sum / deviations.size();
    }
    
    u_ood = 1.0 / (1.0 + std::exp(-2.0 * (raw_ood - 0.5)));
    p_known = 1.0 - u_ood;
    
    _seen_stats.push_back(feats);
    if (_seen_stats.size() > 10) {
        update_baseline();
    }
}

void SoftmaxEntropyEstimator::update_baseline() {
    if (_seen_stats.size() < 5) return;
    
    std::vector<std::string> keys = {"mean", "std", "max_gradient"};
    for (const auto& key : keys) {
        std::vector<double> values;
        for (const auto& s : _seen_stats) {
            if (s.find(key) != s.end()) {
                values.push_back(s.at(key));
            }
        }
        
        if (!values.empty()) {
            std::sort(values.begin(), values.end());
            _baseline_stats[key] = values[values.size() / 2];
        }
    }
}

} // namespace uncertainty
} // namespace eventvault
