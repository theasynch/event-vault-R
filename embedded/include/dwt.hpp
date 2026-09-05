#pragma once

#include <vector>
#include <string>
#include <map>
#include <stdexcept>

namespace eventvault {
namespace codec {

// A simple 2D matrix abstraction to avoid external dependencies (e.g., Eigen)
class Matrix2D {
public:
    int rows;
    int cols;
    std::vector<double> data;

    Matrix2D(int r = 0, int c = 0) : rows(r), cols(c), data(r * c, 0.0) {}

    double& operator()(int r, int c) {
        return data[r * cols + c];
    }

    const double& operator()(int r, int c) const {
        return data[r * cols + c];
    }
};

// Represents a single detail level: (LH, HL, HH)
struct DetailLayer {
    Matrix2D LH;
    Matrix2D HL;
    Matrix2D HH;
};

struct WaveletDecomposition {
    Matrix2D base_layer; // L0
    std::map<int, DetailLayer> residual_layers; // H1, H2, H3 (1 is finest detail)
    std::string wavelet;
    std::string mode;
    int levels;
    int original_rows;
    int original_cols;
};

WaveletDecomposition decompose(const Matrix2D& image, const std::string& wavelet = "bior4.4", int levels = 3, const std::string& mode = "symmetric");
Matrix2D reconstruct(const WaveletDecomposition& decomp, int max_depth = -1);

} // namespace codec
} // namespace eventvault
