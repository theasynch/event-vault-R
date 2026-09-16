"""
Generate Q16.16 fixed-point golden vectors that exactly replicate the C++ dwt_fixed.cpp
conv1d_dwt algorithm. These are the true RTL reference vectors.

The C++ algorithm:
  out_len = (N + F - 1) / 2
  for k in range(out_len):
      s_lo = s_hi = 0
      for j in range(F):
          i = 2*k + 1 - j
          # symmetric reflection boundary
          while i < 0 or i >= N:
              if i < 0: i = -1 - i
              elif i >= N: i = 2*N - 1 - i
          s_lo += x[i] * f_lo[j]  (64-bit)
          s_hi += x[i] * f_hi[j]  (64-bit)
      out_lo[k] = s_lo >> 16
      out_hi[k] = s_hi >> 16
"""

import struct
import numpy as np
import json
import os

# Q16.16 bior4.4 coefficients (from dwt_fixed.cpp)
DEC_LO = [0, 2479, -1563, -7250, 24733, 55882, 24733, -7250, -1563, 2479]
DEC_HI = [0, -4229, 2666, 27400, -51674, 27400, 2666, -4229, 0, 0]

def float_to_q16(val):
    """Convert float to signed Q16.16 (stored as int32)."""
    return int(round(val * (1 << 16)))

def q16_to_float(val):
    """Convert signed Q16.16 int32 to float."""
    return val / (1 << 16)

def q16_to_hex(val):
    """Convert signed int32 to unsigned 32-bit hex string."""
    return f"{val & 0xFFFFFFFF:08X}"

def conv1d_dwt_q16(x, f_lo, f_hi):
    """Exact replica of C++ conv1d_dwt using Q16.16 integer math."""
    N = len(x)
    F = len(f_lo)
    out_len = (N + F - 1) // 2
    
    out_lo = [0] * out_len
    out_hi = [0] * out_len
    
    for k in range(out_len):
        s_lo = 0
        s_hi = 0
        for j in range(F):
            i = 2 * k + 1 - j
            # Symmetric boundary reflection (same as C++)
            while i < 0 or i >= N:
                if i < 0:
                    i = -1 - i
                elif i >= N:
                    i = 2 * N - 1 - i
            s_lo += x[i] * f_lo[j]
            s_hi += x[i] * f_hi[j]
        out_lo[k] = s_lo >> 16  # arithmetic right shift
        out_hi[k] = s_hi >> 16
    
    return out_lo, out_hi

def dwt2d_single_q16(image_q16, rows, cols):
    """Exact replica of C++ dwt2d_single."""
    F = len(DEC_LO)
    out_N = (cols + F - 1) // 2
    out_M = (rows + F - 1) // 2
    
    # Row DWT
    L_rows = [[0]*out_N for _ in range(rows)]
    H_rows = [[0]*out_N for _ in range(rows)]
    
    for i in range(rows):
        row = [image_q16[i][j] for j in range(cols)]
        l_out, h_out = conv1d_dwt_q16(row, DEC_LO, DEC_HI)
        for j in range(out_N):
            L_rows[i][j] = l_out[j]
            H_rows[i][j] = h_out[j]
    
    # Column DWT
    LL = [[0]*out_N for _ in range(out_M)]
    LH = [[0]*out_N for _ in range(out_M)]
    HL = [[0]*out_N for _ in range(out_M)]
    HH = [[0]*out_N for _ in range(out_M)]
    
    for j in range(out_N):
        l_col = [L_rows[i][j] for i in range(rows)]
        h_col = [H_rows[i][j] for i in range(rows)]
        
        ll_out, lh_out = conv1d_dwt_q16(l_col, DEC_LO, DEC_HI)
        hl_out, hh_out = conv1d_dwt_q16(h_col, DEC_LO, DEC_HI)
        
        for i in range(out_M):
            LL[i][j] = ll_out[i]
            LH[i][j] = lh_out[i]
            HL[i][j] = hl_out[i]
            HH[i][j] = hh_out[i]
    
    return LL, LH, HL, HH, out_M, out_N

def write_hex(filename, data_2d, rows, cols):
    """Write 2D array of Q16.16 ints as hex file."""
    with open(filename, 'w') as f:
        for i in range(rows):
            for j in range(cols):
                f.write(q16_to_hex(data_2d[i][j]) + "\n")

def main():
    out_dir = os.path.join(os.path.dirname(__file__), 'vectors')
    os.makedirs(out_dir, exist_ok=True)
    
    # Load the same 64x64 input image
    np.random.seed(42)
    image = np.random.rand(64, 64) * 255.0
    
    ROWS, COLS = 64, 64
    
    # Convert to Q16.16
    image_q16 = [[float_to_q16(image[i][j]) for j in range(COLS)] for i in range(ROWS)]
    
    # Write input hex
    write_hex(os.path.join(out_dir, 'image_001.hex'), image_q16, ROWS, COLS)
    
    # 3-level decomposition
    current = image_q16
    cur_rows, cur_cols = ROWS, COLS
    
    levels_data = {}
    
    for level in range(1, 4):
        LL, LH, HL, HH, out_M, out_N = dwt2d_single_q16(current, cur_rows, cur_cols)
        levels_data[level] = {'LH': LH, 'HL': HL, 'HH': HH, 'rows': out_M, 'cols': out_N}
        
        prefix = f"h{4-level}"  # H3 = level 1, H2 = level 2, H1 = level 3 (matching EventVault convention)
        write_hex(os.path.join(out_dir, f'{prefix}_lh_q16.hex'), LH, out_M, out_N)
        write_hex(os.path.join(out_dir, f'{prefix}_hl_q16.hex'), HL, out_M, out_N)
        write_hex(os.path.join(out_dir, f'{prefix}_hh_q16.hex'), HH, out_M, out_N)
        write_hex(os.path.join(out_dir, f'l{level}_q16.hex'), LL, out_M, out_N)
        
        print(f"Level {level}: {cur_rows}x{cur_cols} -> {out_M}x{out_N}")
        current = LL
        cur_rows, cur_cols = out_M, out_N
    
    # Write L0 (base layer = LL after 3 levels)
    write_hex(os.path.join(out_dir, 'l0_q16.hex'), current, cur_rows, cur_cols)
    print(f"L0 (base): {cur_rows}x{cur_cols} = {cur_rows * cur_cols} values")
    
    # Metadata
    meta = {
        'wavelet': 'bior4.4',
        'format': 'Q16.16',
        'levels': 3,
        'mode': 'symmetric',
        'original_shape': [ROWS, COLS],
        'l0_shape': [cur_rows, cur_cols],
    }
    for level in range(1, 4):
        d = levels_data[level]
        meta[f'level_{level}_shape'] = [d['rows'], d['cols']]
    
    with open(os.path.join(out_dir, 'metadata_q16.json'), 'w') as f:
        json.dump(meta, f, indent=2)
    
    print(f"\nGenerated C++ Q16.16 golden vectors in {out_dir}/")
    
    # Verify a few values
    print(f"\nFirst 5 L0 values (Q16.16 hex):")
    for i in range(min(5, cur_rows)):
        print(f"  [{i}][0] = {q16_to_hex(current[i][0])} = {q16_to_float(current[i][0]):.4f}")

if __name__ == "__main__":
    main()
