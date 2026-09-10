"""Generate the example bracket .glb.

Committed output, reproducible input - the example asset is a real glTF
file, not a placeholder, and this says exactly what it is. Stdlib only.

The geometry is deliberately **Z-up and in metres**, which is what a CAD
export looks like after someone has done the unit conversion but not the
axis one. That makes the example exercise the ``up: z`` option rather
than just claiming it exists.

    python tools/make_example_glb.py
"""

from __future__ import annotations

import json
import pathlib
import struct

OUT = (
    pathlib.Path(__file__).resolve().parent.parent
    / "examples"
    / "Bracket-Assembly"
    / "bracket-v2.glb"
)

MM = 0.001  # glTF's convention is metres; CAD hands you millimetres

#: Two slabs making an L: a base plate and an upright, Z vertical.
#: (origin_x, origin_y, origin_z, size_x, size_y, size_z), in mm.
PARTS = [
    (0, 0, 0, 100, 60, 8),
    (0, 0, 8, 8, 60, 62),
]

_FACES = [
    # (normal, four corners as (dx, dy, dz) unit offsets), counter-clockwise
    ((0, 0, -1), [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)]),
    ((0, 0, 1), [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]),
    ((0, -1, 0), [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]),
    ((0, 1, 0), [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)]),
    ((-1, 0, 0), [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)]),
    ((1, 0, 0), [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)]),
]


def build_geometry():
    positions: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    indices: list[int] = []

    for ox, oy, oz, sx, sy, sz in PARTS:
        for normal, corners in _FACES:
            first = len(positions)
            for dx, dy, dz in corners:
                positions.append(
                    (
                        (ox + dx * sx) * MM,
                        (oy + dy * sy) * MM,
                        (oz + dz * sz) * MM,
                    )
                )
                normals.append(normal)
            indices += [
                first, first + 1, first + 2,
                first, first + 2, first + 3,
            ]

    return positions, normals, indices


def pad(data: bytes, to: int = 4, filler: bytes = b"\x00") -> bytes:
    short = -len(data) % to
    return data + filler * short


def build_glb() -> bytes:
    positions, normals, indices = build_geometry()

    position_bytes = b"".join(struct.pack("<3f", *p) for p in positions)
    normal_bytes = b"".join(struct.pack("<3f", *n) for n in normals)
    index_bytes = pad(b"".join(struct.pack("<H", i) for i in indices))
    binary = position_bytes + normal_bytes + index_bytes

    axes = list(zip(*positions))
    gltf = {
        "asset": {
            "version": "2.0",
            "generator": "mbse-artifact-viewer tools/make_example_glb.py",
        },
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "Bracket"}],
        "meshes": [
            {
                "name": "Bracket",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1},
                        "indices": 2,
                        "material": 0,
                    }
                ],
            }
        ],
        "materials": [
            {
                "name": "Anodised aluminium",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [0.62, 0.64, 0.67, 1.0],
                    "metallicFactor": 0.9,
                    "roughnessFactor": 0.35,
                },
            }
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,  # float
                "count": len(positions),
                "type": "VEC3",
                "min": [min(axis) for axis in axes],
                "max": [max(axis) for axis in axes],
            },
            {
                "bufferView": 1,
                "componentType": 5126,
                "count": len(normals),
                "type": "VEC3",
            },
            {
                "bufferView": 2,
                "componentType": 5123,  # unsigned short
                "count": len(indices),
                "type": "SCALAR",
            },
        ],
        "bufferViews": [
            {
                "buffer": 0,
                "byteOffset": 0,
                "byteLength": len(position_bytes),
                "target": 34962,  # ARRAY_BUFFER
            },
            {
                "buffer": 0,
                "byteOffset": len(position_bytes),
                "byteLength": len(normal_bytes),
                "target": 34962,
            },
            {
                "buffer": 0,
                "byteOffset": len(position_bytes) + len(normal_bytes),
                "byteLength": len(index_bytes),
                "target": 34963,  # ELEMENT_ARRAY_BUFFER
            },
        ],
        "buffers": [{"byteLength": len(binary)}],
    }

    json_chunk = pad(
        json.dumps(gltf, separators=(",", ":")).encode("utf-8"), filler=b" "
    )
    binary_chunk = pad(binary)

    body = (
        struct.pack("<I", len(json_chunk))
        + b"JSON"
        + json_chunk
        + struct.pack("<I", len(binary_chunk))
        + b"BIN\x00"
        + binary_chunk
    )
    header = struct.pack("<4sII", b"glTF", 2, 12 + len(body))
    return header + body


if __name__ == "__main__":
    data = build_glb()
    OUT.write_bytes(data)
    print(f"wrote {OUT} ({len(data)} bytes)")
