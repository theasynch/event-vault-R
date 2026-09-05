import os
import sys
import numpy as np
import pywt
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eventvault.codec.dwt import decompose, reconstruct

def write_matrix(filename, mat):
    """Write 2D numpy array to a simple binary format: int32 rows, int32 cols, float64 array"""
    with open(filename, 'wb') as f:
        f.write(np.int32(mat.shape[0]).tobytes())
        f.write(np.int32(mat.shape[1]).tobytes())
        f.write(mat.astype(np.float64).tobytes())

def main():
    out_dir = os.path.join(os.path.dirname(__file__), 'vectors')
    os.makedirs(out_dir, exist_ok=True)

    # Generate a deterministic input image
    np.random.seed(42)
    image = np.random.rand(64, 64) * 255.0
    
    write_matrix(os.path.join(out_dir, 'image_001.bin'), image)

    wavelet = 'haar'
    decomp = decompose(image, wavelet=wavelet, levels=3, mode='symmetric')

    write_matrix(os.path.join(out_dir, 'l0_001.bin'), decomp.base_layer)
    write_matrix(os.path.join(out_dir, 'h1_lh.bin'), decomp.residual_layers[1][0])
    write_matrix(os.path.join(out_dir, 'h1_hl.bin'), decomp.residual_layers[1][1])
    write_matrix(os.path.join(out_dir, 'h1_hh.bin'), decomp.residual_layers[1][2])
    
    recon = reconstruct(decomp)
    write_matrix(os.path.join(out_dir, 'recon_001.bin'), recon)

    # Generate metadata
    meta = {
        'wavelet': wavelet,
        'levels': 3,
        'mode': 'symmetric',
        'original_shape': list(image.shape)
    }
    with open(os.path.join(out_dir, 'metadata_001.json'), 'w') as f:
        json.dump(meta, f, indent=2)

    print("Generated golden vectors in verification/vectors/")

if __name__ == "__main__":
    main()
