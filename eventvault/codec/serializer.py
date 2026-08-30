"""
Wavelet coefficient serializer for progressive streaming.

Serializes and deserializes wavelet decomposition layers into
byte streams suitable for storage and transmission. Supports
progressive prefix decoding — any prefix of the stream produces
a valid partial reconstruction.
"""

from __future__ import annotations

import io
import struct
from typing import Dict, List, Optional, Tuple

import numpy as np
from numpy.typing import NDArray

from eventvault.codec.dwt import WaveletDecomposition


# Header format: magic(4) + levels(1) + wavelet_len(1) + wavelet(N) +
#                rows(4) + cols(4) + dtype_code(1)
MAGIC = b"EVR1"
DTYPE_MAP = {
    0: np.float32,
    1: np.float64,
    2: np.int32,
}
DTYPE_REVERSE = {v: k for k, v in DTYPE_MAP.items()}


def serialize_decomposition(
    decomp: WaveletDecomposition,
    dtype: type = np.float32,
) -> bytes:
    """
    Serialize a wavelet decomposition to a progressive byte stream.

    The stream is ordered so that any prefix containing complete
    layers can be decoded to produce a valid reconstruction:
        [header][L0][H1][H2][H3]

    Each layer block contains:
        layer_id(1) + num_arrays(1) + [shape(8) + data(N)] per array

    Parameters
    ----------
    decomp : WaveletDecomposition
        Wavelet decomposition to serialize.
    dtype : numpy dtype
        Storage dtype (float32 saves space, float64 for precision).

    Returns
    -------
    bytes
        Progressive byte stream.
    """
    buf = io.BytesIO()

    # Header
    buf.write(MAGIC)
    buf.write(struct.pack("B", decomp.levels))
    wavelet_bytes = decomp.wavelet.encode("utf-8")
    buf.write(struct.pack("B", len(wavelet_bytes)))
    buf.write(wavelet_bytes)
    buf.write(struct.pack("II", *decomp.original_shape))
    buf.write(struct.pack("B", DTYPE_REVERSE.get(dtype, 1)))

    # Base layer (L0)
    _write_layer_block(buf, 0, [decomp.base_layer], dtype)

    # Residual layers H1, H2, H3
    for k in range(1, decomp.levels + 1):
        lh, hl, hh = decomp.residual_layers[k]
        _write_layer_block(buf, k, [lh, hl, hh], dtype)

    return buf.getvalue()


def _write_layer_block(
    buf: io.BytesIO,
    layer_id: int,
    arrays: List[NDArray],
    dtype: type,
) -> None:
    """Write a single layer block to the buffer."""
    buf.write(struct.pack("B", layer_id))
    buf.write(struct.pack("B", len(arrays)))
    for arr in arrays:
        arr_typed = arr.astype(dtype)
        buf.write(struct.pack("II", *arr_typed.shape))
        buf.write(arr_typed.tobytes())


def get_layer_byte_ranges(data: bytes) -> Dict[int, Tuple[int, int]]:
    """
    Parse the stream header and return byte offsets for each layer.

    Returns
    -------
    Dict mapping layer_id to (start_offset, end_offset).
    """
    buf = io.BytesIO(data)
    ranges = {}

    # Parse header
    magic = buf.read(4)
    if magic != MAGIC:
        raise ValueError(f"Invalid magic: {magic}")

    levels = struct.unpack("B", buf.read(1))[0]
    wav_len = struct.unpack("B", buf.read(1))[0]
    buf.read(wav_len)  # wavelet name
    buf.read(8)  # original shape
    dtype_code = struct.unpack("B", buf.read(1))[0]
    dtype = DTYPE_MAP[dtype_code]
    itemsize = np.dtype(dtype).itemsize

    # Parse layer blocks
    for _ in range(levels + 1):
        start = buf.tell()
        layer_id = struct.unpack("B", buf.read(1))[0]
        num_arrays = struct.unpack("B", buf.read(1))[0]
        for _ in range(num_arrays):
            rows, cols = struct.unpack("II", buf.read(8))
            buf.read(rows * cols * itemsize)
        end = buf.tell()
        ranges[layer_id] = (start, end)

    return ranges


def deserialize_decomposition(
    data: bytes,
    max_depth: Optional[int] = None,
) -> WaveletDecomposition:
    """
    Deserialize a progressive byte stream back to a WaveletDecomposition.

    Supports prefix decoding: if max_depth is specified, only layers
    up to that depth are read. Missing layers are zero-filled.

    Parameters
    ----------
    data : bytes
        Progressive byte stream.
    max_depth : int, optional
        Maximum layer depth to decode. None = decode all.

    Returns
    -------
    WaveletDecomposition
    """
    buf = io.BytesIO(data)

    # Parse header
    magic = buf.read(4)
    if magic != MAGIC:
        raise ValueError(f"Invalid stream magic: {magic}")

    levels = struct.unpack("B", buf.read(1))[0]
    wav_len = struct.unpack("B", buf.read(1))[0]
    wavelet = buf.read(wav_len).decode("utf-8")
    orig_rows, orig_cols = struct.unpack("II", buf.read(8))
    dtype_code = struct.unpack("B", buf.read(1))[0]
    dtype = DTYPE_MAP[dtype_code]

    if max_depth is None:
        max_depth = levels

    # Read base layer
    base_layer = _read_layer_block(buf, dtype)
    assert base_layer[0] == 0, "First layer must be base (id=0)"
    base_arrays = base_layer[1]

    # Read residual layers
    residual_layers = {}
    for k in range(1, levels + 1):
        if k <= max_depth and buf.tell() < len(data):
            layer_data = _read_layer_block(buf, dtype)
            layer_id = layer_data[0]
            arrays = layer_data[1]
            residual_layers[layer_id] = (arrays[0], arrays[1], arrays[2])
        else:
            # Zero-fill missing layers (need shape from the previous data)
            # Use a small placeholder — will be properly sized during recon
            residual_layers[k] = None  # Will handle in reconstruct

    return WaveletDecomposition(
        base_layer=base_arrays[0],
        residual_layers=residual_layers,
        wavelet=wavelet,
        mode="symmetric",
        levels=levels,
        original_shape=(orig_rows, orig_cols),
    )


def _read_layer_block(
    buf: io.BytesIO,
    dtype: type,
) -> Tuple[int, List[NDArray]]:
    """Read a single layer block from the buffer."""
    layer_id = struct.unpack("B", buf.read(1))[0]
    num_arrays = struct.unpack("B", buf.read(1))[0]
    arrays = []
    for _ in range(num_arrays):
        rows, cols = struct.unpack("II", buf.read(8))
        data = buf.read(rows * cols * np.dtype(dtype).itemsize)
        arr = np.frombuffer(data, dtype=dtype).reshape(rows, cols).copy()
        arrays.append(arr)
    return (layer_id, arrays)
