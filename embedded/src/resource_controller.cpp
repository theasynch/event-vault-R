#include "resource_controller.hpp"
#include <algorithm>

namespace eventvault {
namespace controller {

ResourceController::ResourceController(
    double default_horizon,
    double min_horizon,
    double warning_fraction,
    double critical_fraction,
    int min_detail_level)
    : _default_horizon(default_horizon),
      _min_horizon(min_horizon),
      _warning_fraction(warning_fraction),
      _critical_fraction(critical_fraction),
      _min_detail_level(min_detail_level) 
{
    _params.trigger_horizon = default_horizon;
}

OperatingParameters ResourceController::update_state(
    double memory_free_fraction,
    double downlink_available,
    double battery_fraction) 
{
    if (memory_free_fraction >= 0.0) {
        _state.memory_free_fraction = memory_free_fraction;
    }
    if (downlink_available >= 0.0) {
        _state.downlink_available = downlink_available;
    }
    if (battery_fraction >= 0.0) {
        _state.battery_fraction = battery_fraction;
    }
    
    _params = compute_parameters(_state);
    return _params;
}

OperatingParameters ResourceController::compute_parameters(const ResourceState& state) const {
    OperatingParameters params;
    double memory_used = 1.0 - state.memory_free_fraction;
    
    if (memory_used < _warning_fraction) {
        params.trigger_horizon = _default_horizon;
        params.min_detail_level = 1;
        params.snr_threshold = 5.0;
        params.allow_new_escrow = true;
        params.force_purge = false;
    } else if (memory_used < _critical_fraction) {
        double pressure = (memory_used - _warning_fraction) / (_critical_fraction - _warning_fraction);
        double horizon = _default_horizon - pressure * (_default_horizon - _min_horizon);
        
        params.trigger_horizon = std::max(horizon, _min_horizon);
        params.min_detail_level = _min_detail_level;
        params.snr_threshold = 5.0 + 2.0 * pressure;
        params.allow_new_escrow = true;
        params.force_purge = false;
    } else {
        params.trigger_horizon = _min_horizon;
        params.min_detail_level = _min_detail_level + 1;
        params.snr_threshold = 10.0;
        params.allow_new_escrow = (state.battery_fraction > 0.2);
        params.force_purge = true;
    }
    
    if (state.battery_fraction < 0.1) {
        params.allow_new_escrow = false;
        params.min_detail_level = std::max(params.min_detail_level, 2);
    }
    
    return params;
}

std::string ResourceController::get_mode() const {
    double memory_used = 1.0 - _state.memory_free_fraction;
    if (memory_used < _warning_fraction) return "NOMINAL";
    if (memory_used < _critical_fraction) return "WARNING";
    return "CRITICAL";
}

} // namespace controller
} // namespace eventvault
