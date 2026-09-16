"""
Compare RTL output hex against C++ Q16.16 golden vectors.
Usage: python verification/compare_hex.py [rtl_file] [golden_file]
"""

import sys

def load_hex(path):
    vals = []
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or 'x' in line.lower():
                continue
            vals.append(int(line, 16))
    return vals

def to_signed(val):
    """Convert unsigned 32-bit to signed."""
    return val if val < 0x80000000 else val - 0x100000000

def to_float(val):
    """Convert signed Q16.16 to float."""
    return to_signed(val) / (1 << 16)

def compare(file_rtl, file_golden):
    try:
        rtl = load_hex(file_rtl)
        golden = load_hex(file_golden)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    if len(rtl) == 0:
        print("RTL output is empty!")
        return

    print(f"RTL values:    {len(rtl)}")
    print(f"Golden values: {len(golden)}")

    compare_len = min(len(rtl), len(golden))
    max_err = 0
    err_count = 0
    sum_sq_err = 0
    total_abs_err = 0

    for i in range(compare_len):
        r_val = to_signed(rtl[i])
        g_val = to_signed(golden[i])
        err = abs(r_val - g_val)
        sum_sq_err += err * err
        total_abs_err += err
        if err > max_err:
            max_err = err
        if err > 1:  # Tolerate +-1 Q16.16 LSB
            err_count += 1
            if err_count <= 10:
                print(f"  Mismatch [{i}]: RTL={to_float(rtl[i]):.4f} Golden={to_float(golden[i]):.4f} (diff_lsb={err})")

    rmse = (sum_sq_err / compare_len) ** 0.5
    mae = total_abs_err / compare_len
    print("--------------------------------------------------")
    print(f"Total Mismatches (>1 LSB): {err_count} / {compare_len}")
    print(f"Max Absolute Error:  {max_err} LSBs = {max_err / 65536:.6f}")
    print(f"Mean Absolute Error: {mae:.2f} LSBs = {mae / 65536:.6f}")
    print(f"RMSE:                {rmse:.2f} LSBs = {rmse / 65536:.6f}")

    if err_count == 0:
        print("\n[SUCCESS] RTL matches C++ Q16.16 Golden Vectors!")
    else:
        pct = 100 * err_count / compare_len
        print(f"\n[FAILURE] {pct:.1f}% of values diverged.")

if __name__ == "__main__":
    rtl_file = sys.argv[1] if len(sys.argv) > 1 else "verification/vectors/rtl_out_l0.hex"
    golden_file = sys.argv[2] if len(sys.argv) > 2 else "verification/vectors/l0_q16.hex"
    compare(rtl_file, golden_file)
