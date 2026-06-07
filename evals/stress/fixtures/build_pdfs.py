"""Generate deterministic PDF attachment fixtures for stress testing."""

from __future__ import annotations

from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent
EMBEDDED_FACT = "attachment fact: redis caching required"
TARGETS_KB = (5, 20, 50, 100)
_TOLERANCE = 0.15


def build_all(output_dir: Path | None = None) -> dict[int, Path]:
    """Write attach_{size}kb.pdf files and return paths."""

    destination = output_dir or FIXTURE_DIR
    destination.mkdir(parents=True, exist_ok=True)
    written: dict[int, Path] = {}
    for target_kb in TARGETS_KB:
        path = destination / f"attach_{target_kb}kb.pdf"
        _write_pdf(path, target_kb=target_kb)
        written[target_kb] = path
    return written


def _write_pdf(path: Path, *, target_kb: int) -> None:
    target_bytes = target_kb * 1024
    min_bytes = int(target_bytes * (1 - _TOLERANCE))
    max_bytes = int(target_bytes * (1 + _TOLERANCE))

    filler = (
        f"{EMBEDDED_FACT}\n"
        "Deterministic stress attachment filler. "
        "Repeat this paragraph to reach the target PDF size without randomness.\n"
    )
    body = bytearray()
    while len(body) < min_bytes - 256:
        body.extend(filler.encode("ascii"))

    header = (
        b"%PDF-1.4\n"
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n"
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
        b"3 0 obj<< /Type /Page /Parent 2 0 R "
        b"/MediaBox [0 0 612 792] /Contents 4 0 R /Resources<< /Font<< /F1 5 0 R >> >> >>endobj\n"
        b"4 0 obj<< /Length "
    )
    stream = b"BT /F1 10 Tf 50 740 Td (" + body + b") Tj ET"
    mid = (
        str(len(stream)).encode("ascii")
        + b" >>stream\n"
        + stream
        + b"\nendstream endobj\n"
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n"
        b"trailer<< /Size 6 /Root 1 0 R >>\nstartxref\n0\n%%EOF\n"
    )
    raw = header + mid
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
    path.write_bytes(raw)


if __name__ == "__main__":
    paths = build_all()
    for size_kb, file_path in paths.items():
        actual_kb = file_path.stat().st_size / 1024
        print(f"wrote {file_path.name}: {actual_kb:.1f} KB")
