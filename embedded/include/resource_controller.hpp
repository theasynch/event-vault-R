#pragma once
#include <string>

namespace eventvault {
namespace controller {

struct ResourceState {
    double memory_free_fraction = 1.0;
    double downlink_available = 1.0;
    double battery_fraction = 1.0;
};

struct OperatingParameters {
    double trigger_horizon = 1800.0;
    int min_detail_level = 1;
    double snr_threshold = 5.0;
    bool allow_new_escrow = true;
    bool force_purge = false;
};

class ResourceController {
public:
    ResourceController(
        double default_horizon = 1800.0,
        double min_horizon = 300.0,
        double warning_fraction = 0.7,
        double critical_fraction = 0.9,
        int min_detail_level = 1
    );

    OperatingParameters update_state(
        double memory_free_fraction = -1.0,
        double downlink_available = -1.0,
        double battery_fraction = -1.0
    );

    ResourceState get_state() const { return _state; }
    OperatingParameters get_parameters() const { return _params; }
    std::string get_mode() const;

private:
    OperatingParameters compute_parameters(const ResourceState& state) const;

    double _default_horizon;
    double _min_horizon;
    double _warning_fraction;
    double _critical_fraction;
    int _min_detail_level;

    ResourceState _state;
    OperatingParameters _params;
};

} // namespace controller
} // namespace eventvault
