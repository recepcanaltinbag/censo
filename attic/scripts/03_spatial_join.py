#!/usr/bin/env python3
"""
Join the 75 monitoring stations to the Ergene river network, and build the
directed topology the whole analysis depends on.

This is the pipeline's highest-risk step. If stations do not snap cleanly onto
segments, no reach-level inference is possible. The script therefore reports
snap quality in detail rather than silently accepting a nearest match.

CRS note
--------
Station coordinates are WGS84 geographic (parsed from DMS in script 01).
The river shapefiles are ETRS89-LAEA (EPSG:3035), in metres:
    PROJCS ETRS89_ETRS_LAEA, GRS80, lat_0=52, lon_0=10,
    false_easting=4321000, false_northing=3210000
Stations are therefore transformed WGS84 -> EPSG:3035 before snapping, so all
distances are true metres.

Inputs  (read-only):  Data/ShapeFiles/Erg_river/Erg_river_Hydro.shp
                      derived/processed/stations.csv   (from script 01)
Outputs:              derived/processed/segments.csv
                      derived/processed/network_edges.csv
                      derived/processed/stations_snapped.csv
                      eval/spatial_join.md

Usage:  python scripts/03_spatial_join.py [--max-snap-m 500]
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict, deque
from pathlib import Path

try:
    import shapefile  # pyshp
except ImportError:
    sys.exit("pyshp is required:  pip install pyshp")

try:
    from pyproj import Transformer
except ImportError:
    sys.exit("pyproj is required:  pip install pyproj")

ROOT = Path(__file__).resolve().parent.parent
RIVER_SHP = ROOT / "Data" / "ShapeFiles" / "Erg_river" / "Erg_river_Hydro.shp"
MAIN_SHP = ROOT / "Data" / "ShapeFiles" / "Erg_river" / "Erg_mainriver_Hydro.shp"
PROC = ROOT / "derived" / "processed"
EVAL = ROOT / "eval"

EPSG_RIVER = 3035  # ETRS89-LAEA, metres
EPSG_WGS84 = 4326


# ---------------------------------------------------------------- geometry --

def point_segment_distance(px, py, ax, ay, bx, by):
    """Distance from P to segment AB, plus the projection parameter t in [0,1]."""
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay), 0.0
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy), t


def polyline_distance(px, py, points):
    """Minimum distance from P to a polyline, and the along-line position (m)."""
    best = (float("inf"), 0.0)
    travelled = 0.0
    for i in range(len(points) - 1):
        ax, ay = points[i]
        bx, by = points[i + 1]
        seg_len = math.hypot(bx - ax, by - ay)
        d, t = point_segment_distance(px, py, ax, ay, bx, by)
        if d < best[0]:
            best = (d, travelled + t * seg_len)
        travelled += seg_len
    return best


def polyline_length(points):
    return sum(math.hypot(points[i + 1][0] - points[i][0],
                          points[i + 1][1] - points[i][1])
               for i in range(len(points) - 1))


# ------------------------------------------------------------------- input --

def read_network():
    """Read segments with their topology attributes and geometry."""
    sf = shapefile.Reader(str(RIVER_SHP))
    names = [f[0] for f in sf.fields[1:]]
    idx = {n: i for i, n in enumerate(names)}
    segments = []
    for shp, rec in zip(sf.shapes(), sf.records()):
        pts = [(float(x), float(y)) for x, y in shp.points]
        if len(pts) < 2:
            continue
        segments.append({
            "seg_id": str(rec[idx["SegID"]]),
            "arc_id": str(rec[idx["ARCID"]]),
            "from_node": str(rec[idx["FROM_NODE"]]),
            "to_node": str(rec[idx["TO_NODE"]]),
            "wtr_id": str(rec[idx["WtrID"]]),
            "strahler": int(rec[idx["StrahlerOr"]]),
            "length_km": float(rec[idx["Length_km"]]),
            "area_km2": float(rec[idx["Area_km2"]]),
            "catch_id": str(rec[idx["CatchID"]]),
            "carea_km2": float(rec[idx["CArea_km2"]]),
            "points": pts,
            "geom_length_m": polyline_length(pts),
        })
    sf.close()
    return segments


def read_main_segments():
    """SegIDs belonging to the main stem."""
    if not MAIN_SHP.exists():
        return set()
    sf = shapefile.Reader(str(MAIN_SHP))
    names = [f[0] for f in sf.fields[1:]]
    i = names.index("SegID")
    out = {str(r[i]) for r in sf.records()}
    sf.close()
    return out


def read_stations():
    """One row per distinct station; coordinates taken from the campaign that
    has a valid pair. Campaign-to-campaign coordinate disagreement is reported."""
    path = PROC / "stations.csv"
    if not path.exists():
        sys.exit("run scripts/01_extract_campaigns.py first")
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    by_station = defaultdict(list)
    for r in rows:
        by_station[r["station"]].append(r)

    stations, disagreements = {}, []
    for sid, recs in by_station.items():
        good = [r for r in recs
                if r["coord_valid"] == "True" and r["lat"] and r["lon"]]
        if not good:
            continue
        coords = {(round(float(r["lat"]), 5), round(float(r["lon"]), 5))
                  for r in good}
        if len(coords) > 1:
            disagreements.append((sid, sorted(coords)))
        r = good[0]
        stations[sid] = {"station": sid,
                         "lat": float(r["lat"]), "lon": float(r["lon"]),
                         "altitude_m": r["altitude_m"],
                         "n_campaigns": len(recs),
                         "n_valid_coord": len(good)}
    invalid = sorted(set(by_station) - set(stations), key=lambda s: int(s))
    return stations, disagreements, invalid


# ------------------------------------------------------------------ graph --

def build_graph(segments):
    """Directed graph FROM_NODE -> TO_NODE (flow direction)."""
    out_edges = defaultdict(list)
    in_edges = defaultdict(list)
    for s in segments:
        out_edges[s["from_node"]].append(s)
        in_edges[s["to_node"]].append(s)
    return out_edges, in_edges


def find_outlets(segments, out_edges):
    """Nodes that receive flow but never pass it on."""
    to_nodes = {s["to_node"] for s in segments}
    return sorted(n for n in to_nodes if not out_edges.get(n))


def upstream_segments(seg, in_edges, by_id):
    """All segments strictly upstream of `seg`, via reverse BFS."""
    seen, queue = set(), deque([seg["from_node"]])
    while queue:
        node = queue.popleft()
        for up in in_edges.get(node, []):
            if up["seg_id"] in seen:
                continue
            seen.add(up["seg_id"])
            queue.append(up["from_node"])
    return seen


def detect_cycles(segments, out_edges):
    """Kahn's algorithm; leftover nodes indicate cycles (bad topology)."""
    indeg = defaultdict(int)
    nodes = set()
    for s in segments:
        nodes.add(s["from_node"])
        nodes.add(s["to_node"])
        indeg[s["to_node"]] += 1
    queue = deque(n for n in nodes if indeg[n] == 0)
    visited = 0
    while queue:
        n = queue.popleft()
        visited += 1
        for s in out_edges.get(n, []):
            indeg[s["to_node"]] -= 1
            if indeg[s["to_node"]] == 0:
                queue.append(s["to_node"])
    return len(nodes) - visited


