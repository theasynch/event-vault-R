#pragma once
#include <string>
#include <deque>
#include <vector>
#include <map>

namespace eventvault {
namespace telemetry {

enum class DownlinkPriority {
    CRITICAL = 0,
    PROMOTED = 1,
    HIGH = 2,
    NORMAL = 3,
    LOW = 4
};

struct DownlinkItem {
    int frame_id;
    std::string layer;
    DownlinkPriority priority;
    int size_bytes;
    double timestamp;
    std::vector<char> data; // empty for simulation
};

struct DownlinkStatistics {
    int total_queued = 0;
    int total_transmitted = 0;
    int total_bytes_transmitted = 0;
    int total_dropped = 0;
    int queue_depth = 0;
    std::map<std::string, int> items_by_priority;
};

class DownlinkQueue {
public:
    DownlinkQueue(int bandwidth_bps = 9600, int max_queue_depth = 50);

    bool enqueue(const DownlinkItem& item);
    
    bool enqueue_base_layer(int frame_id, int size_bytes, double timestamp);
    bool enqueue_promoted(int frame_id, const std::string& layer, int size_bytes, double timestamp);

    std::vector<DownlinkItem> transmit(double duration_seconds);

    int queue_depth() const;
    DownlinkStatistics get_statistics();
    const std::vector<DownlinkItem>& transmitted_items() const { return _transmitted; }

private:
    bool drop_lowest_priority();

    int _bandwidth_bps;
    int _max_queue_depth;

    std::map<DownlinkPriority, std::deque<DownlinkItem>> _queues;
    DownlinkStatistics _stats;
    std::vector<DownlinkItem> _transmitted;
};

} // namespace telemetry
} // namespace eventvault
