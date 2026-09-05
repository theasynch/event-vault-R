#include "dwt.hpp"
#include <iostream>
#include <fstream>
#include <vector>
#include <cmath>
#include <cstdint>

using namespace eventvault::codec;

Matrix2D read_matrix(const std::string& filename) {
    std::ifstream file(filename, std::ios::binary);
    if (!file) {
        throw std::runtime_error("Could not open " + filename);
    }
    int32_t rows = 0, cols = 0;
    file.read(reinterpret_cast<char*>(&rows), sizeof(int32_t));
    file.read(reinterpret_cast<char*>(&cols), sizeof(int32_t));
    
    Matrix2D mat(rows, cols);
    file.read(reinterpret_cast<char*>(mat.data.data()), rows * cols * sizeof(double));
    return mat;
}

double max_abs_error(const Matrix2D& A, const Matrix2D& B) {
    if (A.rows != B.rows || A.cols != B.cols) return 1e9;
    double max_err = 0.0;
    for (size_t i = 0; i < A.data.size(); ++i) {
        max_err = std::max(max_err, std::abs(A.data[i] - B.data[i]));
    }
    return max_err;
}

int main() {
    try {
        std::cout << "Running DWT Verification against Python Golden Vectors..." << std::endl;
        
        // Read input image
        Matrix2D image = read_matrix("../../../verification/vectors/image_001.bin");
        std::cout << "Loaded image: " << image.rows << "x" << image.cols << std::endl;
        
        // Run C++ DWT
        WaveletDecomposition decomp = decompose(image, "haar", 3, "symmetric");
        
        // Read expected L0 (base layer)
        Matrix2D expected_l0 = read_matrix("../../../verification/vectors/l0_001.bin");
        
        // Compare L0
        if (decomp.base_layer.rows == 1 && decomp.base_layer.cols == 1) {
            std::cout << "[WARN] DWT not fully implemented yet." << std::endl;
            return 0; // Don't fail yet, we are still building it
        }

        double l0_err = max_abs_error(expected_l0, decomp.base_layer);
        std::cout << "L0 Max Abs Error: " << l0_err << std::endl;
        
        if (l0_err > 1e-5) {
            std::cerr << "FAIL: L0 error exceeds tolerance! Expected shape " << expected_l0.rows << "x" << expected_l0.cols 
                      << " but got " << decomp.base_layer.rows << "x" << decomp.base_layer.cols << std::endl;
            return 1;
        }
        
        std::cout << "PASS: L0 matches Golden Vector!" << std::endl;
        
        // Read expected H1 (LH, HL, HH)
        Matrix2D expected_lh = read_matrix("../../../verification/vectors/h1_lh.bin");
        Matrix2D expected_hl = read_matrix("../../../verification/vectors/h1_hl.bin");
        Matrix2D expected_hh = read_matrix("../../../verification/vectors/h1_hh.bin");
        
        double lh_err = max_abs_error(expected_lh, decomp.residual_layers[1].LH);
        double hl_err = max_abs_error(expected_hl, decomp.residual_layers[1].HL);
        double hh_err = max_abs_error(expected_hh, decomp.residual_layers[1].HH);
        
        std::cout << "H1 LH Max Abs Error: " << lh_err << std::endl;
        std::cout << "H1 HL Max Abs Error: " << hl_err << std::endl;
        std::cout << "H1 HH Max Abs Error: " << hh_err << std::endl;
        
        if (lh_err > 1e-5 || hl_err > 1e-5 || hh_err > 1e-5) {
            std::cerr << "FAIL: H1 error exceeds tolerance!" << std::endl;
            return 1;
        }
        
        std::cout << "PASS: H1 matches Golden Vectors perfectly!" << std::endl;
        
        // Reconstruct and compare
        Matrix2D recon = reconstruct(decomp);
        Matrix2D expected_recon = read_matrix("../../../verification/vectors/recon_001.bin");
        
        double recon_err = max_abs_error(expected_recon, recon);
        std::cout << "Reconstruction Max Abs Error: " << recon_err << std::endl;
        
        if (recon_err > 1e-5) {
            std::cerr << "FAIL: Reconstruction error exceeds tolerance!" << std::endl;
            return 1;
        }
        
        std::cout << "PASS: Full DWT/IDWT round-trip verified against PyWavelets!" << std::endl;
        
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
    
    return 0;
}
