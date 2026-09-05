import struct
import sys
from pathlib import Path

def float_to_q16(val):
    return int(val * (1 << 16)) & 0xFFFFFFFF

def dump_file(bin_path, hex_path):
    with open(bin_path, 'rb') as f:
        # Read header: rows, cols
        header = f.read(8)
        if len(header) < 8:
            return
        rows, cols = struct.unpack('<ii', header)
        
        # Read floats
        data = f.read()
        num_floats = len(data) // 8
        floats = struct.unpack(f'<{num_floats}d', data)
        
        with open(hex_path, 'w') as out_f:
            for val in floats:
                q16 = float_to_q16(val)
                out_f.write(f"{q16:08X}\n")

if __name__ == "__main__":
    base_dir = Path(__file__).parent / "vectors"
    for bin_file in base_dir.glob("*.bin"):
        if "saved_discovery" in bin_file.name:
            continue
        hex_file = bin_file.with_suffix('.hex')
        dump_file(bin_file, hex_file)
        print(f"Dumped {bin_file.name} to {hex_file.name}")
