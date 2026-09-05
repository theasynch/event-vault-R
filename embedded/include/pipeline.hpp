#pragma once

#include "dwt.hpp"
#include "guardrail.hpp"
#include "escrow.hpp"
#include "resource_controller.hpp"
#include "telemetry.hpp"
#include "uncertainty.hpp"

#include <vector>
#include <string>
#include <functional>
#include <map>
#include <memory>

namespace eventvault {
namespace pipeline {

struct FrameMetadata {
    int frame_id;
    double timestamp;
};

struct PipelineMetrics {
    int frame_id;
    double timestamp;
    double processing_time_ms = 0.0;
    int num_sources_detected = 0;
    double p_known = 0.0;
    double u_ood = 0.0;
    double retention_utility = 0.0;
    std::vector<int> purgeable_layers;
    std::vector<int> locked_layers;
    double escrow_occupancy = 0.0;
    std::string resource_mode = "NOMINAL";
    bool triggered = false;
    int promoted_count = 0;
};

struct EventVaultConfig {
    double epsilon_F = 0.005;
    double epsilon_x = 0.1;
    double min_source_snr = 5.0;
    double aperture_radius = 5.0;
    double annulus_inner = 7.0;
    double annulus_outer = 12.0;

    int escrow_capacity = 100;
    double trigger_horizon_seconds = 1800.0;
    
    double alpha = 1.0;
    double beta = 1.5;
    double temporal_decay_lambda = 0.01;
    
    double memory_warning_fraction = 0.7;
    double memory_critical_fraction = 0.9;
    double min_horizon_seconds = 300.0;
    int min_detail_level = 1;
    
    int downlink_bandwidth_bps = 9600;
    int max_queue_depth = 50;
    
    double cadence_seconds = 30.0;
};

class EventVaultPipeline {
public:
    using TriggerCallback = std::function<bool(int frame_id, double timestamp, const std::vector<science::SourceMeasurement>&)>;

    EventVaultPipeline(
        const EventVaultConfig& config = EventVaultConfig(),
        TriggerCallback trigger_callback = nullptr
    );

    PipelineMetrics process_frame(const codec::Matrix2D& frame, const FrameMetadata& metadata);

    const std::vector<PipelineMetrics>& metrics() const { return _metrics; }

private:
    double compute_retention_utility(
        double p_known, double u_ood, 
        double timestamp, double event_time, 
        int storage_cost_bits
    );

    EventVaultConfig _config;
    TriggerCallback _trigger_callback;
    
    escrow::EscrowBuffer _escrow_buffer;
    uncertainty::SoftmaxEntropyEstimator _uncertainty_estimator;
    controller::ResourceController _resource_controller;
    telemetry::DownlinkQueue _downlink_queue;
    
    std::map<int, codec::Matrix2D> _base_layer_store;
    std::vector<PipelineMetrics> _metrics;
};

} // namespace pipeline
} // namespace eventvault
