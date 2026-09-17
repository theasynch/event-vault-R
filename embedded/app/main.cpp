#include "pipeline.hpp"
#include <iostream>
#include <fstream>
#include <vector>

using namespace eventvault;

int main() {
    std::cout << "EventVault-R C++ Embedded Verification" << std::endl;
    
    // Load config matching Saved Discovery
    pipeline::EventVaultConfig config;
    config.escrow_capacity = 70;
    config.trigger_horizon_seconds = 3600.0;
    
    int detect_frame = 25;
    
    // Trigger callback
    auto trigger_cb = [detect_frame](int frame_id, [[maybe_unused]] double ts, [[maybe_unused]] const std::vector<science::SourceMeasurement>& sources) {
        return frame_id == detect_frame;
    };
    
    pipeline::EventVaultPipeline p(config, trigger_cb);
    
    // Read binary
    std::ifstream file("../../verification/vectors/saved_discovery_frames.bin", std::ios::binary);
    if (!file) {
        std::cerr << "Failed to open verification file." << std::endl;
        return 1;
    }
    
    int num_frames, rows, cols;
    file.read(reinterpret_cast<char*>(&num_frames), sizeof(int));
    file.read(reinterpret_cast<char*>(&rows), sizeof(int));
    file.read(reinterpret_cast<char*>(&cols), sizeof(int));
    
    std::cout << "Loading " << num_frames << " frames (" << rows << "x" << cols << ")...\n";
    std::cout.flush();
    
    int promoted_frames = 0;
    
    for (int i = 0; i < num_frames; ++i) {
        std::cout << "Processing frame " << i << "...\n"; std::cout.flush();
        int frame_id;
        double timestamp;
        file.read(reinterpret_cast<char*>(&frame_id), sizeof(int));
        file.read(reinterpret_cast<char*>(&timestamp), sizeof(double));
        
        codec::Matrix2D frame(rows, cols);
        file.read(reinterpret_cast<char*>(frame.data.data()), rows * cols * sizeof(double));
        
        pipeline::FrameMetadata meta{frame_id, timestamp};
        auto metrics = p.process_frame(frame, meta);
        
        if (metrics.triggered) {
            std::cout << "Trigger received at frame " << frame_id << "\n";
            std::cout << "Promoted " << metrics.promoted_count << " pre-trigger frames from escrow!\n";
            promoted_frames += metrics.promoted_count;
        }
    }
    
    std::cout << "Processing Complete. Promoted " << promoted_frames << " frames total.\n";
    if (promoted_frames >= 15) {
        std::cout << "SUCCESS: Recovered pre-trigger photometric frames!" << std::endl;
    } else {
        std::cout << "FAILED: Did not recover enough pre-trigger frames." << std::endl;
        return 1;
    }
    
    return 0;
}
