"""Tessellate STEP files into glTF, so an artifact can show them.

**This is not part of the package, and deliberately so.** A browser
cannot draw STEP: it is boundary representation - surfaces defined by
equations - and something has to turn those into triangles first. Doing
that inside Model Explorer would mean a few hundred megabytes of
OpenCascade in every deployment, and seconds to minutes of CPU per
assembly, on every page view, to produce a picture that does not change.

So it happens once, here, at build time - in the discipline repo that
owns the CAD, next to that repo's other tooling. The output is committed
(or published as a CI artifact) and the manifest points at the ``.glb``.
The renderer stays a renderer.

    pip install cascadio          # OpenCascade, wrapped; pulls numpy
    python tools/step_to_glb.py examples/steps/*.step

Two things this handles that you would otherwise have to fix by hand:

**Units.** glTF's convention is metres and CAD almost always exports
millimetres. cascadio reads the unit declared in the STEP header and
converts, so an M3 nut comes out 0.006 wide rather than 6.0. Worth
checking against ``--report`` on a part whose size you know.

**Axis.** STEP is normally Z-up, glTF is Y-up. Nothing here rotates the
geometry, because doing so silently would make the ``.glb`` disagree with
the CAD it came from. Say ``up: z`` in the manifest instead - the viewer
stands it upright at display time and the file stays faithful.

**Tolerance** is the size/fidelity dial. ``--tol-linear`` is the largest
distance a triangle may sit from the true surface, in millimetres: 0.05
for a small machined part, 0.2 for an assembly nobody will measure on
screen. It is the difference between a 30 MB glTF and a 3 MB one.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import struct
import sys
import time


def convert(
    source: pathlib.Path,
    destination: pathlib.Path,
    tol_linear: float,
    tol_angular: float,
) -> None:
    try:
        import cascadio
    except ImportError:
        raise SystemExit(
            "step_to_glb: cascadio is not installed - 'pip install cascadio'.\n"
            "  It carries OpenCascade, so it is a large install, and it is "
            "needed only here at build time - never by the renderer."
        ) from None

    destination.parent.mkdir(parents=True, exist_ok=True)
    cascadio.step_to_glb(
        str(source),
        str(destination),
        tol_linear=tol_linear,
        tol_angular=tol_angular,
    )


def describe(path: pathlib.Path) -> dict:
    """Read back the glTF header: extents, part count, triangle count.

    Reading the output rather than trusting it - a conversion that
    silently produced an empty scene, or a model a thousand times too
    big, looks like success until someone opens it.
    """
    data = path.read_bytes()
    length, = struct.unpack("<I", data[12:16])
    gltf = json.loads(data[20 : 20 + length])

    vectors = [
        (accessor["min"], accessor["max"])
        for accessor in gltf.get("accessors", ())
        if accessor.get("type") == "VEC3" and "min" in accessor
    ]
    if vectors:
        low = [min(axis) for axis in zip(*(v[0] for v in vectors))]
        high = [max(axis) for axis in zip(*(v[1] for v in vectors))]
        size = [round((h - l) * 1000, 1) for l, h in zip(low, high)]
    else:
        size = []

    return {
        "bytes": len(data),
        "parts": len(gltf.get("nodes", ())),
        "triangles": sum(
            accessor["count"]
            for accessor in gltf.get("accessors", ())
            if accessor.get("type") == "SCALAR"
        )
        // 3,
        "size_mm": size,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="step_to_glb",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("sources", nargs="+", type=pathlib.Path)
    parser.add_argument(
        "-o",
        "--out",
        type=pathlib.Path,
        help="output directory (default: a .build/ beside each source)",
    )
    parser.add_argument(
        "--tol-linear",
        type=float,
        default=0.1,
        help="largest deviation from the true surface, in mm (default: 0.1)",
    )
    parser.add_argument(
        "--tol-angular",
        type=float,
        default=0.4,
        help="largest angular deviation, in radians (default: 0.4)",
    )
    args = parser.parse_args(argv)

    for source in args.sources:
        if not source.is_file():
            print(f"  skipped {source} (not a file)", file=sys.stderr)
            continue

        out_dir = args.out or source.parent / ".build"
        destination = out_dir / (source.stem + ".glb")

        started = time.time()
        convert(source, destination, args.tol_linear, args.tol_angular)
        elapsed = time.time() - started

        facts = describe(destination)
        print(
            f"  {source.name}\n"
            f"    {source.stat().st_size / 1e6:.1f} MB STEP"
            f" -> {facts['bytes'] / 1e6:.2f} MB glTF"
            f"  ({elapsed:.1f}s, {facts['parts']} parts,"
            f" {facts['triangles']:,} triangles)\n"
            f"    extents {facts['size_mm']} mm"
            f"  -> {destination}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
