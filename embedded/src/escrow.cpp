#include "escrow.hpp"
#include <iostream>

namespace eventvault {
namespace escrow {

EscrowBuffer::EscrowBuffer(size_t capacity, double trigger_horizon_seconds)
    : _capacity(capacity), _trigger_horizon_seconds(trigger_horizon_seconds) {}

EscrowEntry* EscrowBuffer::push(
    int frame_id,
    double timestamp,
    const std::map<int, codec::DetailLayer>& residual_layers,
    double uncertainty_score,
    int source_count,
    double horizon_override)
{
    if (_entries.size() >= _capacity) {
        if (!evict_one(timestamp)) {
            _uncontrolled_losses++;
            throw EscrowBufferOverflowError(
                "Buffer full, all entries are locked or unexpired. Cannot push without data loss."
            );
        }
    }
    
    double horizon = (horizon_override > 0.0) ? horizon_override : _trigger_horizon_seconds;
    
    EscrowEntry entry;
    entry.frame_id = frame_id;
    entry.timestamp = timestamp;
    entry.layers = residual_layers;
    entry.uncertainty_score = uncertainty_score;
    entry.source_count = source_count;
    entry.trigger_horizon_expiry = timestamp + horizon;
    
    for (const auto& pair : residual_layers) {
        int level = pair.first;
        const auto& lh = pair.second.LH;
        
        LayerInfo info;
        info.level = level;
        info.byte_size = lh.data.size() * sizeof(double) * 3;
        info.retention_class = RetentionClass::ESCROW;
        
        entry.layer_info[level] = info;
    }
    
    _entries.push_back(std::move(entry));
    auto it = std::prev(_entries.end());
    _entry_map[frame_id] = it;
    
    _total_pushed++;
    
    return &(*it);
}

EscrowEntry* EscrowBuffer::get(int frame_id) {
    auto it = _entry_map.find(frame_id);
    if (it != _entry_map.end()) {
        return &(*it->second);
    }
    return nullptr;
}

bool EscrowBuffer::lock(int frame_id) {
    EscrowEntry* entry = get(frame_id);
    if (entry) {
        entry->lock();
        return true;
    }
    return false;
}

bool EscrowBuffer::unlock_layer(int frame_id, int layer) {
    EscrowEntry* entry = get(frame_id);
    if (entry) {
        entry->unlock_layer(layer);
        return true;
    }
    return false;
}

EscrowEntry* EscrowBuffer::promote(int frame_id) {
    EscrowEntry* entry = get(frame_id);
    if (entry) {
        entry->promote();
        _total_promoted++;
        return entry;
    }
    return nullptr;
}

std::vector<int> EscrowBuffer::purge_expired_unlocked(double current_time) {
    std::vector<int> to_purge;
    for (const auto& entry : _entries) {
        if (entry.can_purge(current_time)) {
            to_purge.push_back(entry.frame_id);
        }
    }
    
    for (int frame_id : to_purge) {
        _entries.erase(_entry_map[frame_id]);
        _entry_map.erase(frame_id);
        _total_purged++;
    }
    
    return to_purge;
}

bool EscrowBuffer::purge_layer(int frame_id, int layer) {
    EscrowEntry* entry = get(frame_id);
    if (!entry) return false;
    
    auto it = entry->layer_info.find(layer);
    if (it == entry->layer_info.end()) return false;
    
    if (it->second.retention_class != RetentionClass::UNLOCKED) return false;
    
    entry->layers.erase(layer);
    it->second.retention_class = RetentionClass::PURGED;
    
    return true;
}

int EscrowBuffer::total_bytes() const {
    int total = 0;
    for (const auto& entry : _entries) {
        total += entry.total_bytes();
    }
    return total;
}

std::vector<EscrowEntry*> EscrowBuffer::get_entries_in_window(double start_time, double end_time) {
    std::vector<EscrowEntry*> result;
    for (auto& entry : _entries) {
        if (entry.timestamp >= start_time && entry.timestamp <= end_time) {
            result.push_back(&entry);
        }
    }
    return result;
}

std::vector<EscrowEntry*> EscrowBuffer::get_promoted_entries() {
    std::vector<EscrowEntry*> result;
    for (auto& entry : _entries) {
        if (entry.is_promoted) {
            result.push_back(&entry);
        }
    }
    return result;
}

EscrowStats EscrowBuffer::get_statistics() const {
    EscrowStats stats;
    stats.capacity = _capacity;
    stats.size = size();
    stats.occupancy = occupancy_fraction();
    stats.total_bytes = total_bytes();
    stats.total_pushed = _total_pushed;
    stats.total_purged = _total_purged;
    stats.total_promoted = _total_promoted;
    stats.uncontrolled_losses = _uncontrolled_losses;
    
    int locked = 0, promoted = 0;
    for (const auto& entry : _entries) {
        if (entry.is_promoted) promoted++;
        else if (entry.is_locked) locked++;
    }
    stats.locked = locked;
    stats.promoted = promoted;
    
    return stats;
}

bool EscrowBuffer::evict_one(double current_time) {
    // 1. Find expired unlocked entries (oldest first)
    for (auto it = _entries.begin(); it != _entries.end(); ++it) {
        if (it->can_purge(current_time)) {
            _entry_map.erase(it->frame_id);
            _entries.erase(it);
            _total_purged++;
            return true;
        }
    }
    
    // 2. Find any unlocked entry (oldest first)
    for (auto it = _entries.begin(); it != _entries.end(); ++it) {
        if (!it->is_locked && !it->is_promoted) {
            _entry_map.erase(it->frame_id);
            _entries.erase(it);
            _total_purged++;
            return true;
        }
    }
    
    return false;
}

} // namespace escrow
} // namespace eventvault
