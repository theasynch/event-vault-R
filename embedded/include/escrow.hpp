#pragma once

#include "dwt.hpp"
#include <map>
#include <vector>
#include <list>
#include <memory>
#include <optional>
#include <limits>
#include <stdexcept>
#include <string>

namespace eventvault {
namespace escrow {

enum class RetentionClass {
    ESCROW,
    LOCKED,
    PROMOTED,
    UNLOCKED,
    PURGED
};

struct LayerInfo {
    int level;
    int byte_size;
    RetentionClass retention_class = RetentionClass::ESCROW;
    bool guardrail_safe = false;
};

struct EscrowEntry {
    int frame_id;
    double timestamp;
    std::map<int, codec::DetailLayer> layers;
    std::map<int, LayerInfo> layer_info;
    int source_count = 0;
    double uncertainty_score = 0.0;
    double retention_utility = 0.0;
    double trigger_horizon_expiry = std::numeric_limits<double>::infinity();
    bool is_locked = false;
    bool is_promoted = false;

    int total_bytes() const {
        int total = 0;
        for (const auto& pair : layers) {
            const auto& layer = pair.second;
            total += layer.LH.data.size() * sizeof(double) * 3; 
        }
        return total;
    }
    
    RetentionClass get_retention_class() const {
        if (is_promoted) return RetentionClass::PROMOTED;
        if (is_locked) return RetentionClass::LOCKED;
        for (const auto& pair : layer_info) {
            if (pair.second.retention_class == RetentionClass::LOCKED) return RetentionClass::LOCKED;
        }
        return RetentionClass::ESCROW;
    }
    
    void lock() {
        is_locked = true;
        for (auto& pair : layer_info) {
            pair.second.retention_class = RetentionClass::LOCKED;
        }
    }
    
    void unlock_layer(int level) {
        if (layer_info.find(level) != layer_info.end()) {
            layer_info[level].retention_class = RetentionClass::UNLOCKED;
            layer_info[level].guardrail_safe = true;
        }
    }
    
    void promote() {
        is_promoted = true;
        is_locked = true;
        for (auto& pair : layer_info) {
            pair.second.retention_class = RetentionClass::PROMOTED;
        }
    }
    
    bool is_expired(double current_time) const {
        return current_time > trigger_horizon_expiry;
    }
    
    bool can_purge(double current_time) const {
        if (is_locked || is_promoted) return false;
        return is_expired(current_time);
    }
};

struct EscrowStats {
    int capacity;
    int size;
    double occupancy;
    int total_bytes;
    int locked;
    int promoted;
    int total_pushed;
    int total_purged;
    int total_promoted;
    int uncontrolled_losses;
};

class EscrowBufferOverflowError : public std::runtime_error {
public:
    EscrowBufferOverflowError(const std::string& msg) : std::runtime_error(msg) {}
};

class EscrowBuffer {
public:
    EscrowBuffer(int capacity = 100, double trigger_horizon_seconds = 1800.0);
    
    EscrowEntry* push(
        int frame_id,
        double timestamp,
        const std::map<int, codec::DetailLayer>& residual_layers,
        double uncertainty_score = 0.0,
        int source_count = 0,
        double horizon_override = -1.0
    );
    
    EscrowEntry* get(int frame_id);
    bool lock(int frame_id);
    bool unlock_layer(int frame_id, int layer);
    EscrowEntry* promote(int frame_id);
    
    std::vector<int> purge_expired_unlocked(double current_time);
    bool purge_layer(int frame_id, int layer);
    
    int size() const { return _entries.size(); }
    bool is_full() const { return _entries.size() >= _capacity; }
    double occupancy_fraction() const { return _capacity > 0 ? (double)_entries.size() / _capacity : 0.0; }
    int total_bytes() const;
    int uncontrolled_losses() const { return _uncontrolled_losses; }
    
    std::vector<EscrowEntry*> get_entries_in_window(double start_time, double end_time);
    std::vector<EscrowEntry*> get_promoted_entries();
    EscrowStats get_statistics() const;

private:
    bool evict_one(double current_time);

    int _capacity;
    double _trigger_horizon_seconds;
    
    std::list<EscrowEntry> _entries;
    std::map<int, std::list<EscrowEntry>::iterator> _entry_map;
    
    int _total_pushed = 0;
    int _total_purged = 0;
    int _total_promoted = 0;
    int _uncontrolled_losses = 0;
};

} // namespace escrow
} // namespace eventvault
