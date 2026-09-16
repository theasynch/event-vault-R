"""
Generate golden verification vectors for EventVault-R Phase C.

Produces:
  - image_001.bin/hex    : 64x64 input image (float64 / Q16.16)
  - l0_001.bin/hex       : Level-3 LL base layer (bior4.4, 3 levels)
  - h1_lh/hl/hh.bin/hex  : Level-1 detail sub-bands
  - h2_lh/hl/hh.bin/hex  : Level-2 detail sub-bands
  - h3_lh/hl/hh.bin/hex  : Level-3 detail sub-bands
  - recon_001.bin/hex     : Reconstructed image
  - metadata_001.json    : Parameters

Also generates Q16.16 hex files for SystemVerilog $readmemh.
"""

import os
import sys
import struct
import numpy as np
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from eventvault.codec.dwt import decompose, reconstruct


def write_matrix(filename, mat):
    """Write 2D numpy array: int32 rows, int32 cols, float64 data."""
    with open(filename, 'wb') as f:
        f.write(np.int32(mat.shape[0]).tobytes())
        f.write(np.int32(mat.shape[1]).tobytes())
        f.write(mat.astype(np.float64).tobytes())


def float_to_q16(val):
    """Convert a float to unsigned Q16.16 representation (32-bit)."""
    return int(val * (1 << 16)) & 0xFFFFFFFF


def write_hex(filename, mat):
    """Write a 2D numpy array as Q16.16 hex values, one per line."""
    flat = mat.flatten()
    with open(filename, 'w') as f:
        for v in flat:
            f.write(f"{float_to_q16(v):08X}\n")


def main():
    out_dir = os.path.join(os.path.dirname(__file__), 'vectors')
    os.makedirs(out_dir, exist_ok=True)

    # Deterministic 64x64 input image
    np.random.seed(42)
    image = np.random.rand(64, 64) * 255.0

    write_matrix(os.path.join(out_dir, 'image_001.bin'), image)
    write_hex(os.path.join(out_dir, 'image_001.hex'), image)

    # --- Bior4.4 decomposition (matches C++ dwt_fixed.cpp and RTL) ---
    wavelet = 'bior4.4'
    decomp = decompose(image, wavelet=wavelet, levels=3, mode='symmetric')

    # Base layer (L0 = LL3)
    write_matrix(os.path.join(out_dir, 'l0_001.bin'), decomp.base_layer)
    write_hex(os.path.join(out_dir, 'l0_001.hex'), decomp.base_layer)
    print(f"L0 shape: {decomp.base_layer.shape}")

    # Detail layers
    for lvl in sorted(decomp.residual_layers.keys()):
        lh, hl, hh = decomp.residual_layers[lvl]
        prefix = f"h{lvl}"
        write_matrix(os.path.join(out_dir, f'{prefix}_lh.bin'), lh)
        write_matrix(os.path.join(out_dir, f'{prefix}_hl.bin'), hl)
        write_matrix(os.path.join(out_dir, f'{prefix}_hh.bin'), hh)
        write_hex(os.path.join(out_dir, f'{prefix}_lh.hex'), lh)
        write_hex(os.path.join(out_dir, f'{prefix}_hl.hex'), hl)
        write_hex(os.path.join(out_dir, f'{prefix}_hh.hex'), hh)
        print(f"H{lvl} shape: {lh.shape}")

    # Reconstruction
    recon = reconstruct(decomp)
    write_matrix(os.path.join(out_dir, 'recon_001.bin'), recon)
    write_hex(os.path.join(out_dir, 'recon_001.hex'), recon)

    # PSNR check
    mse = np.mean((image - recon) ** 2)
    psnr = 10 * np.log10(255.0**2 / mse) if mse > 0 else float('inf')
    print(f"Reconstruction PSNR: {psnr:.2f} dB (perfect = inf)")

    # Metadata
    meta = {
        'wavelet': wavelet,
        'levels': 3,
        'mode': 'symmetric',
        'original_shape': list(image.shape),
        'l0_shape': list(decomp.base_layer.shape),
    }
    for lvl in sorted(decomp.residual_layers.keys()):
        meta[f'h{lvl}_shape'] = list(decomp.residual_layers[lvl][0].shape)

    with open(os.path.join(out_dir, 'metadata_001.json'), 'w') as f:
        json.dump(meta, f, indent=2)

    print(f"\nGenerated bior4.4 golden vectors in {out_dir}/")


if __name__ == "__main__":
    main()
