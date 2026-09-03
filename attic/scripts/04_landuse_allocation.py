#!/usr/bin/env python3
"""
Allocate land use / pressure sources to river segments, aggregate them upstream,
and compute the land-use DELTA for every station-to-station reach.

This is what makes "micropollutants x land use x hydrology" a single joined
object: for each reach we obtain both (a) which substances first appear there
and (b) which pressures are newly added there.

WHAT THE AREA FIELDS ACTUALLY MEAN  (verified, not assumed)
-----------------------------------------------------------
The hydrology layer carries two area fields whose names invite exactly the wrong
reading, and an earlier version of this script took the bait:

  * `Area_km2`  is NOT the segment's catchment. It is an attribute of the
    WATERSHED (`WtrID`, 35 distinct) repeated on every segment belonging to it.
    Summing it over segments double-counts massively -- the naive total is
    804,742 km2 for a basin of ~11,000 km2. It is carried through here as a
    descriptive field and is never summed.

  * `CArea_km2` is NOT cumulative, despite the leading C. It is the LOCAL
    incremental catchment of the segment's own catchment polygon (`CatchID`,
    989 distinct, one value each). Summed over all 989 segments it gives
    10,967.2 km2, the Ergene basin area, and summing it over the upstream set
    of the single terminal segment S-976 reproduces that same total exactly.
    That telescoping identity is asserted below as a self-test.

So: local catchment = `CArea_km2`; cumulative catchment = its sum over the
upstream set. Both are checked, not trusted.

HOW PRESSURES ARE ALLOCATED
---------------------------
Catchment POLYGONS are not distributed with the dataset, so pressures are
allocated by proximity to the channel network, with three corrections over a
naive nearest-centroid rule:

  1. AREAL pressures are SUBDIVIDED, not point-collapsed. A 40 km2 irrigation
     scheme does not drain to one reach. Each polygon is sampled on a regular
     200 m lattice and every sample is allocated independently, so the polygon's
     area is distributed across the reaches that actually drain it. Area is
     conserved: the shares sum to the polygon's true area.

  2. Allocation is CLIPPED to the basin. The pressure layers are distributed on
     provincial extents (Edirne / Kirklareli / Tekirdag) that reach far beyond
     the Ergene catchment, and an uncapped nearest-segment rule happily assigns
     an irrigation scheme 48 km away to whichever reach happens to be closest.
     The cutoff is not guessed: the network states its own basin area, so the
     radius D is SOLVED so that the area within D of the network equals
     10,967.2 km2. Everything beyond D is reported as clipped, not silently
     allocated.

  3. The nearest-segment search is EXACT. Edges are binned into the spatial
     index by the cells their bounding box spans (binning by vertex, as an
     earlier version did, makes a long edge invisible to queries near its
     midpoint), and the ring search terminates only once the best distance
     found is provably smaller than anything outside the searched block.

The resulting proximity partition is cross-checked against the network's own
`CArea_km2`, so the allocation error is reported rather than hidden.

CRS: everything is transformed to EPSG:3035 (ETRS89-LAEA), which is EQUAL-AREA,
so polygon areas computed here are correct.

Inputs  (read-only):  Data/ShapeFiles/{Erg_river,osbler,tarimalanlari,urban}/*.shp
                      derived/processed/stations_snapped.csv
Outputs:              derived/processed/pressures.csv
                      derived/processed/segment_pressures.csv
                      derived/processed/station_upstream_pressures.csv
                      derived/processed/reaches.csv
                      eval/landuse_allocation.md

Usage:  python scripts/04_landuse_allocation.py [--sample-m 200]
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
import unicodedata
from collections import defaultdict, deque
from pathlib import Path

try:
    import numpy as np
    import shapefile
    from pyproj import Transformer
except ImportError:
    sys.exit("requires pyshp, pyproj and numpy:  pip install pyshp pyproj numpy")

ROOT = Path(__file__).resolve().parent.parent
SHP = ROOT / "Data" / "ShapeFiles"
RIVER_SHP = SHP / "Erg_river" / "Erg_river_Hydro.shp"
PROC = ROOT / "derived" / "processed"
EVAL = ROOT / "eval"

EPSG_TARGET = 3035
CELL = 2000.0            # spatial index cell size, metres
CAL_GRID = 250.0         # lattice for solving the allocation radius, metres

# Pressure layers: (path, kind, geometry, source CRS EPSG)
LAYERS = [
    (SHP / "osbler" / "OSBFirmalar.shp", "industrial_firm", "point", 4326),
    (SHP / "osbler" / "OSBPlanlar.shp", "industrial_zone", "polygon", 4326),
    (SHP / "tarimalanlari" / "TarimAlanlari-Sulama.shp",
     "agriculture_surface_irrigation", "polygon", 4326),
    (SHP / "tarimalanlari" / "TarimAlanlari-YeraltiSuyuSulama.shp",
     "agriculture_groundwater_irrigation", "polygon", 4326),
    (SHP / "urban" / "g100_clc12_v18_5_Ergene_UrbanCity.shp",
     "urban_corine", "polygon", 3035),
]

# ---------------------------------------------------------------------------
# Industrial sector inference from company names.
#
# The OSB firm layer carries 1107 company names in Turkish. Sector is inferred
# from keywords in the trade name -- Turkish company names conventionally state
# the line of business ("... TEKSTIL SAN. TIC. A.S."). This is a heuristic and
# is reported with its coverage; unmatched firms stay 'unclassified' rather than
# being forced into a class.
#
# Sector labels align with the ontology's Industry taxonomy.
# ---------------------------------------------------------------------------
SECTOR_KEYWORDS = {
    "textile": ["tekstil", "iplik", "dokuma", "konfeksiyon", "orme", "kumas",
                "hali", "triko", "boyahane", "apre", "canta"],
    "chemical": ["kimya", "boya", "kimyevi", "deterjan", "polimer", "recine",
                 "yapistirici", "gubre", "asit"],
    "leather": ["deri", "tabak", "kosele", "saraciye"],
    "metal": ["metal", "demir", "celik", "doküm", "dokum", "aluminyum",
              "aluminium", "galvaniz", "kaplama", "hadde", "civata", "tel"],
    "food": ["gida", "sut", "et ", "un ", "yem", "unlu", "bisküvi", "biskuvi",
             "yag", "seker", "meyve", "sebze", "tavuk", "peynir", "makarna"],
    "alcohol_beverage": ["icecek", "alkol", "bira", "sarap", "raki", "mesrubat"],
    "wood_paper": ["orman", "kereste", "mobilya", "ahsap", "kagit", "karton",
                   "ambalaj", "matbaa"],
    "plastic_rubber": ["plastik", "kaucuk", "lastik", "pvc", "polietilen"],
    "mining_stone": ["madencilik", "maden", "mermer", "tas ", "cimento",
                     "beton", "tugla", "kirec", "seramik", "cam"],
    "pharma_cosmetic": ["ilac", "kozmetik", "farma", "medikal", "saglik"],
    "machinery_auto": ["makina", "makine", "otomotiv", "yedek parca", "motor",
                       "elektrik", "elektronik", "kablo"],
    "energy_waste": ["enerji", "geri donusum", "geri kazanim", "aritma",
                     "atik", "petrol", "akaryakit"],
    "agriculture_industry": ["tarim", "ziraat", "hayvancilik", "besicilik",
                             "fide", "tohum"],
}

# Corine LABEL3/CLC_CODE groups actually relevant as urban pressure.
CORINE_GROUPS = {
    "111": "urban_continuous", "112": "urban_discontinuous",
    "121": "industrial_commercial", "122": "transport",
    "123": "port", "124": "airport",
    "131": "mineral_extraction", "132": "dump_site", "133": "construction",
    "141": "green_urban", "142": "sport_leisure",
}


def deaccent(s: str) -> str:
    """Fold Turkish diacritics so keyword matching is robust."""
    s = s.replace("ı", "i").replace("İ", "i").replace("ş", "s").replace("Ş", "s")
    s = s.replace("ğ", "g").replace("Ğ", "g").replace("ç", "c").replace("Ç", "c")
    s = s.replace("ö", "o").replace("Ö", "o").replace("ü", "u").replace("Ü", "u")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def infer_sector(name: str) -> str:
    text = " " + re.sub(r"\s+", " ", deaccent(name)) + " "
    hits = [sec for sec, kws in SECTOR_KEYWORDS.items()
            if any(k in text for k in kws)]
    if not hits:
        return "unclassified"
    if len(hits) == 1:
        return hits[0]
    return "|".join(sorted(hits))  # multi-sector firms kept explicit


# ------------------------------------------------------- nearest network ----

class NearestNetwork:
    """Exact nearest-segment queries over a polyline network.

    Edges -- not vertices -- are binned into a uniform grid, by every cell their
    bounding box spans. Binning by vertex (the previous implementation) leaves a
    long edge unrepresented in the cells between its endpoints, so a query near
    its midpoint finds nothing and silently falls through to a much more distant
    segment.

    The ring search stops only when the result is provably optimal: after
    searching rings 0..r around the query cell, every point outside the searched
    block is more than r*CELL away, so a best distance below r*CELL cannot be
    beaten.
    """

    def __init__(self, seg_geom: dict[str, list[tuple[float, float]]]):
        ax, ay, bx, by, owner, s0 = [], [], [], [], [], []
        for sid, pts in seg_geom.items():
            run = 0.0
            for i in range(len(pts) - 1):
                ax.append(pts[i][0]); ay.append(pts[i][1])
                bx.append(pts[i + 1][0]); by.append(pts[i + 1][1])
                owner.append(sid)
                s0.append(run)          # distance from the segment's start node
                run += math.dist(pts[i], pts[i + 1])
        self.ax = np.asarray(ax); self.ay = np.asarray(ay)
        self.bx = np.asarray(bx); self.by = np.asarray(by)
        self.owner = owner
        self.s0 = np.asarray(s0)
        self.dx = self.bx - self.ax
        self.dy = self.by - self.ay
        self.len2 = self.dx ** 2 + self.dy ** 2
        self.len2[self.len2 == 0.0] = 1.0   # degenerate edge -> point distance
        self.elen = np.sqrt(self.len2)

        buckets = defaultdict(list)
        for e in range(len(owner)):
            cx0 = int(min(self.ax[e], self.bx[e]) // CELL)
            cx1 = int(max(self.ax[e], self.bx[e]) // CELL)
            cy0 = int(min(self.ay[e], self.by[e]) // CELL)
            cy1 = int(max(self.ay[e], self.by[e]) // CELL)
            for gx in range(cx0, cx1 + 1):
                for gy in range(cy0, cy1 + 1):
                    buckets[(gx, gy)].append(e)
        self.grid = {k: np.asarray(v) for k, v in buckets.items()}
        self.max_ring = 40   # 80 km; the basin is ~140 km across

    def _dist_to(self, idx, x, y):
        """Distance to each candidate edge, and the projection parameter t."""
        t = ((x - self.ax[idx]) * self.dx[idx]
             + (y - self.ay[idx]) * self.dy[idx]) / self.len2[idx]
        np.clip(t, 0.0, 1.0, out=t)
        d = np.hypot(x - (self.ax[idx] + t * self.dx[idx]),
                     y - (self.ay[idx] + t * self.dy[idx]))
        return d, t

    def query(self, x: float, y: float):
        """Return (seg_id, distance_m, pos_along_seg_m), exactly.

        `pos_along_seg_m` is the arc length from the segment's FROM_NODE to the
        projected point, which is what makes two stations on the same segment
        orderable.
        """
        gx, gy = int(x // CELL), int(y // CELL)
        pool: list[np.ndarray] = []
        best_sid, best_d, best_pos = None, float("inf"), float("nan")
        for ring in range(self.max_ring + 1):
            added = False
            for dxc in range(-ring, ring + 1):
                for dyc in range(-ring, ring + 1):
                    if ring and max(abs(dxc), abs(dyc)) != ring:
                        continue
                    b = self.grid.get((gx + dxc, gy + dyc))
                    if b is not None:
                        pool.append(b)
                        added = True
            if added:
                idx = np.concatenate(pool)
                d, t = self._dist_to(idx, x, y)
                k = int(np.argmin(d))
                if d[k] < best_d:
                    e = int(idx[k])
                    best_d = float(d[k])
                    best_sid = self.owner[e]
                    best_pos = float(self.s0[e] + t[k] * self.elen[e])
                pool = [idx]        # keep the union, avoid re-concatenating
            # everything outside rings 0..ring is further than ring*CELL away
            if best_sid is not None and best_d <= ring * CELL:
                return best_sid, best_d, best_pos
        return best_sid, best_d, best_pos

    def query_many(self, xs: np.ndarray, ys: np.ndarray):
        """Vectorised over a lattice: returns (owner_index array, distances).

        Points are grouped by grid cell so the candidate gather happens once per
        cell rather than once per point.
        """
        out_sid = [None] * len(xs)
        out_d = np.full(len(xs), np.inf)
        out_pos = np.full(len(xs), np.nan)
        cells = defaultdict(list)
        for i, (x, y) in enumerate(zip(xs, ys)):
            cells[(int(x // CELL), int(y // CELL))].append(i)
        for (gx, gy), members in cells.items():
            m = np.asarray(members)
            mx, my = xs[m], ys[m]
            pool = []
            ring = 0
            while ring <= self.max_ring:
                for dxc in range(-ring, ring + 1):
                    for dyc in range(-ring, ring + 1):
                        if ring and max(abs(dxc), abs(dyc)) != ring:
                            continue
                        b = self.grid.get((gx + dxc, gy + dyc))
                        if b is not None:
                            pool.append(b)
                if pool:
                    idx = np.concatenate(pool)
                    pool = [idx]
                    # (points x edges) distance matrix for this cell
                    t = ((mx[:, None] - self.ax[idx][None, :]) * self.dx[idx][None, :]
                         + (my[:, None] - self.ay[idx][None, :]) * self.dy[idx][None, :]) \
                        / self.len2[idx][None, :]
                    np.clip(t, 0.0, 1.0, out=t)
                    d = np.hypot(mx[:, None] - (self.ax[idx][None, :] + t * self.dx[idx][None, :]),
                                 my[:, None] - (self.ay[idx][None, :] + t * self.dy[idx][None, :]))
                    j = np.argmin(d, axis=1)
                    dv = d[np.arange(len(m)), j]
                    tv = t[np.arange(len(m)), j]
                    for a, i in enumerate(m):
                        if dv[a] < out_d[i]:
                            e = int(idx[j[a]])
                            out_d[i] = dv[a]
                            out_sid[i] = self.owner[e]
                            out_pos[i] = self.s0[e] + tv[a] * self.elen[e]
                    if float(dv.max()) <= ring * CELL:
                        break
                ring += 1
        return out_sid, out_d, out_pos


# ---------------------------------------------------------------- geometry --

def ring_area_centroid(ring):
    """Shoelace signed area (m^2, LAEA is equal-area) and centroid."""
    a = cx = cy = 0.0
    for i in range(len(ring) - 1):
        x0, y0 = ring[i]
        x1, y1 = ring[i + 1]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if abs(a) < 1e-9:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return 0.0, (sum(xs) / len(xs), sum(ys) / len(ys))
    return a, (cx / (6 * a), cy / (6 * a))


def polygon_rings(shape, tf=None):
    parts = list(shape.parts) + [len(shape.points)]
    rings = []
    for i in range(len(parts) - 1):
        pts = shape.points[parts[i]:parts[i + 1]]
        if tf is not None:
            ring = [tf.transform(float(px), float(py)) for px, py in pts]
        else:
            ring = [(float(px), float(py)) for px, py in pts]
        if len(ring) < 3:
            continue
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        rings.append(ring)
    return rings


def polygon_area_centroid(rings):
    """Area (m^2) and centroid of a possibly multi-ring polygon.

    Outer rings are positive (clockwise in shapefile convention), holes
    negative; summing signed areas handles holes correctly.
    """
    total = wx = wy = 0.0
    for ring in rings:
        a, (cx, cy) = ring_area_centroid(ring)
        total += a
        wx += cx * a
        wy += cy * a
    if abs(total) < 1e-9:
        pts = [p for r in rings for p in r]
        if not pts:
            return 0.0, (0.0, 0.0)
        return 0.0, (sum(p[0] for p in pts) / len(pts),
                     sum(p[1] for p in pts) / len(pts))
    return abs(total), (wx / total, wy / total)


def points_in_polygon(rings, px, py):
    """Vectorised even-odd crossing test over all rings (holes handled)."""
    inside = np.zeros(len(px), dtype=bool)
    for ring in rings:
        r = np.asarray(ring)
        x0, y0 = r[:-1, 0], r[:-1, 1]
        x1, y1 = r[1:, 0], r[1:, 1]
        for i in range(len(x0)):
            cond = ((y0[i] > py) != (y1[i] > py))
            if not cond.any():
                continue
            xint = (x1[i] - x0[i]) * (py - y0[i]) / (y1[i] - y0[i]) + x0[i]
            inside ^= cond & (px < xint)
    return inside


def lattice_over(rings, step):
    """Regular lattice of sample points covering the polygon's bounding box."""
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    # anchor to a global lattice so neighbouring polygons sample consistently
    gx = np.arange(math.floor(x0 / step) * step + step / 2, x1 + step, step)
    gy = np.arange(math.floor(y0 / step) * step + step / 2, y1 + step, step)
    if len(gx) == 0 or len(gy) == 0:
        return np.array([]), np.array([])
    mx, my = np.meshgrid(gx, gy)
    return mx.ravel(), my.ravel()


