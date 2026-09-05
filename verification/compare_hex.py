import sys

def load_hex(path):
    with open(path, 'r') as f:
        return [int(line.strip(), 16) for line in f if line.strip()]

def to_signed(val):
    return val if val < 0x80000000 else val - 0x100000000

def compare(file_rtl, file_py):
    try:
        rtl = load_hex(file_rtl)
        py = load_hex(file_py)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    if len(rtl) == 0:
        print("RTL output is empty!")
        return

    print(f"RTL length: {len(rtl)}, Python length: {len(py)}")

    # We only compare up to the length of the RTL output
    compare_len = min(len(rtl), len(py))
    max_err = 0
    err_count = 0
    sum_sq_err = 0

    for i in range(compare_len):
        r_val = to_signed(rtl[i])
        p_val = to_signed(py[i])
        err = abs(r_val - p_val)
        sum_sq_err += err * err
        if err > max_err:
            max_err = err
        if err > 1: # tolerate +-1 Q16.16 LSB quantization diff
            err_count += 1
            if err_count <= 5:
                print(f"Mismatch at index {i}: RTL={r_val} Py={p_val} (diff={err})")

    rmse = (sum_sq_err / compare_len) ** 0.5
    print("--------------------------------------------------")
    print(f"Total Mismatches (>1 LSB): {err_count} / {compare_len}")
    print(f"Max Absolute Error (Q16.16): {max_err}")
    print(f"RMSE (Q16.16 LSBs): {rmse:.2f}")
    
    if err_count == 0:
        print("SUCCESS: RTL matches Python Golden Vectors!")
    else:
        print("FAILURE: RTL diverged from Python Golden Vectors.")

if __name__ == "__main__":
    compare("verification/vectors/rtl_out_l0.hex", "verification/vectors/l0_001.hex")
