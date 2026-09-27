from pathlib import Path, PureWindowsPath

from harness.graphics import ffmpeg_filter_path
from harness.verify import _decode_raw, check_against_timemap


def encode_row(n: int | None, cells: int = 17) -> bytes:
    if n is None:
        return bytes([0] * cells)
    return bytes([200] + [200 if (n >> b) & 1 else 10 for b in range(16)])


def test_decode_raw_roundtrip():
    frames = [0, 1, 1200, 65535, None, 42]
    raw = b"".join(encode_row(n) for n in frames)
    assert _decode_raw(raw, 17) == frames


def test_timemap_check_detects_exact_and_offset():
    tm = [{"order": 0, "kind": "segment", "segment_id": "s", "source_start": 1.0, "source_end": 2.0,
           "out_start": 0.0, "out_end": 1.0}]
    exact = list(range(30, 60))
    r = check_against_timemap(exact, tm, 30)
    assert r["segments_exact"] == 1 and r["intra_segment_discontinuities"] == 0
    late = list(range(31, 61))
    r = check_against_timemap(late, tm, 30)
    assert r["max_abs_start_error_frames"] == 1
    dup = exact[:10] + [exact[9]] + exact[11:]
    assert check_against_timemap(dup, tm, 30)["intra_segment_discontinuities"] == 2


def test_filter_path_escapes_windows_drive_colon():
    p = PureWindowsPath(r"D:\runs\it's\t.txt")
    assert ffmpeg_filter_path(Path(str(p))) == "'D\\:/runs/it\\'s/t.txt'"