def open_reader(path):
    for enc in ("utf-8", "cp1254", "latin-1"):
        try:
            sf = shapefile.Reader(str(path), encoding=enc)
            sf.records()
            return sf, enc
        except Exception:
            continue
    raise RuntimeError(f"cannot read {path}")


# ------------------------------------------------------------------- main --

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-m", type=float, default=200.0,
                    help="lattice spacing for subdividing areal pressures (m)")
    args = ap.parse_args()
    EVAL.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)

    notes = []   # verification findings surfaced in the report

    # ---- river geometry (already EPSG:3035) --------------------------------
    sf = shapefile.Reader(str(RIVER_SHP))
    names = [f[0] for f in sf.fields[1:]]
    ix = {n: i for i, n in enumerate(names)}
    seg_geom, seg_meta = {}, {}
    for shp, rec in zip(sf.shapes(), sf.records()):
        pts = [(float(x), float(y)) for x, y in shp.points]
        if len(pts) < 2:
            continue
        sid = str(rec[ix["SegID"]])
        seg_geom[sid] = pts
        seg_meta[sid] = {
            "from_node": str(rec[ix["FROM_NODE"]]),
            "to_node": str(rec[ix["TO_NODE"]]),
            "catch_id": str(rec[ix["CatchID"]]),
            "wtr_id": str(rec[ix["WtrID"]]),
            "strahler": int(rec[ix["StrahlerOr"]]),
            # LOCAL incremental catchment -- verified below, see module docstring
            "local_catchment_km2": float(rec[ix["CArea_km2"]]),
            # WATERSHED attribute, repeated per segment. Never summed.
            "watershed_km2": float(rec[ix["Area_km2"]]),
            "length_km": float(rec[ix["Length_km"]]),
        }
    sf.close()

    # ---- verify the area-field semantics rather than trusting the names ----
    catch_ids = {m["catch_id"] for m in seg_meta.values()}
    wtr_area = defaultdict(set)
    for m in seg_meta.values():
        wtr_area[m["wtr_id"]].add(round(m["watershed_km2"], 6))
    basin_km2 = sum(m["local_catchment_km2"] for m in seg_meta.values())
    wtr_sum = sum(next(iter(v)) for v in wtr_area.values())

    if len(catch_ids) != len(seg_meta):
        notes.append(f"CatchID is not 1:1 with segments "
                     f"({len(catch_ids)} ids for {len(seg_meta)} segments); "
                     f"local catchment areas may be shared and would then be "
                     f"double-counted upstream.")
    if any(len(v) != 1 for v in wtr_area.values()):
        notes.append("Area_km2 varies within a WtrID; it is not a pure "
                     "watershed attribute after all — re-check before use.")
    if abs(wtr_sum - basin_km2) / basin_km2 > 0.01:
        notes.append(f"watershed areas sum to {wtr_sum:,.1f} km2 but local "
                     f"catchments sum to {basin_km2:,.1f} km2; the two "
                     f"partitions disagree.")

    net = NearestNetwork(seg_geom)

    # ---- topology ----------------------------------------------------------
    in_edges = defaultdict(list)
    out_edges = defaultdict(list)
    for sid, m in seg_meta.items():
        in_edges[m["to_node"]].append(sid)
        out_edges[m["from_node"]].append(sid)

    def upstream_set(sid):
        seen, queue = {sid}, deque([seg_meta[sid]["from_node"]])
        while queue:
            node = queue.popleft()
            for up in in_edges.get(node, []):
                if up in seen:
                    continue
                seen.add(up)
                queue.append(seg_meta[up]["from_node"])
        return seen

    terminals = [s for s in seg_meta if not out_edges.get(seg_meta[s]["to_node"])]
    # Telescoping self-test: cumulative catchment at the outlet must be the basin.
    outlet_check = ""
    if len(terminals) == 1:
        t = terminals[0]
        us_t = upstream_set(t)
        cum = sum(seg_meta[u]["local_catchment_km2"] for u in us_t)
        outlet_check = (f"single outlet `{t}`, {len(us_t)} segments upstream, "
                        f"cumulative catchment {cum:,.1f} km2 "
                        f"vs basin total {basin_km2:,.1f} km2")
        if abs(cum - basin_km2) > 1.0:
            notes.append(f"cumulative catchment at the outlet ({cum:,.1f} km2) "
                         f"does not close on the basin total "
                         f"({basin_km2:,.1f} km2).")
    else:
        notes.append(f"{len(terminals)} terminal segments; the network is not a "
                     f"single drainage tree, so cumulative areas cannot be "
                     f"closed against the basin total.")

    # ---- solve the allocation radius from the basin's own area -------------
    # The area within distance D of the network is a monotone function of D.
    # Solve D so that it equals the basin area the network itself reports.
    xs_all = [p[0] for pts in seg_geom.values() for p in pts]
    ys_all = [p[1] for pts in seg_geom.values() for p in pts]
    pad = 12000.0
    gx = np.arange(min(xs_all) - pad, max(xs_all) + pad, CAL_GRID) + CAL_GRID / 2
    gy = np.arange(min(ys_all) - pad, max(ys_all) + pad, CAL_GRID) + CAL_GRID / 2
    MX, MY = np.meshgrid(gx, gy)
    MX, MY = MX.ravel(), MY.ravel()
    print(f"  solving allocation radius on {len(MX):,} lattice cells "
          f"({CAL_GRID:.0f} m) …")
    _, dgrid, _ = net.query_many(MX, MY)
    cell_km2 = (CAL_GRID / 1000.0) ** 2
    lo, hi = 0.0, 20000.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if float((dgrid <= mid).sum()) * cell_km2 < basin_km2:
            lo = mid
        else:
            hi = mid
    D_MAX = 0.5 * (lo + hi)
    covered = float((dgrid <= D_MAX).sum()) * cell_km2
    print(f"  allocation radius D = {D_MAX:,.0f} m "
          f"(covers {covered:,.0f} km2 vs basin {basin_km2:,.1f} km2)")

    # ---- read and allocate pressures ---------------------------------------
    pressures = []          # one row per (feature, segment) allocation share
    layer_report = []
    for path, kind, geom, epsg in LAYERS:
        if not path.exists():
            layer_report.append([path.name, kind, 0, 0, 0, 0.0, 0.0, "MISSING"])
            continue
        sf, enc = open_reader(path)
        flds = [f[0] for f in sf.fields[1:]]
        fi = {n: i for i, n in enumerate(flds)}
        tf = (Transformer.from_crs(epsg, EPSG_TARGET, always_xy=True)
              if epsg != EPSG_TARGET else None)
        n_feat = n_alloc = 0
        area_in = area_clip = 0.0

        for shp, rec in zip(sf.shapes(), sf.records()):
            if not shp.points:
                continue
            n_feat += 1
            name = str(rec[fi["Name"]]) if "Name" in fi else ""
            if kind == "urban_corine":
                code = str(rec[fi["CLC_CODE"]]) if "CLC_CODE" in fi else ""
                label = str(rec[fi["LABEL3"]]) if "LABEL3" in fi else ""
                subtype = CORINE_GROUPS.get(code, f"clc_{code}")
                name = label or subtype
            elif kind == "industrial_firm":
                subtype = infer_sector(name)
            else:
                subtype = kind

            if geom == "point":
                x, y = float(shp.points[0][0]), float(shp.points[0][1])
                if tf:
                    x, y = tf.transform(x, y)
                sid, dist, pos = net.query(x, y)
                if sid is None or dist > D_MAX:
                    continue      # outside the basin footprint
                n_alloc += 1
                pressures.append({
                    "kind": kind, "subtype": subtype, "name": name,
                    "x_3035": f"{x:.1f}", "y_3035": f"{y:.1f}",
                    "count": 1, "area_km2": "0.000000",
                    "seg_id": sid, "dist_to_seg_m": f"{dist:.1f}",
                    "pos_along_seg_m": f"{pos:.1f}",
                })
                continue

            # --- areal: subdivide on a lattice, allocate each sample ---------
            rings = polygon_rings(shp, tf)
            if not rings:
                continue
            area_m2, (cx, cy) = polygon_area_centroid(rings)
            area_in += area_m2 / 1e6
            lx, ly = lattice_over(rings, args.sample_m)
            hit = points_in_polygon(rings, lx, ly) if len(lx) else np.array([], bool)
            n_in = int(hit.sum())

            if n_in < 4:
                # Too small to subdivide meaningfully: fall back to the centroid.
                sid, dist, pos = net.query(cx, cy)
                if sid is None or dist > D_MAX:
                    area_clip += area_m2 / 1e6
                    continue
                n_alloc += 1
                pressures.append({
                    "kind": kind, "subtype": subtype, "name": name,
                    "x_3035": f"{cx:.1f}", "y_3035": f"{cy:.1f}",
                    "count": 1, "area_km2": f"{area_m2/1e6:.6f}",
                    "seg_id": sid, "dist_to_seg_m": f"{dist:.1f}",
                    "pos_along_seg_m": f"{pos:.1f}",
                })
                continue

            sx, sy = lx[hit], ly[hit]
            sids, dists, poss = net.query_many(sx, sy)
            share = defaultdict(int)
            dsum = defaultdict(float)
            psum = defaultdict(float)
            n_ok = 0
            for s_, d_, p_ in zip(sids, dists, poss):
                if s_ is None or d_ > D_MAX:
                    continue
                share[s_] += 1
                dsum[s_] += d_
                psum[s_] += p_
                n_ok += 1
            if not n_ok:
                area_clip += area_m2 / 1e6
                continue
            # Area is conserved against the polygon's TRUE area: shares are
            # fractions of the samples that fell inside it.
            area_clip += area_m2 / 1e6 * (n_in - n_ok) / n_in
            n_alloc += 1
            for s_, c_ in sorted(share.items()):
                pressures.append({
                    "kind": kind, "subtype": subtype, "name": name,
                    "x_3035": f"{cx:.1f}", "y_3035": f"{cy:.1f}",
                    "count": 1 if c_ == max(share.values()) else 0,
                    "area_km2": f"{area_m2/1e6*c_/n_in:.6f}",
                    "seg_id": s_, "dist_to_seg_m": f"{dsum[s_]/c_:.1f}",
                    "pos_along_seg_m": f"{psum[s_]/c_:.1f}",
                })

        layer_report.append([path.name, kind, n_feat, n_alloc,
                             n_feat - n_alloc, area_in, area_clip, enc])
        sf.close()
        print(f"  {kind:38s} {n_alloc:5d}/{n_feat:5d} features, "
              f"{area_clip:8.1f} km2 clipped outside the basin")

    with (PROC / "pressures.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(pressures[0].keys()))
        w.writeheader()
        w.writerows(sorted(pressures,
                           key=lambda p: (p["kind"], p["seg_id"], p["name"])))

    # ---- per-segment local totals ------------------------------------------
    # `count` marks a feature's PRIMARY segment (the one holding most of its
    # area), so feature counts stay counts and are not inflated by subdivision.
    KINDS = sorted({p["kind"] for p in pressures})
    local = defaultdict(lambda: defaultdict(float))
    local_n = defaultdict(lambda: defaultdict(int))
    sector_n = defaultdict(lambda: defaultdict(int))
    for p in pressures:
        sid, k = p["seg_id"], p["kind"]
        local_n[sid][k] += int(p["count"])
        local[sid][k] += float(p["area_km2"])
        if k == "industrial_firm":
            for sec in p["subtype"].split("|"):
                sector_n[sid][sec] += int(p["count"])

    SECTORS = sorted({s for d in sector_n.values() for s in d})

    with (PROC / "segment_pressures.csv").open("w", newline="",
                                               encoding="utf-8") as fh:
        fields = (["seg_id", "strahler", "local_catchment_km2", "watershed_km2"]
                  + [f"n_{k}" for k in KINDS] + [f"km2_{k}" for k in KINDS]
                  + [f"nfirm_{s}" for s in SECTORS])
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for sid in sorted(seg_meta):
            row = {"seg_id": sid, "strahler": seg_meta[sid]["strahler"],
                   "local_catchment_km2":
                       f"{seg_meta[sid]['local_catchment_km2']:.4f}",
                   "watershed_km2": f"{seg_meta[sid]['watershed_km2']:.4f}"}
            for k in KINDS:
                row[f"n_{k}"] = local_n[sid][k]
                row[f"km2_{k}"] = f"{local[sid][k]:.6f}"
            for s in SECTORS:
                row[f"nfirm_{s}"] = sector_n[sid][s]
            w.writerow(row)

    # ---- cross-check the proximity partition against CArea_km2 -------------
    # The lattice already carries a nearest-segment label; comparing the two
    # partitions is the honest way to report how good "nearest segment" is.
    near_sid, near_d, _ = net.query_many(MX, MY)
    prox = defaultdict(float)
    for s_, d_ in zip(near_sid, near_d):
        if s_ is not None and d_ <= D_MAX:
            prox[s_] += cell_km2
    both = [(prox.get(s, 0.0), seg_meta[s]["local_catchment_km2"])
            for s in seg_meta]
    pa = np.array([b[0] for b in both])
    ca = np.array([b[1] for b in both])

    def spearman(u, v):
        ru = np.argsort(np.argsort(u)).astype(float)
        rv = np.argsort(np.argsort(v)).astype(float)
        ru -= ru.mean(); rv -= rv.mean()
        return float((ru * rv).sum() / math.sqrt((ru ** 2).sum() * (rv ** 2).sum()))

    rho = spearman(pa, ca)
    mae = float(np.abs(pa - ca).mean())
    agree = float(np.minimum(pa, ca).sum() / max(ca.sum(), 1e-9))

    # ---- upstream aggregation ----------------------------------------------
    # What is upstream of a STATION, not merely of its segment. A station sits
    # part-way along its segment, so that segment contributes only the part
    # above it:
    #
    #   * pressures -- exactly those whose projected position lies above the
    #     station, since every allocation records its along-segment position;
    #   * catchment -- the segment's local catchment scaled by the fraction of
    #     the segment above the station (linear interpolation; no finer
    #     information exists without catchment polygons).
    #
    # This is what makes a reach between two stations ON THE SAME SEGMENT
    # computable rather than degenerate. Under a whole-segment rule such a pair
    # is upstream of itself in both directions: 18 of the 28 "immediate"
    # reaches were 9 station pairs counted twice, each with a zero delta.
    press_by_seg = defaultdict(list)
    for p in pressures:
        press_by_seg[p["seg_id"]].append(
            (float(p["pos_along_seg_m"]), p["kind"], p["subtype"],
             float(p["area_km2"]), int(p["count"])))
    for v in press_by_seg.values():
        v.sort()

    stations = list(csv.DictReader((PROC / "stations_snapped.csv")
                                   .open(encoding="utf-8")))
    for s in stations:
        s["pos"] = float(s["pos_along_seg_m"])

    upstream_cache = {}

    def content(sid, pos):
        """Pressures and catchment upstream of a point at `pos` on `sid`."""
        if sid not in upstream_cache:
            upstream_cache[sid] = upstream_set(sid)
        us = upstream_cache[sid]
        agg = {f"n_{k}": 0 for k in KINDS}
        agg.update({f"km2_{k}": 0.0 for k in KINDS})
        agg.update({f"nfirm_{s2}": 0 for s2 in SECTORS})
        for u in us:
            own = (u == sid)
            for ppos, k, sub, area, cnt in press_by_seg.get(u, ()):
                if own and ppos > pos:
                    break          # positions are sorted
                agg[f"n_{k}"] += cnt
                agg[f"km2_{k}"] += area
                if k == "industrial_firm" and cnt:
                    for sec in sub.split("|"):
                        agg[f"nfirm_{sec}"] += cnt
        seg_len = max(seg_meta[sid]["length_km"] * 1000.0, 1e-6)
        frac = min(max(pos / seg_len, 0.0), 1.0)
        agg["n_upstream_segments"] = len(us)
        agg["upstream_catchment_km2"] = (
            sum(seg_meta[u]["local_catchment_km2"] for u in us if u != sid)
            + seg_meta[sid]["local_catchment_km2"] * frac)
        agg["local_catchment_km2"] = seg_meta[sid]["local_catchment_km2"]
        return agg

    up_press = {s["station"]: content(s["seg_id"], s["pos"]) for s in stations}

    def is_upstream(a, b):
        """Station `a` lies strictly upstream of station `b`."""
        if a["seg_id"] not in upstream_cache[b["seg_id"]]:
            return False
        if a["seg_id"] == b["seg_id"]:
            return a["pos"] < b["pos"]
        return True

    with (PROC / "station_upstream_pressures.csv").open("w", newline="",
                                                        encoding="utf-8") as fh:
        fields = (["station", "seg_id", "strahler", "n_upstream_segments",
                   "upstream_catchment_km2", "local_catchment_km2"]
                  + [f"n_{k}" for k in KINDS] + [f"km2_{k}" for k in KINDS]
                  + [f"nfirm_{s}" for s in SECTORS])
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for s in sorted(stations, key=lambda r: int(r["station"])):
            a = up_press[s["station"]]
            row = {"station": s["station"], "seg_id": s["seg_id"],
                   "strahler": s["strahler"],
                   "n_upstream_segments": a["n_upstream_segments"],
                   "upstream_catchment_km2": f"{a['upstream_catchment_km2']:.4f}",
                   "local_catchment_km2": f"{a['local_catchment_km2']:.4f}"}
            for k in KINDS:
                row[f"n_{k}"] = a[f"n_{k}"]
                row[f"km2_{k}"] = f"{a[f'km2_{k}']:.6f}"
            for s2 in SECTORS:
                row[f"nfirm_{s2}"] = a[f"nfirm_{s2}"]
            w.writerow(row)

    # ---- reaches: ordered station pairs + land-use delta -------------------
    # A reach is (upstream station U, downstream station D) where U's segment is
    # in D's upstream set. "Immediate" reaches have no third station between.
    reaches = []
    for d in stations:
        ups = [u for u in stations if is_upstream(u, d)]
        for u in ups:
            # A reach is immediate when no OTHER station lies anywhere in the
            # catchment it adds -- not merely on the flow path between the two.
            # A station on a tributary joining in between still supplies its own
            # evidence about that water, so the pair is not a clean two-station
            # unit. Testing only the flow path (an earlier attempt) inflated the
            # count from 28 to 72 and let single "reaches" swallow the entire
            # basin: R-24-72 came out adding 10,364 km2 and all 1,048 firms.
            mid = [m for m in stations
                   if m["station"] not in (u["station"], d["station"])
                   and is_upstream(m, d) and not is_upstream(m, u)]
            immediate = not mid
            au, ad = up_press[u["station"]], up_press[d["station"]]
            row = {
                "reach_id": f"R-{u['station']}-{d['station']}",
                "up_station": u["station"], "down_station": d["station"],
                "up_seg": u["seg_id"], "down_seg": d["seg_id"],
                "immediate": str(immediate),
                "n_intervening_stations": len(mid),
                "d_catchment_km2": f"{ad['upstream_catchment_km2']-au['upstream_catchment_km2']:.4f}",
            }
            for k in KINDS:
                row[f"d_n_{k}"] = ad[f"n_{k}"] - au[f"n_{k}"]
                row[f"d_km2_{k}"] = f"{ad[f'km2_{k}']-au[f'km2_{k}']:.6f}"
            for s2 in SECTORS:
                row[f"d_nfirm_{s2}"] = ad[f"nfirm_{s2}"] - au[f"nfirm_{s2}"]
            reaches.append(row)

    with (PROC / "reaches.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(reaches[0].keys()))
        w.writeheader()
        w.writerows(reaches)

    # ---- report -------------------------------------------------------------
    immediate = [r for r in reaches if r["immediate"] == "True"]
    firm_rows = [p for p in pressures if p["kind"] == "industrial_firm"]
    n_firms = len(firm_rows)
    unclassified = sum(1 for p in firm_rows if p["subtype"] == "unclassified")

    L = []
    A = L.append
    A("# Land-use allocation and reach construction\n")
    A("Generated by `scripts/04_landuse_allocation.py`.\n")

    A("## What the area fields mean\n")
    A("Verified against the data, because the field names are misleading:\n")
    A("| field | naive reading | what it actually is | evidence |")
    A("|---|---|---|---|")
    A(f"| `Area_km2` | segment catchment | **watershed attribute**, repeated on "
      f"every segment of its `WtrID` | {len(wtr_area)} watersheds, one distinct "
      f"value each; naive sum over segments = "
      f"{sum(m['watershed_km2'] for m in seg_meta.values()):,.0f} km² |")
    A(f"| `CArea_km2` | cumulative catchment | **local incremental catchment** of "
      f"the segment's own `CatchID` | {len(catch_ids)} catchments for "
      f"{len(seg_meta)} segments; sum = {basin_km2:,.1f} km² |")
    A("")
    A(f"Both partitions close on the same basin area "
      f"({wtr_sum:,.1f} km² by watershed, {basin_km2:,.1f} km² by catchment), "
      f"which is what makes the reading above verifiable rather than plausible.\n")
    if outlet_check:
        A(f"Telescoping self-test: {outlet_check}.\n")
    A("Cumulative catchment is therefore computed as the sum of `CArea_km2` "
      "over a segment's upstream set. `Area_km2` is carried as a descriptive "
      "field and never summed.\n")

    A("## Allocation radius\n")
    A(f"Pressure layers are distributed on provincial extents that reach well "
      f"beyond the catchment, so allocation must be clipped. The radius is not "
      f"chosen by eye: it is solved so that the area within *D* of the channel "
      f"network equals the basin area the network itself reports.\n")
    A(f"- basin area (Σ`CArea_km2`): **{basin_km2:,.1f} km²**")
    A(f"- channel length: {sum(m['length_km'] for m in seg_meta.values()):,.0f} km")
    A(f"- solved radius **D = {D_MAX:,.0f} m**, covering {covered:,.0f} km² "
      f"on a {CAL_GRID:.0f} m lattice")
    A(f"- areal pressures are subdivided on a {args.sample_m:.0f} m lattice, so "
      f"a polygon spanning several reaches is split between them\n")

    A("## Layers read\n")
    A("| file | pressure kind | features | allocated | outside basin | "
      "area in layer (km²) | area clipped (km²) | encoding |")
    A("|---|---|---|---|---|---|---|---|")
    for fn, kind, tot, alloc, drop, ain, aclip, enc in layer_report:
        A(f"| `{fn}` | {kind} | {tot} | {alloc} | {drop} | {ain:,.1f} | "
          f"{aclip:,.1f} | {enc} |")
    A("")
    A("All layers transformed to EPSG:3035 (ETRS89-LAEA, equal-area), so areas "
      "are metric and comparable. OSB and agriculture layers are natively WGS84; "
      "the Corine layer and the river network are natively EPSG:3035.\n")
    tot_clip = sum(r[6] for r in layer_report)
    tot_in = sum(r[5] for r in layer_report)
    if tot_in:
        A(f"> **{tot_clip:,.0f} km² of {tot_in:,.0f} km² "
          f"({100*tot_clip/tot_in:.0f}%)** of the areal pressure layers lies "
          f"outside the basin footprint and is discarded. An uncapped "
          f"nearest-segment rule would have allocated all of it.\n")

    A("## Allocation quality\n")
    A(f"The proximity partition (nearest segment within *D*) is compared "
      f"against the network's own local catchments — an independent field in "
      f"the same dataset:\n")
    A(f"- Spearman ρ(proximity area, `CArea_km2`) = **{rho:.3f}**")
    A(f"- mean absolute difference = {mae:.2f} km² per segment "
      f"(mean catchment {basin_km2/len(seg_meta):.2f} km²)")
    A(f"- overlap agreement Σmin/Σ`CArea_km2` = **{100*agree:.1f}%**\n")
    A("Proximity is therefore a good but imperfect stand-in for the true "
      "catchment: it recovers the right ranking of segments and most of the "
      "area, and the residual is the price of not having catchment polygons. "
      "Reach-level conclusions are drawn from *differences* between nested "
      "upstream sets, where this error largely cancels.\n")
    dists = sorted(float(p["dist_to_seg_m"]) for p in pressures)
    A(f"- allocation records (feature × segment): **{len(pressures):,}**")
    A(f"- distance to allocated segment: median "
      f"{dists[len(dists)//2]:,.0f} m, p90 {dists[int(0.9*len(dists))]:,.0f} m, "
      f"max {dists[-1]:,.0f} m (bounded by *D*)\n")

    A("## Industrial sector inference\n")
    A(f"Sector is inferred from the Turkish trade name of each of the "
      f"**{n_firms}** OSB firms allocated inside the basin.\n")
    A(f"- classified: **{n_firms-unclassified}** "
      f"({100*(n_firms-unclassified)/max(n_firms,1):.1f}%)")
    A(f"- unclassified: {unclassified}\n")
    A("| sector | firms |")
    A("|---|---|")
    sec_tot = defaultdict(int)
    for p in firm_rows:
        for s in p["subtype"].split("|"):
            sec_tot[s] += 1
    for s, c in sorted(sec_tot.items(), key=lambda x: -x[1]):
        A(f"| {s} | {c} |")
    A("")
    A("> Firms matching several sector keywords keep all of them "
      "(`textile|chemical`), because a dyehouse genuinely is both. Unclassified "
      "firms are never forced into a class.\n")

    A("## Reaches\n")
    A(f"- Ordered station pairs (all): **{len(reaches)}**")
    A(f"- **Immediate reaches** (no intervening station): **{len(immediate)}**")
    A("")
    A("Immediate reaches are the inferential unit: a substance appearing at the "
      "downstream station but not the upstream one is attributable to the "
      "pressures added within that reach, given in the `d_*` columns.\n")
    A("| reach | Δcatchment km² | Δfirms | Δagri km² | Δurban km² |")
    A("|---|---|---|---|---|")
    for r in sorted(immediate,
                    key=lambda r: -int(r.get("d_n_industrial_firm", 0)))[:15]:
        agri = (float(r.get("d_km2_agriculture_surface_irrigation", 0))
                + float(r.get("d_km2_agriculture_groundwater_irrigation", 0)))
        A(f"| {r['reach_id']} | {float(r['d_catchment_km2']):,.1f} | "
          f"{r.get('d_n_industrial_firm', 0)} | {agri:,.1f} | "
          f"{float(r.get('d_km2_urban_corine', 0)):,.1f} |")
    A("")
    A("(top 15 immediate reaches by number of industrial firms added)\n")

    if notes:
        A("## Verification findings\n")
        for n in notes:
            A(f"- **{n}**")
        A("")

    text = "\n".join(L)
    (EVAL / "landuse_allocation.md").write_text(text, encoding="utf-8")
    print("\n" + text)
    print(f"\nwrote: {EVAL/'landuse_allocation.md'}, {PROC/'pressures.csv'}, "
          f"{PROC/'segment_pressures.csv'}, "
          f"{PROC/'station_upstream_pressures.csv'}, {PROC/'reaches.csv'}")
    return 1 if notes else 0


if __name__ == "__main__":
    raise SystemExit(main())
