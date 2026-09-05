#include "dwt.hpp"
#include <cmath>
#include <algorithm>
#include <iostream>

namespace eventvault {
namespace codec {

// Filter definitions for DWT
struct WaveletFilters {
    std::vector<double> dec_lo;
    std::vector<double> dec_hi;
    std::vector<double> rec_lo;
    std::vector<double> rec_hi;
};

// Extracted from PyWavelets (pywt)
WaveletFilters get_filters(const std::string& name) {
    if (name == "haar") {
        return {
            {0.7071067811865476, 0.7071067811865476},
            {-0.7071067811865476, 0.7071067811865476},
            {0.7071067811865476, 0.7071067811865476},
            {0.7071067811865476, -0.7071067811865476}
        };
    } else if (name == "db4") {
        return {
            {-0.010597401785069032, 0.0328830116668852, 0.030841381835560764, -0.18703481171909309, -0.027983769416859854, 0.6308807679298589, 0.7148465705529157, 0.2303778133088965},
            {-0.2303778133088965, 0.7148465705529157, -0.6308807679298589, -0.027983769416859854, 0.18703481171909309, 0.030841381835560764, -0.0328830116668852, -0.010597401785069032},
            {0.2303778133088965, 0.7148465705529157, 0.6308807679298589, -0.027983769416859854, -0.18703481171909309, 0.030841381835560764, 0.0328830116668852, -0.010597401785069032},
            {-0.010597401785069032, -0.0328830116668852, 0.030841381835560764, 0.18703481171909309, -0.027983769416859854, -0.6308807679298589, 0.7148465705529157, -0.2303778133088965}
        };
    } else if (name == "bior4.4") {
        return {
            {0.0, 0.03782845550726404, -0.023849465019556843, -0.11062440441843718, 0.37740285561283066, 0.8526986790088938, 0.37740285561283066, -0.11062440441843718, -0.023849465019556843, 0.03782845550726404},
            {-0.0, -0.06453888262869706, 0.04068941760916406, 0.41809227322161724, -0.7884856164055829, 0.41809227322161724, 0.04068941760916406, -0.06453888262869706, -0.0, 0.0},
            {0.0, -0.06453888262869706, -0.04068941760916406, 0.41809227322161724, 0.7884856164055829, 0.41809227322161724, -0.04068941760916406, -0.06453888262869706, 0.0, 0.0},
            {0.0, -0.03782845550726404, -0.023849465019556843, 0.11062440441843718, 0.37740285561283066, -0.8526986790088938, 0.37740285561283066, 0.11062440441843718, -0.023849465019556843, -0.03782845550726404}
        };
    }
    throw std::invalid_argument("Unsupported wavelet: " + name);
}

// 1D Convolution with decimation (mode='symmetric')
void conv1d_dwt(const std::vector<double>& x, const std::vector<double>& f_lo, const std::vector<double>& f_hi, std::vector<double>& out_lo, std::vector<double>& out_hi) {
    int N = x.size();
    int F = f_lo.size();
    int out_len = (N + F - 1) / 2;
    
    out_lo.assign(out_len, 0.0);
    out_hi.assign(out_len, 0.0);
    
    for (int k = 0; k < out_len; ++k) {
        double s_lo = 0.0;
        double s_hi = 0.0;
        for (int j = 0; j < F; ++j) {
            int i = 2 * k + 1 - j;
            
            // PyWavelets symmetric (half-point) reflection
            while (i < 0 || i >= N) {
                if (i < 0) {
                    i = -1 - i;
                } else if (i >= N) {
                    i = 2 * N - 1 - i;
                }
            }
            
            s_lo += x[i] * f_lo[j];
            s_hi += x[i] * f_hi[j];
        }
        out_lo[k] = s_lo;
        out_hi[k] = s_hi;
    }
}

// 2D Single Level Decomposition
void dwt2d_single(const Matrix2D& image, const WaveletFilters& filters, Matrix2D& LL, Matrix2D& LH, Matrix2D& HL, Matrix2D& HH) {
    int M = image.rows;
    int N = image.cols;
    int F = filters.dec_lo.size();
    int out_N = (N + F - 1) / 2;
    int out_M = (M + F - 1) / 2;
    
    Matrix2D L_rows(M, out_N);
    Matrix2D H_rows(M, out_N);
    
    // 1. Process Rows
    for (int i = 0; i < M; ++i) {
        std::vector<double> row(N);
        for (int j = 0; j < N; ++j) row[j] = image(i, j);
        
        std::vector<double> l_out, h_out;
        conv1d_dwt(row, filters.dec_lo, filters.dec_hi, l_out, h_out);
        
        for (int j = 0; j < out_N; ++j) {
            L_rows(i, j) = l_out[j];
            H_rows(i, j) = h_out[j];
        }
    }
    
    LL = Matrix2D(out_M, out_N);
    LH = Matrix2D(out_M, out_N);
    HL = Matrix2D(out_M, out_N);
    HH = Matrix2D(out_M, out_N);
    
    // 2. Process Columns
    for (int j = 0; j < out_N; ++j) {
        std::vector<double> l_col(M), h_col(M);
        for (int i = 0; i < M; ++i) {
            l_col[i] = L_rows(i, j);
            h_col[i] = H_rows(i, j);
        }
        
        std::vector<double> ll_out, lh_out, hl_out, hh_out;
        conv1d_dwt(l_col, filters.dec_lo, filters.dec_hi, ll_out, lh_out);
        conv1d_dwt(h_col, filters.dec_lo, filters.dec_hi, hl_out, hh_out);
        
        for (int i = 0; i < out_M; ++i) {
            LL(i, j) = ll_out[i];
            LH(i, j) = lh_out[i];
            HL(i, j) = hl_out[i];
            HH(i, j) = hh_out[i];
        }
    }
}

// 1D IDWT Reconstruction
void conv1d_idwt(const std::vector<double>& cA, const std::vector<double>& cD, const std::vector<double>& f_lo, const std::vector<double>& f_hi, std::vector<double>& out, int N_orig) {
    int F = f_lo.size();
    int N_c = cA.size();
    int up_len = 2 * N_c;
    
    std::vector<double> cA_up(up_len, 0.0);
    std::vector<double> cD_up(up_len, 0.0);
    for (int i = 0; i < N_c; ++i) {
        cA_up[2 * i] = cA[i];
        cD_up[2 * i] = cD[i];
    }
    
    out.assign(N_orig, 0.0);
    int offset = F - 2;
    
    for (int k = 0; k < N_orig; ++k) {
        double s = 0.0;
        for (int j = 0; j < F; ++j) {
            int i = k + offset - j;
            if (i >= 0 && i < up_len) {
                s += cA_up[i] * f_lo[j] + cD_up[i] * f_hi[j];
            }
        }
        out[k] = s;
    }
}

// 2D Single Level Reconstruction
void idwt2d_single(const Matrix2D& LL, const Matrix2D& LH, const Matrix2D& HL, const Matrix2D& HH, const WaveletFilters& filters, Matrix2D& out, int original_rows, int original_cols) {
    int out_M = LL.rows;
    int out_N = LL.cols;
    
    // Reverse of decomposition:
    // 1. Reconstruct columns
    Matrix2D L_rows(original_rows, out_N);
    Matrix2D H_rows(original_rows, out_N);
    
    for (int j = 0; j < out_N; ++j) {
        std::vector<double> ll_col(out_M), lh_col(out_M), hl_col(out_M), hh_col(out_M);
        for (int i = 0; i < out_M; ++i) {
            ll_col[i] = LL(i, j);
            lh_col[i] = LH(i, j);
            hl_col[i] = HL(i, j);
            hh_col[i] = HH(i, j);
        }
        
        std::vector<double> l_out, h_out;
        conv1d_idwt(ll_col, lh_col, filters.rec_lo, filters.rec_hi, l_out, original_rows);
        conv1d_idwt(hl_col, hh_col, filters.rec_lo, filters.rec_hi, h_out, original_rows);
        
        for (int i = 0; i < original_rows; ++i) {
            L_rows(i, j) = l_out[i];
            H_rows(i, j) = h_out[i];
        }
    }
    
    // 2. Reconstruct rows
    out = Matrix2D(original_rows, original_cols);
    for (int i = 0; i < original_rows; ++i) {
        std::vector<double> l_row(out_N), h_row(out_N);
        for (int j = 0; j < out_N; ++j) {
            l_row[j] = L_rows(i, j);
            h_row[j] = H_rows(i, j);
        }
        
        std::vector<double> out_row;
        conv1d_idwt(l_row, h_row, filters.rec_lo, filters.rec_hi, out_row, original_cols);
        
        for (int j = 0; j < original_cols; ++j) {
            out(i, j) = out_row[j];
        }
    }
}

WaveletDecomposition decompose(const Matrix2D& image, const std::string& wavelet, int levels, const std::string& mode) {
    if (mode != "symmetric") {
        throw std::invalid_argument("Only 'symmetric' mode is currently implemented.");
    }

    WaveletDecomposition decomp;
    decomp.wavelet = wavelet;
    decomp.mode = mode;
    decomp.levels = levels;
    decomp.original_rows = image.rows;
    decomp.original_cols = image.cols;
    
    WaveletFilters filters = get_filters(wavelet);
    
    Matrix2D current_ll = image;
    
    for (int level = 1; level <= levels; ++level) {
        Matrix2D next_ll, lh, hl, hh;
        dwt2d_single(current_ll, filters, next_ll, lh, hl, hh);
        
        DetailLayer dl;
        dl.LH = lh;
        dl.HL = hl;
        dl.HH = hh;
        
        decomp.residual_layers[levels - level + 1] = dl;
        current_ll = next_ll;
    }
    
    decomp.base_layer = current_ll;
    return decomp;
}

Matrix2D reconstruct(const WaveletDecomposition& decomp, int max_depth) {
    WaveletFilters filters = get_filters(decomp.wavelet);
    
    int target_depth = (max_depth > 0 && max_depth <= decomp.levels) ? max_depth : decomp.levels;
    
    Matrix2D current_ll = decomp.base_layer;
    
    // Reconstruct starting from deepest level (which has the highest level index in our dict, i.e., levels)
    // Wait, in decompose we saved finest as 1, coarsest as `levels`.
    // So we reconstruct from coarsest (`levels`) down to finest (`1`).
    // But if max_depth is specified, we stop early? 
    // In eventvault, IDWT max_depth=k means we only use up to level k.
    
    // For now, let's implement full IDWT. We must determine the intermediate target sizes.
    // The sizes can be derived from the DetailLayer at that level.
    for (int level = 1; level <= decomp.levels; ++level) {
        if (level > target_depth) {
            // If we are reconstructing a truncated stream, we could pass zero matrices.
            // For now, just use the detail layers.
        }
        
        // Find the corresponding detail layer
        auto it = decomp.residual_layers.find(level);
        if (it == decomp.residual_layers.end()) {
            throw std::runtime_error("Missing detail layer for reconstruction.");
        }
        
        const DetailLayer& dl = it->second;
        
        // Calculate original shape for this step
        // If it's the finest level (level == decomp.levels), the target is original_rows x original_cols
        // Otherwise, it's the shape of the LH layer of the next finest level (level + 1)
        int target_rows = (level == decomp.levels) ? decomp.original_rows : decomp.residual_layers.at(level + 1).LH.rows;
        int target_cols = (level == decomp.levels) ? decomp.original_cols : decomp.residual_layers.at(level + 1).LH.cols;
        
        Matrix2D next_ll;
        idwt2d_single(current_ll, dl.LH, dl.HL, dl.HH, filters, next_ll, target_rows, target_cols);
        current_ll = next_ll;
    }
    
    return current_ll;
}

} // namespace codec
} // namespace eventvault