# ------------------------------------------------------------------- main --

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-snap-m", type=float, default=500.0,
                    help="stations further than this are flagged unreliable")
    args = ap.parse_args()

    EVAL.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)

    segments = read_network()
    main_ids = read_main_segments()
    stations, disagreements, invalid = read_stations()

    by_id = {s["seg_id"]: s for s in segments}
    out_edges, in_edges = build_graph(segments)
    outlets = find_outlets(segments, out_edges)
    n_cyclic = detect_cycles(segments, out_edges)

    # ---- transform stations WGS84 -> EPSG:3035 ----
    tf = Transformer.from_crs(EPSG_WGS84, EPSG_RIVER, always_xy=True)
    snapped = []
    for sid in sorted(stations, key=lambda s: int(s)):
        st = stations[sid]
        x, y = tf.transform(st["lon"], st["lat"])
        best, best_d, best_pos = None, float("inf"), 0.0
        for seg in segments:
            d, pos = polyline_distance(x, y, seg["points"])
            if d < best_d:
                best, best_d, best_pos = seg, d, pos
        snapped.append({
            "station": sid, "lat": f"{st['lat']:.6f}", "lon": f"{st['lon']:.6f}",
            "x_3035": f"{x:.1f}", "y_3035": f"{y:.1f}",
            "seg_id": best["seg_id"], "arc_id": best["arc_id"],
            "from_node": best["from_node"], "to_node": best["to_node"],
            "strahler": best["strahler"], "catch_id": best["catch_id"],
            "carea_km2": f"{best['carea_km2']:.4f}",
            "on_main_stem": str(best["seg_id"] in main_ids),
            "snap_dist_m": f"{best_d:.1f}",
            "pos_along_seg_m": f"{best_pos:.1f}",
            "seg_length_m": f"{best['geom_length_m']:.1f}",
            "snap_ok": str(best_d <= args.max_snap_m),
        })

    # ---- outputs ----
    with (PROC / "segments.csv").open("w", newline="", encoding="utf-8") as fh:
        fields = ["seg_id", "arc_id", "from_node", "to_node", "wtr_id", "strahler",
                  "length_km", "geom_length_m", "area_km2", "catch_id", "carea_km2",
                  "on_main_stem"]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for s in sorted(segments, key=lambda s: s["seg_id"]):
            w.writerow({k: (f"{s['geom_length_m']:.1f}" if k == "geom_length_m"
                            else str(s["seg_id"] in main_ids) if k == "on_main_stem"
                            else s[k]) for k in fields})

    with (PROC / "network_edges.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["seg_id", "from_node", "to_node", "strahler"])
        for s in sorted(segments, key=lambda s: s["seg_id"]):
            w.writerow([s["seg_id"], s["from_node"], s["to_node"], s["strahler"]])

    with (PROC / "stations_snapped.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(snapped[0].keys()))
        w.writeheader()
        w.writerows(snapped)

    # ---- station-to-station upstream relation (the reach skeleton) ----
    station_by_seg = defaultdict(list)
    for s in snapped:
        station_by_seg[s["seg_id"]].append(s["station"])

    pairs = 0
    for s in snapped:
        seg = by_id[s["seg_id"]]
        ups = upstream_segments(seg, in_edges, by_id)
        pairs += sum(len(station_by_seg[u]) for u in ups if u in station_by_seg)

    # ---- report ----
    dists = sorted(float(s["snap_dist_m"]) for s in snapped)
    n = len(dists)
    ok = sum(1 for s in snapped if s["snap_ok"] == "True")
    multi = {k: v for k, v in station_by_seg.items() if len(v) > 1}

    def q(p):
        return dists[min(n - 1, int(p * n))]

    L = []
    A = L.append
    A("# Spatial join: stations to river network\n")
    A("Generated by `scripts/03_spatial_join.py`.\n")

    A("## Coordinate reference systems\n")
    A("| Layer | CRS | Units |")
    A("|---|---|---|")
    A("| River network (`Erg_river_Hydro.shp`) | ETRS89-LAEA (EPSG:3035) | metres |")
    A("| Admin boundaries | WGS84 geographic (EPSG:4326) | degrees |")
    A("| Station coordinates (campaign sheets) | WGS84 geographic, DMS | degrees |")
    A("")
    A("Stations are transformed to EPSG:3035 before snapping, so every distance "
      "below is in true metres.\n")

    A("## Network\n")
    A(f"- Segments: **{len(segments)}**")
    A(f"- Nodes: {len({s['from_node'] for s in segments} | {s['to_node'] for s in segments})}")
    A(f"- Strahler orders: {sorted({s['strahler'] for s in segments})}")
    A(f"- Main-stem segments: {len(main_ids)}")
    A(f"- Outlet nodes (no downstream edge): **{len(outlets)}** → {outlets[:10]}")
    A(f"- Nodes involved in cycles: **{n_cyclic}** "
      f"{'(topology is a clean DAG)' if n_cyclic == 0 else '← MUST BE FIXED'}")
    A(f"- Total network length: {sum(s['length_km'] for s in segments):,.1f} km")
    A("")

    A("## Station snapping\n")
    A(f"- Stations with usable coordinates: **{n}** (of 75 in the campaign files)")
    if invalid:
        A(f"- Stations with no valid coordinate in any campaign: {invalid}")
    A(f"- Snapped within {args.max_snap_m:.0f} m: **{ok} / {n} "
      f"({100*ok/n:.1f}%)**")
    A("")
    A("| percentile | snap distance (m) |")
    A("|---|---|")
    for p, lab in [(0.0, "min"), (0.25, "p25"), (0.5, "median"),
                   (0.75, "p75"), (0.9, "p90"), (0.99, "max")]:
        A(f"| {lab} | {q(p):,.1f} |")
    A("")

    far = [s for s in snapped if s["snap_ok"] == "False"]
    if far:
        A(f"### Stations further than {args.max_snap_m:.0f} m ({len(far)})\n")
        A("| station | snap dist (m) | nearest seg | Strahler | lat | lon |")
        A("|---|---|---|---|---|---|")
        for s in sorted(far, key=lambda r: -float(r["snap_dist_m"])):
            A(f"| {s['station']} | {float(s['snap_dist_m']):,.0f} | {s['seg_id']} | "
              f"{s['strahler']} | {s['lat']} | {s['lon']} |")
        A("")
        A("> These need manual review: either the coordinate is wrong, or the "
          "station lies on a tributary absent from the network layer. They must "
          "be resolved or excluded before reach inference.\n")

    if multi:
        A(f"### Segments carrying more than one station ({len(multi)})\n")
        for seg_id, sts in sorted(multi.items()):
            A(f"- `{seg_id}`: stations {', '.join(sorted(sts, key=int))}")
        A("")
        A("> Within-segment ordering uses `pos_along_seg_m`.\n")

    A("## Reach skeleton\n")
    A(f"- Distinct segments carrying at least one station: "
      f"**{len(station_by_seg)}**")
    A(f"- Ordered upstream/downstream station pairs derivable from the network: "
      f"**{pairs}**")
    A("")
    A("Each such pair defines a reach over which a load balance or a "
      "detection-onset test can be evaluated. This count is the effective "
      "sample size of the whole study.\n")

    if disagreements:
        A("## Coordinate disagreement between campaigns\n")
        for sid, coords in sorted(disagreements, key=lambda d: int(d[0])):
            A(f"- station {sid}: {coords}")
        A("")

    text = "\n".join(L)
    (EVAL / "spatial_join.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"\nwrote: {EVAL/'spatial_join.md'}, {PROC/'segments.csv'}, "
          f"{PROC/'network_edges.csv'}, {PROC/'stations_snapped.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
