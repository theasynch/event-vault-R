#include "dwt_fixed.hpp"
#include "dwt.hpp"
#include "guardrail.hpp"
#include <iostream>
#include <fstream>
#include <vector>
#include <cmath>
#include <iomanip>

using namespace eventvault;

int main() {
    std::cout << "--- Fixed Point Accuracy Evaluation (B5-B6) ---\n";
    
    std::ifstream file("../../../verification/vectors/saved_discovery_frames.bin", std::ios::binary);
    if (!file) {
        std::cerr << "Failed to open verification file." << std::endl;
        return 1;
    }
    
    int num_frames, rows, cols;
    file.read(reinterpret_cast<char*>(&num_frames), sizeof(int));
    file.read(reinterpret_cast<char*>(&rows), sizeof(int));
    file.read(reinterpret_cast<char*>(&cols), sizeof(int));
    
    // We'll just read the 26th frame which is when the transient is bright
    int target_frame = 25;
    codec::Matrix2D frame(rows, cols);
    
    for (int i = 0; i <= target_frame; ++i) {
        int frame_id;
        double timestamp;
        file.read(reinterpret_cast<char*>(&frame_id), sizeof(int));
        file.read(reinterpret_cast<char*>(&timestamp), sizeof(double));
        file.read(reinterpret_cast<char*>(frame.data.data()), rows * cols * sizeof(double));
    }
    
    // 1. Float DWT
    auto decomp_float = codec::decompose(frame, "bior4.4", 3, "symmetric");
    auto recon_float = codec::reconstruct(decomp_float);
    
    // 2. Fixed DWT
    codec::fixed::Matrix2D_Q16 frame_q16(rows, cols);
    frame_q16.from_float(frame);
    
    auto decomp_fixed = codec::fixed::decompose(frame_q16, "bior4.4", 3, "symmetric");
    auto recon_fixed_q16 = codec::fixed::reconstruct(decomp_fixed);
    auto recon_fixed = recon_fixed_q16.to_float();
    
    // 3. Pixel Errors
    double max_err = 0;
    double sq_err_sum = 0;
    for (int i = 0; i < rows * cols; ++i) {
        double diff = std::abs(recon_float.data[i] - recon_fixed.data[i]);
        if (diff > max_err) max_err = diff;
        sq_err_sum += diff * diff;
    }
    double rmse = std::sqrt(sq_err_sum / (rows * cols));
    
    std::cout << "Q-Format: Q16.16\n";
    std::cout << "Word Length: 32-bit\n";
    std::cout << "Maximum Error (pixels): " << max_err << "\n";
    std::cout << "RMS Error (pixels): " << rmse << "\n";
    
    // 4. Science Errors
    // Use the known transient position (64, 64)
    auto meas_orig = science::measure_source(frame, 64, 64);
    auto meas_float = science::measure_source(recon_float, 64, 64);
    auto meas_fixed = science::measure_source(recon_fixed, 64, 64);
    
    double delta_F_float = std::abs(meas_float.flux - meas_orig.flux) / meas_orig.flux * 100.0;
    double delta_x_float = std::sqrt(std::pow(meas_float.x_centroid - meas_orig.x_centroid, 2) + std::pow(meas_float.y_centroid - meas_orig.y_centroid, 2));

    double delta_F_fixed = std::abs(meas_fixed.flux - meas_orig.flux) / meas_orig.flux * 100.0;
    double delta_x_fixed = std::sqrt(std::pow(meas_fixed.x_centroid - meas_orig.x_centroid, 2) + std::pow(meas_fixed.y_centroid - meas_orig.y_centroid, 2));

    std::cout << "\nScience Validation against Original Image:\n";
    std::cout << "Float DWT Delta F: " << delta_F_float << "%\n";
    std::cout << "Float DWT Delta x: " << delta_x_float << " px\n";
    std::cout << "Fixed DWT Delta F: " << delta_F_fixed << "%\n";
    std::cout << "Fixed DWT Delta x: " << delta_x_fixed << " px\n";

    if (delta_F_fixed <= 0.5 && delta_x_fixed <= 0.1) {
        std::cout << "\nSUCCESS: Fixed-point implementation meets scientific tolerances (ΔF <= 0.5%, Δx <= 0.1px)\n";
    } else {
        std::cout << "\nFAILED: Fixed-point implementation violates scientific tolerances.\n";
    }

    return 0;
}
