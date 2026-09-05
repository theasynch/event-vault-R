#include "telemetry.hpp"
#include <algorithm>

namespace eventvault {
namespace telemetry {

DownlinkQueue::DownlinkQueue(int bandwidth_bps, int max_queue_depth)
    : _bandwidth_bps(bandwidth_bps), _max_queue_depth(max_queue_depth) 
{
    _queues[DownlinkPriority::CRITICAL] = std::deque<DownlinkItem>();
    _queues[DownlinkPriority::PROMOTED] = std::deque<DownlinkItem>();
    _queues[DownlinkPriority::HIGH] = std::deque<DownlinkItem>();
    _queues[DownlinkPriority::NORMAL] = std::deque<DownlinkItem>();
    _queues[DownlinkPriority::LOW] = std::deque<DownlinkItem>();
}

bool DownlinkQueue::enqueue(const DownlinkItem& item) {
    if (queue_depth() >= _max_queue_depth) {
        if (!drop_lowest_priority()) {
            _stats.total_dropped++;
            return false;
        }
    }
    
    _queues[item.priority].push_back(item);
    _stats.total_queued++;
    return true;
}

bool DownlinkQueue::enqueue_base_layer(int frame_id, int size_bytes, double timestamp) {
    DownlinkItem item;
    item.frame_id = frame_id;
    item.layer = "base";
    item.priority = DownlinkPriority::CRITICAL;
    item.size_bytes = size_bytes;
    item.timestamp = timestamp;
    return enqueue(item);
}

bool DownlinkQueue::enqueue_promoted(int frame_id, const std::string& layer, int size_bytes, double timestamp) {
    DownlinkItem item;
    item.frame_id = frame_id;
    item.layer = layer;
    item.priority = DownlinkPriority::PROMOTED;
    item.size_bytes = size_bytes;
    item.timestamp = timestamp;
    return enqueue(item);
}

std::vector<DownlinkItem> DownlinkQueue::transmit(double duration_seconds) {
    double available_bits = _bandwidth_bps * duration_seconds;
    double available_bytes = available_bits / 8.0;
    
    std::vector<DownlinkItem> transmitted;
    int bytes_sent = 0;
    
    std::vector<DownlinkPriority> priorities = {
        DownlinkPriority::CRITICAL,
        DownlinkPriority::PROMOTED,
        DownlinkPriority::HIGH,
        DownlinkPriority::NORMAL,
        DownlinkPriority::LOW
    };
    
    for (auto p : priorities) {
        auto& queue = _queues[p];
        while (!queue.empty() && (bytes_sent + queue.front().size_bytes) <= available_bytes) {
            DownlinkItem item = queue.front();
            queue.pop_front();
            
            bytes_sent += item.size_bytes;
            transmitted.push_back(item);
            _transmitted.push_back(item);
            
            _stats.total_transmitted++;
            _stats.total_bytes_transmitted += item.size_bytes;
        }
    }
    
    return transmitted;
}

int DownlinkQueue::queue_depth() const {
    int depth = 0;
    for (const auto& pair : _queues) {
        depth += pair.second.size();
    }
    return depth;
}

DownlinkStatistics DownlinkQueue::get_statistics() {
    _stats.queue_depth = queue_depth();
    
    auto get_name = [](DownlinkPriority p) {
        switch(p) {
            case DownlinkPriority::CRITICAL: return "CRITICAL";
            case DownlinkPriority::PROMOTED: return "PROMOTED";
            case DownlinkPriority::HIGH: return "HIGH";
            case DownlinkPriority::NORMAL: return "NORMAL";
            case DownlinkPriority::LOW: return "LOW";
        }
        return "UNKNOWN";
    };
    
    for (const auto& pair : _queues) {
        _stats.items_by_priority[get_name(pair.first)] = pair.second.size();
    }
    
    return _stats;
}

bool DownlinkQueue::drop_lowest_priority() {
    std::vector<DownlinkPriority> priorities = {
        DownlinkPriority::LOW,
        DownlinkPriority::NORMAL,
        DownlinkPriority::HIGH,
        DownlinkPriority::PROMOTED,
        DownlinkPriority::CRITICAL
    };
    
    for (auto p : priorities) {
        auto& queue = _queues[p];
        if (!queue.empty()) {
            queue.pop_back(); // drop newest from lowest priority
            _stats.total_dropped++;
            return true;
        }
    }
    return false;
}

} // namespace telemetry
} // namespace eventvault
