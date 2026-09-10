"""Generate the example torque-spec PDF.

Committed output, reproducible input - same idea as
``make_example_glb.py``. Stdlib only: a two-page PDF written by hand, so
the examples don't depend on whatever PDF library happens to be around.

Two pages rather than one so the example can ask for a page *selection*
and have that mean something.

    python tools/make_example_pdf.py
"""

from __future__ import annotations

import pathlib

OUT = (
    pathlib.Path(__file__).resolve().parent.parent
    / "examples"
    / "Bracket-Assembly"
    / "torque-spec.pdf"
)

PAGES = [
    [
        ("H", "Fastener Torque Schedule"),
        ("S", "Bracket Assembly / antenna deployment mechanism"),
        ("", ""),
        ("B", "Position      Fastener        Torque       Preload"),
        ("", "-------------------------------------------------------"),
        ("", "M4-1          M4x12 A2-70     2.8 Nm       +/- 0.2 Nm"),
        ("", "M4-2          M4x12 A2-70     2.8 Nm       +/- 0.2 Nm"),
        ("", "Base-1..4     M3x8  A2-70     1.2 Nm       +/- 0.1 Nm"),
        ("", ""),
        ("B", "Sequence"),
        ("", "1. Seat all fasteners hand-tight before torquing."),
        ("", "2. Torque the base fasteners diagonally, then the M4 pair."),
        ("", "3. Re-check the base fasteners after the M4 pair is set."),
        ("", ""),
        ("B", "Lubrication"),
        ("", "Dry. Values assume no thread lubricant. A lubricated"),
        ("", "thread reaches the same preload at roughly 70% of the"),
        ("", "torque above, so do not substitute without recalculating."),
    ],
    [
        ("H", "Inspection and Rework"),
        ("S", "Page 2 of the torque schedule"),
        ("", ""),
        ("B", "Witness marking"),
        ("", "Mark every torqued fastener with a continuous line across"),
        ("", "the head, washer and substrate. A broken line at a later"),
        ("", "inspection means the joint moved and must be re-torqued."),
        ("", ""),
        ("B", "Rework limits"),
        ("", "Two re-torques per position. A third means the insert is"),
        ("", "replaced, not the fastener."),
        ("", ""),
        ("B", "Records"),
        ("", "Log the wrench serial number and calibration date against"),
        ("", "each assembly serial. Torque values without a traceable"),
        ("", "wrench are not acceptance evidence."),
    ],
]

_SIZES = {"H": (18, "F2"), "S": (10, "F1"), "B": (12, "F2"), "": (10, "F1")}


def escape(text: str) -> str:
    """PDF string literals escape backslash and both parentheses."""
    for old, new in (("\\", r"\\"), ("(", r"\("), (")", r"\)")):
        text = text.replace(old, new)
    return text


def content_stream(lines: list[tuple[str, str]]) -> bytes:
    out = ["BT", "1 0 0 1 56 780 Tm", "16 TL"]
    for kind, text in lines:
        size, font = _SIZES[kind]
        out.append(f"/{font} {size} Tf")
        out.append(f"({escape(text)}) Tj" if text else "")
        out.append("T*")
        if kind == "H":
            out.append("T*")
    out.append("ET")
    return "\n".join(out).encode("latin-1")


def build_pdf() -> bytes:
    page_count = len(PAGES)
    # Object numbering: 1 catalog, 2 pages, 3..(2+n) pages,
    # then one content stream each, then the two fonts.
    first_page = 3
    first_stream = first_page + page_count
    regular = first_stream + page_count
    bold = regular + 1

    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            "<< /Type /Pages /Kids ["
            + " ".join(f"{first_page + i} 0 R" for i in range(page_count))
            + f"] /Count {page_count} >>"
        ).encode("latin-1"),
        regular: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        bold: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    }

    for index, lines in enumerate(PAGES):
        stream = content_stream(lines)
        objects[first_page + index] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {regular} 0 R /F2 {bold} 0 R >> >> "
            f"/Contents {first_stream + index} 0 R >>"
        ).encode("latin-1")
        objects[first_stream + index] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
            + stream
            + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode("latin-1")
        out += objects[number]
        out += b"\nendobj\n"

    start_xref = len(out)
    total = max(objects) + 1
    out += f"xref\n0 {total}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for number in range(1, total):
        out += f"{offsets[number]:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {total} /Root 1 0 R >>\n"
        f"startxref\n{start_xref}\n%%EOF\n"
    ).encode("latin-1")
    return bytes(out)


if __name__ == "__main__":
    data = build_pdf()
    OUT.write_bytes(data)
    print(f"wrote {OUT} ({len(data)} bytes)")
