#pragma once

#include <vector>
#include <string>
#include <map>
#include <cstdint>
#include "dwt.hpp" // For Matrix2D compatibility routines

namespace eventvault {
namespace codec {
namespace fixed {

typedef int32_t q16_16_t;

// Convert double to Q16.16
inline q16_16_t double_to_q16(double val) {
    return static_cast<q16_16_t>(val * 65536.0);
}

// Convert Q16.16 to double
inline double q16_to_double(q16_16_t val) {
    return static_cast<double>(val) / 65536.0;
}

// Q16.16 Multiplication
inline q16_16_t q16_mul(q16_16_t a, q16_16_t b) {
    int64_t result = static_cast<int64_t>(a) * static_cast<int64_t>(b);
    return static_cast<q16_16_t>(result >> 16);
}

class Matrix2D_Q16 {
public:
    int rows;
    int cols;
    std::vector<q16_16_t> data;

    Matrix2D_Q16(int r = 0, int c = 0) : rows(r), cols(c), data(r * c, 0) {}

    q16_16_t& operator()(int r, int c) { return data[r * cols + c]; }
    const q16_16_t& operator()(int r, int c) const { return data[r * cols + c]; }
    
    // Conversion to/from float matrix
    void from_float(const Matrix2D& src) {
        rows = src.rows;
        cols = src.cols;
        data.resize(rows * cols);
        for (int i = 0; i < src.data.size(); ++i) {
            data[i] = double_to_q16(src.data[i]);
        }
    }
    
    Matrix2D to_float() const {
        Matrix2D dst(rows, cols);
        for (int i = 0; i < data.size(); ++i) {
            dst.data[i] = q16_to_double(data[i]);
        }
        return dst;
    }
};

struct DetailLayer_Q16 {
    Matrix2D_Q16 LH;
    Matrix2D_Q16 HL;
    Matrix2D_Q16 HH;
};

struct WaveletDecomposition_Q16 {
    Matrix2D_Q16 base_layer;
    std::map<int, DetailLayer_Q16> residual_layers;
    std::string wavelet;
    std::string mode;
    int levels;
    int original_rows;
    int original_cols;
};

WaveletDecomposition_Q16 decompose(const Matrix2D_Q16& image, const std::string& wavelet = "bior4.4", int levels = 3, const std::string& mode = "symmetric");
Matrix2D_Q16 reconstruct(const WaveletDecomposition_Q16& decomp, int max_depth = -1);

} // namespace fixed
} // namespace codec
} // namespace eventvault
