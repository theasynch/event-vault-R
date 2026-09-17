#include "pipeline.hpp"
#include <chrono>
#include <iostream>
#include <algorithm>
#include <cmath>

namespace eventvault {
namespace pipeline {

EventVaultPipeline::EventVaultPipeline(const EventVaultConfig& config, TriggerCallback trigger_callback)
    : _config(config),
      _trigger_callback(trigger_callback),
      _escrow_buffer(config.escrow_capacity, config.trigger_horizon_seconds),
      _resource_controller(config.trigger_horizon_seconds, config.min_horizon_seconds,
                           config.memory_warning_fraction, config.memory_critical_fraction, config.min_detail_level),
      _downlink_queue(config.downlink_bandwidth_bps, config.max_queue_depth)
{
}

double EventVaultPipeline::compute_retention_utility(
    double p_known, double u_ood, 
    double timestamp, double event_time, 
    int storage_cost_bits)
{
    double science_value = _config.alpha * p_known + _config.beta * u_ood;
    double dt = std::abs(timestamp - event_time);
    double omega = std::exp(-_config.temporal_decay_lambda * dt);
    double cost_factor = storage_cost_bits > 0 ? 1.0 / storage_cost_bits : 1.0;
    
    return science_value * omega * cost_factor;
}

PipelineMetrics EventVaultPipeline::process_frame(const codec::Matrix2D& frame, const FrameMetadata& metadata) {
    auto t_start = std::chrono::high_resolution_clock::now();
    
    PipelineMetrics metrics;
    metrics.frame_id = metadata.frame_id;
    metrics.timestamp = metadata.timestamp;
    
    // Step 1: DWT Decomposition
    auto decomp = codec::decompose(frame, "bior4.4", 3, "symmetric");
    
    // Step 2: Store base layer
    _base_layer_store[metadata.frame_id] = decomp.base_layer;
    int base_size = decomp.base_layer.data.size() * sizeof(double);
    _downlink_queue.enqueue_base_layer(metadata.frame_id, base_size, metadata.timestamp);
    
    // Step 3: Push residuals to escrow
    escrow::EscrowEntry* escrow_entry = nullptr;
    try {
        escrow_entry = _escrow_buffer.push(
            metadata.frame_id,
            metadata.timestamp,
            decomp.residual_layers,
            0.0,
            0,
            _resource_controller.get_parameters().trigger_horizon
        );
    } catch (const escrow::EscrowBufferOverflowError&) {
        auto t_end = std::chrono::high_resolution_clock::now();
        metrics.processing_time_ms = std::chrono::duration<double, std::milli>(t_end - t_start).count();
        _metrics.push_back(metrics);
        return metrics;
    }
    
    // Step 4: Extract sources
    auto full_recon = codec::reconstruct(decomp);
    auto reference_sources = science::extract_sources(
        full_recon,
        _resource_controller.get_parameters().snr_threshold,
        _config.aperture_radius,
        _config.annulus_inner,
        _config.annulus_outer,
        _config.min_source_snr
    );
    
    metrics.num_sources_detected = reference_sources.size();
    if (escrow_entry) escrow_entry->source_count = reference_sources.size();
    
    // Step 5: Estimate uncertainty
    double p_known, u_ood;
    _uncertainty_estimator.estimate(frame, p_known, u_ood);
    metrics.p_known = p_known;
    metrics.u_ood = u_ood;
    if (escrow_entry) escrow_entry->uncertainty_score = u_ood;
    
    // Step 6-21: Guardrail evaluation
    if (!reference_sources.empty()) {
        auto guardrail_decision = science::evaluate_frame(
            decomp,
            reference_sources,
            _config.epsilon_F,
            _config.epsilon_x,
            _config.aperture_radius,
            _config.annulus_inner,
            _config.annulus_outer
        );
        
        for (const auto& pair : guardrail_decision.layer_decisions) {
            int layer = pair.first;
            const auto& result = pair.second;
            
            if (result.is_safe) {
                _escrow_buffer.unlock_layer(metadata.frame_id, layer);
            } else {
                _escrow_buffer.lock(metadata.frame_id);
            }
        }
        
        metrics.purgeable_layers = guardrail_decision.purgeable_layers;
        metrics.locked_layers = guardrail_decision.locked_layers;
    } else {
        for (int layer = 1; layer <= decomp.levels; ++layer) {
            _escrow_buffer.unlock_layer(metadata.frame_id, layer);
        }
    }
    
    // Step 22: Compute retention utility
    if (escrow_entry) {
        double utility = compute_retention_utility(
            p_known, u_ood,
            metadata.timestamp, metadata.timestamp,
            escrow_entry->total_bytes() * 8
        );
        escrow_entry->retention_utility = utility;
        metrics.retention_utility = utility;
    }
    
    // Step 23: Resource-aware scheduling
    double memory_free = 1.0 - _escrow_buffer.occupancy_fraction();
    auto params = _resource_controller.update_state(memory_free);
    metrics.resource_mode = _resource_controller.get_mode();
    metrics.escrow_occupancy = _escrow_buffer.occupancy_fraction();
    
    if (params.force_purge) {
        _escrow_buffer.purge_expired_unlocked(metadata.timestamp);
    }
    
    // Step 24-26: Check for trigger
    if (_trigger_callback) {
        bool triggered = _trigger_callback(metadata.frame_id, metadata.timestamp, reference_sources);
        if (triggered) {
            metrics.triggered = true;
            // Retroactive promotion
            double window_start = metadata.timestamp - _config.trigger_horizon_seconds;
            double window_end = metadata.timestamp;
            auto candidates = _escrow_buffer.get_entries_in_window(window_start, window_end);
            
            std::vector<int> promoted_ids;
            for (auto* entry : candidates) {
                if (entry->is_promoted) continue;
                if (entry->layers.empty()) continue;
                
                auto* promoted = _escrow_buffer.promote(entry->frame_id);
                if (promoted) {
                    promoted_ids.push_back(entry->frame_id);
                    metrics.promoted_count++;
                    
                    for (const auto& lpair : entry->layers) {
                        int level = lpair.first;
                        int size = lpair.second.LH.data.size() * sizeof(double) * 3;
                        _downlink_queue.enqueue_promoted(entry->frame_id, "H" + std::to_string(level), size, entry->timestamp);
                    }
                }
            }
        }
    }
    
    // Step 27: Purge expired unlocked entries
    _escrow_buffer.purge_expired_unlocked(metadata.timestamp);
    
    // Simulate downlink during cadence
    _downlink_queue.transmit(_config.cadence_seconds);
    
    auto t_end = std::chrono::high_resolution_clock::now();
    metrics.processing_time_ms = std::chrono::duration<double, std::milli>(t_end - t_start).count();
    _metrics.push_back(metrics);
    
    return metrics;
}

} // namespace pipeline
} // namespace eventvault
