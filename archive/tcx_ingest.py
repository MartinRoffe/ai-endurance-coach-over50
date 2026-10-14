#!/usr/bin/env python3
"""Parse TCX files into 1 Hz power JSON streams for MMP."""
from __future__ import annotations

import argparse
import json
import re
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Optional

ARCHIVE_DIR = Path(__file__).resolve().parent
REPO_ROOT = ARCHIVE_DIR.parent
TCX_DIR = REPO_ROOT / "data" / "haute-route-2012"
STREAMS_DIR = ARCHIVE_DIR / "streams"
TCX_CACHE_DIR = ARCHIVE_DIR / "tcx"

# Day N → Garmin activity_id (from activities CSV)
HR2012_MAP = {
    1: 277575486,
    2: 277575362,
    3: 277575279,
    4: 277575228,
    5: 277575139,
}


def _parse_time(s: str) -> Optional[float]:
    try:
        s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


def parse_tcx_power(path: Path) -> list[tuple[float, float]]:
    """Return (unix_ts, watts) pairs from Trackpoints with Watts."""
    pairs: list[tuple[float, float]] = []
    tree = ET.parse(path)
    root = tree.getroot()
    for tp in root.iter():
        tag = tp.tag.split("}")[-1] if "}" in tp.tag else tp.tag
        if tag != "Trackpoint":
            continue
        t_el = None
        watts = None
        for child in tp:
            ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if ctag == "Time" and child.text:
                t_el = _parse_time(child.text)
            if ctag == "Extensions":
                for ext in child.iter():
                    et = ext.tag.split("}")[-1] if "}" in ext.tag else ext.tag
                    if et == "Watts" and ext.text:
                        try:
                            watts = float(ext.text)
                        except ValueError:
                            pass
        if t_el is not None and watts is not None:
            pairs.append((t_el, watts))
    pairs.sort(key=lambda x: x[0])
    return pairs


def parse_tcx_power_bytes(data: bytes) -> list[tuple[float, float]]:
    """Parse TCX XML bytes via a temp file (reuses path parser)."""
    with tempfile.NamedTemporaryFile(suffix=".tcx", delete=False) as tmp:
        tmp.write(data)
        path = Path(tmp.name)
    try:
        return parse_tcx_power(path)
    finally:
        path.unlink(missing_ok=True)


def to_1hz(pairs: list[tuple[float, float]]) -> list[Optional[float]]:
    if not pairs:
        return []
    t0, t_end = pairs[0][0], pairs[-1][0]
    n = int(round(t_end - t0)) + 1
    if n <= 0 or n > 3600 * 20:
        return [p for _, p in pairs]
    out: list[Optional[float]] = [None] * n
    for t, p in pairs:
        idx = int(round(t - t0))
        if 0 <= idx < n:
            out[idx] = p
    last_p = None
    last_i = None
    for i in range(n):
        if out[i] is not None:
            last_p = out[i]
            last_i = i
        elif last_p is not None and last_i is not None and (i - last_i) <= 3:
            out[i] = last_p
    return out


def write_stream_json(
    activity_id: int,
    series: list[Optional[float]],
    *,
    pairs_n: int,
    source: str = "tcx",
    path: Optional[str] = None,
    extra: Optional[dict] = None,
) -> Path:
    STREAMS_DIR.mkdir(parents=True, exist_ok=True)
    powered = sum(1 for p in series if p is not None)
    out = STREAMS_DIR / f"{activity_id}.json"
    payload = {
        "activity_id": activity_id,
        "source": source,
        "path": path,
        "n_trackpoints_with_watts": pairs_n,
        "n_1hz": len(series),
        "n_powered": powered,
        "power_1hz": series,
        "device_ftp_w": None,
        "device_ftp_source": None,
    }
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload), encoding="utf-8")
    return out


def ingest_tcx_bytes(activity_id: int, data: bytes, *, source: str = "garmin_tcx") -> Optional[Path]:
    """Cache TCX bytes and write stream JSON. Returns stream path or None if no power."""
    TCX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tcx_path = TCX_CACHE_DIR / f"{activity_id}.tcx"
    tcx_path.write_bytes(data)
    pairs = parse_tcx_power(tcx_path)
    series = to_1hz(pairs)
    powered = sum(1 for p in series if p is not None)
    if powered < 5:
        return None
    return write_stream_json(
        activity_id,
        series,
        pairs_n=len(pairs),
        source=source,
        path=str(tcx_path),
    )


def find_tcx_for_day(day: int) -> Optional[Path]:
    for p in TCX_DIR.glob("*.tcx"):
        if re.search(rf"Day\s*{day}\b", p.name, re.I):
            return p
    return None


def ingest_hr2012() -> list[Path]:
    STREAMS_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for day, aid in HR2012_MAP.items():
        tcx = find_tcx_for_day(day)
        if tcx is None:
            print(f"  Day {day}: TCX not found", flush=True)
            continue
        print(f"  Day {day} → {aid}: parsing {tcx.name}…", flush=True)
        pairs = parse_tcx_power(tcx)
        series = to_1hz(pairs)
        powered = sum(1 for p in series if p is not None)
        out = write_stream_json(
            aid,
            series,
            pairs_n=len(pairs),
            source="tcx",
            path=str(tcx),
            extra={"day": day},
        )
        print(f"    wrote {out.name} ({powered} powered samples / {len(series)} s)", flush=True)
        written.append(out)
    return written


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    if not TCX_DIR.is_dir():
        raise SystemExit(f"Missing {TCX_DIR}")
    ingest_hr2012()


if __name__ == "__main__":
    main()
