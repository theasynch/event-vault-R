import sys
from pathlib import Path
import json

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from eventvault.acquisition.synthetic import generate_sequence
from eventvault.codec.dwt import decompose
from eventvault.config import load_config
import numpy as np

def main():
    config = load_config()
    config.acquisition.frame_shape = (128, 128)
    sequence = generate_sequence(
        num_frames=10,
        cadence_seconds=30.0,
        frame_shape=config.acquisition.frame_shape,
        num_static_sources=20,
        transient_position=(64, 64),
        transient_start_frame=5,
        transient_peak_flux=5000.0,
        transient_rise_time_frames=5,
        seed=42,
    )
    
    min_val = float('inf')
    max_val = float('-inf')
    
    for frame, _ in sequence:
        decomp = decompose(frame.astype(np.float64), levels=3)
        
        # Check base layer
        min_val = min(min_val, np.min(decomp.base_layer))
        max_val = max(max_val, np.max(decomp.base_layer))
        
        # Check residuals
        for l, layers in decomp.residual_layers.items():
            for name, data in zip(['LH', 'HL', 'HH'], layers):
                min_val = min(min_val, np.min(data))
                max_val = max(max_val, np.max(data))
                
    print(f"Minimum coefficient: {min_val}")
    print(f"Maximum coefficient: {max_val}")
    
    # Check if Q16.16 is sufficient
    # Q16.16 max value is approx 32767.999
    print("If max absolute is < 32767, Q16.16 is sufficient.")

if __name__ == "__main__":
    main()
