#include "dwt_fixed.hpp"
#include <cmath>
#include <algorithm>
#include <iostream>
#include <stdexcept>

namespace eventvault {
namespace codec {
namespace fixed {

struct WaveletFilters_Q16 {
    std::vector<q16_16_t> dec_lo;
    std::vector<q16_16_t> dec_hi;
    std::vector<q16_16_t> rec_lo;
    std::vector<q16_16_t> rec_hi;
};

// Convert float filters to Q16.16
WaveletFilters_Q16 get_filters_q16(const std::string& name) {
    if (name == "bior4.4") {
        return {
            {0, 2479, -1563, -7250, 24733, 55882, 24733, -7250, -1563, 2479},
            {0, -4229, 2666, 27400, -51674, 27400, 2666, -4229, 0, 0},
            {0, -4229, -2666, 27400, 51674, 27400, -2666, -4229, 0, 0},
            {0, -2479, -1563, 7250, 24733, -55882, 24733, 7250, -1563, -2479}
        }; // pre-calculated from double_to_q16
    }
    throw std::invalid_argument("Unsupported fixed-point wavelet: " + name);
}

void conv1d_dwt(const std::vector<q16_16_t>& x, const std::vector<q16_16_t>& f_lo, const std::vector<q16_16_t>& f_hi, std::vector<q16_16_t>& out_lo, std::vector<q16_16_t>& out_hi) {
    int N = x.size();
    int F = f_lo.size();
    int out_len = (N + F - 1) / 2;
    
    out_lo.assign(out_len, 0);
    out_hi.assign(out_len, 0);
    
    for (int k = 0; k < out_len; ++k) {
        int64_t s_lo = 0;
        int64_t s_hi = 0;
        for (int j = 0; j < F; ++j) {
            int i = 2 * k + 1 - j;
            while (i < 0 || i >= N) {
                if (i < 0) {
                    i = -1 - i;
                } else if (i >= N) {
                    i = 2 * N - 1 - i;
                }
            }
            s_lo += static_cast<int64_t>(x[i]) * static_cast<int64_t>(f_lo[j]);
            s_hi += static_cast<int64_t>(x[i]) * static_cast<int64_t>(f_hi[j]);
        }
        out_lo[k] = static_cast<q16_16_t>(s_lo >> 16);
        out_hi[k] = static_cast<q16_16_t>(s_hi >> 16);
    }
}

void dwt2d_single(const Matrix2D_Q16& image, const WaveletFilters_Q16& filters, Matrix2D_Q16& LL, Matrix2D_Q16& LH, Matrix2D_Q16& HL, Matrix2D_Q16& HH) {
    int M = image.rows;
    int N = image.cols;
    int F = filters.dec_lo.size();
    int out_N = (N + F - 1) / 2;
    int out_M = (M + F - 1) / 2;
    
    Matrix2D_Q16 L_rows(M, out_N);
    Matrix2D_Q16 H_rows(M, out_N);
    
    for (int i = 0; i < M; ++i) {
        std::vector<q16_16_t> row(N);
        for (int j = 0; j < N; ++j) row[j] = image(i, j);
        
        std::vector<q16_16_t> l_out, h_out;
        conv1d_dwt(row, filters.dec_lo, filters.dec_hi, l_out, h_out);
        
        for (int j = 0; j < out_N; ++j) {
            L_rows(i, j) = l_out[j];
            H_rows(i, j) = h_out[j];
        }
    }
    
    LL = Matrix2D_Q16(out_M, out_N);
    LH = Matrix2D_Q16(out_M, out_N);
    HL = Matrix2D_Q16(out_M, out_N);
    HH = Matrix2D_Q16(out_M, out_N);
    
    for (int j = 0; j < out_N; ++j) {
        std::vector<q16_16_t> l_col(M), h_col(M);
        for (int i = 0; i < M; ++i) {
            l_col[i] = L_rows(i, j);
            h_col[i] = H_rows(i, j);
        }
        
        std::vector<q16_16_t> ll_out, lh_out, hl_out, hh_out;
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

WaveletDecomposition_Q16 decompose(const Matrix2D_Q16& image, const std::string& wavelet, int levels, const std::string& mode) {
    if (mode != "symmetric") {
        throw std::invalid_argument("Only 'symmetric' mode is currently implemented.");
    }

    WaveletDecomposition_Q16 decomp;
    decomp.wavelet = wavelet;
    decomp.mode = mode;
    decomp.levels = levels;
    decomp.original_rows = image.rows;
    decomp.original_cols = image.cols;
    
    WaveletFilters_Q16 filters = get_filters_q16(wavelet);
    
    Matrix2D_Q16 current_ll = image;
    
    for (int level = 1; level <= levels; ++level) {
        Matrix2D_Q16 next_ll, lh, hl, hh;
        dwt2d_single(current_ll, filters, next_ll, lh, hl, hh);
        
        DetailLayer_Q16 dl;
        dl.LH = lh;
        dl.HL = hl;
        dl.HH = hh;
        
        decomp.residual_layers[levels - level + 1] = dl;
        current_ll = next_ll;
    }
    
    decomp.base_layer = current_ll;
    return decomp;
}

void conv1d_idwt(const std::vector<q16_16_t>& cA, const std::vector<q16_16_t>& cD, const std::vector<q16_16_t>& f_lo, const std::vector<q16_16_t>& f_hi, std::vector<q16_16_t>& out, int N_orig) {
    int F = f_lo.size();
    int N_c = cA.size();
    int up_len = 2 * N_c;
    
    std::vector<q16_16_t> cA_up(up_len, 0);
    std::vector<q16_16_t> cD_up(up_len, 0);
    for (int i = 0; i < N_c; ++i) {
        cA_up[2 * i] = cA[i];
        cD_up[2 * i] = cD[i];
    }
    
    out.assign(N_orig, 0);
    int offset = F - 2;
    
    for (int k = 0; k < N_orig; ++k) {
        int64_t s = 0;
        for (int j = 0; j < F; ++j) {
            int i = k + offset - j;
            if (i >= 0 && i < up_len) {
                s += static_cast<int64_t>(cA_up[i]) * static_cast<int64_t>(f_lo[j]);
                s += static_cast<int64_t>(cD_up[i]) * static_cast<int64_t>(f_hi[j]);
            }
        }
        out[k] = static_cast<q16_16_t>(s >> 16);
    }
}

void idwt2d_single(const Matrix2D_Q16& LL, const Matrix2D_Q16& LH, const Matrix2D_Q16& HL, const Matrix2D_Q16& HH, const WaveletFilters_Q16& filters, Matrix2D_Q16& out, int original_rows, int original_cols) {
    int out_M = LL.rows;
    int out_N = LL.cols;
    
    Matrix2D_Q16 L_rows(original_rows, out_N);
    Matrix2D_Q16 H_rows(original_rows, out_N);
    
    for (int j = 0; j < out_N; ++j) {
        std::vector<q16_16_t> ll_col(out_M), lh_col(out_M), hl_col(out_M), hh_col(out_M);
        for (int i = 0; i < out_M; ++i) {
            ll_col[i] = LL(i, j);
            lh_col[i] = LH(i, j);
            hl_col[i] = HL(i, j);
            hh_col[i] = HH(i, j);
        }
        
        std::vector<q16_16_t> l_out, h_out;
        conv1d_idwt(ll_col, lh_col, filters.rec_lo, filters.rec_hi, l_out, original_rows);
        conv1d_idwt(hl_col, hh_col, filters.rec_lo, filters.rec_hi, h_out, original_rows);
        
        for (int i = 0; i < original_rows; ++i) {
            L_rows(i, j) = l_out[i];
            H_rows(i, j) = h_out[i];
        }
    }
    
    out = Matrix2D_Q16(original_rows, original_cols);
    for (int i = 0; i < original_rows; ++i) {
        std::vector<q16_16_t> l_row(out_N), h_row(out_N);
        for (int j = 0; j < out_N; ++j) {
            l_row[j] = L_rows(i, j);
            h_row[j] = H_rows(i, j);
        }
        
        std::vector<q16_16_t> out_row;
        conv1d_idwt(l_row, h_row, filters.rec_lo, filters.rec_hi, out_row, original_cols);
        
        for (int j = 0; j < original_cols; ++j) {
            out(i, j) = out_row[j];
        }
    }
}

// 2D Full Reconstruction
Matrix2D_Q16 reconstruct(const WaveletDecomposition_Q16& decomp, [[maybe_unused]] int max_depth) {
    WaveletFilters_Q16 filters = get_filters_q16(decomp.wavelet);
    
    Matrix2D_Q16 current_ll = decomp.base_layer;
    
    for (int level = 1; level <= decomp.levels; ++level) {
        auto it = decomp.residual_layers.find(level);
        if (it == decomp.residual_layers.end()) {
            throw std::runtime_error("Missing detail layer for reconstruction.");
        }
        const DetailLayer_Q16& dl = it->second;
        
        int target_rows = (level == decomp.levels) ? decomp.original_rows : decomp.residual_layers.at(level + 1).LH.rows;
        int target_cols = (level == decomp.levels) ? decomp.original_cols : decomp.residual_layers.at(level + 1).LH.cols;
        
        Matrix2D_Q16 next_ll;
        idwt2d_single(current_ll, dl.LH, dl.HL, dl.HH, filters, next_ll, target_rows, target_cols);
        current_ll = next_ll;
    }
    
    return current_ll;
}

} // namespace fixed
} // namespace codec
} // namespace eventvault
