import sys
from pathlib import Path
import json

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from eventvault.acquisition.synthetic import generate_sequence
from eventvault.config import load_config
import numpy as np
import struct

def main():
    config = load_config()
    config.acquisition.frame_shape = (128, 128)
    config.synthetic.num_static_sources = 15
    config.escrow.capacity = 70
    config.saved_discovery.transient_position = (64, 64)
    cfg = config.saved_discovery
    
    sequence = generate_sequence(
        num_frames=cfg.num_frames,
        cadence_seconds=cfg.cadence_seconds,
        frame_shape=config.acquisition.frame_shape,
        num_static_sources=config.synthetic.num_static_sources,
        transient_position=tuple(cfg.transient_position),
        transient_start_frame=cfg.transient_start_frame,
        transient_peak_flux=cfg.transient_peak_flux,
        transient_rise_time_frames=cfg.transient_rise_time_frames,
        seed=42,
    )
    
    out_dir = Path(__file__).parent.parent / "verification" / "vectors"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with open(out_dir / "saved_discovery_frames.bin", "wb") as f:
        # Write header: num_frames, rows, cols
        f.write(struct.pack("<iii", len(sequence), 128, 128))
        for frame, metadata in sequence:
            # write frame_id and timestamp
            f.write(struct.pack("<id", metadata.frame_id, metadata.timestamp))
            # write frame data
            f.write(frame.astype(np.float64).tobytes())
            
    print(f"Exported {len(sequence)} frames to {out_dir / 'saved_discovery_frames.bin'}")

if __name__ == "__main__":
    main()
