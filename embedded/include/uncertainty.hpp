#pragma once

#include "dwt.hpp"
#include <map>
#include <string>
#include <vector>

namespace eventvault {
namespace uncertainty {

class UncertaintyEstimator {
public:
    virtual ~UncertaintyEstimator() = default;
    
    virtual void estimate(
        const codec::Matrix2D& image,
        double& p_known,
        double& u_ood
    ) = 0;
};

class SoftmaxEntropyEstimator : public UncertaintyEstimator {
public:
    SoftmaxEntropyEstimator(
        double novelty_threshold = 3.0
    );
    
    void estimate(
        const codec::Matrix2D& image,
        double& p_known,
        double& u_ood
    ) override;

private:
    std::map<std::string, double> extract_features(const codec::Matrix2D& image);
    void update_baseline();

    std::map<std::string, double> _baseline_stats;
    double _novelty_threshold;
    std::vector<std::map<std::string, double>> _seen_stats;
};

} // namespace uncertainty
} // namespace eventvault
