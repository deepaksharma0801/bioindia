"""Phase 10: build gridded forest-change, fragmentation and human-pressure layers for India.

Sources (downloaded by scripts/phase10_download_landuse.sh):
  * Hansen/UMD/Google/USGS/NASA Global Forest Change 2000-2024 v1.12 (30 m; tree cover 2000, loss year,
    data mask), CC BY 4.0.
  * GHSL R2023A built-up surface and population, epoch 2020, 30 arc-seconds, CC BY 4.0.

Everything is aggregated to 0.05-degree cells (about 5.5 km), stored in land_use_cells, then summarised:
  * species_land_pressure: conditions in the cells a species occupies (records within 10 km only);
  * analytics_grid_cells: the Phase 13 0.75-degree cells gain forest, loss, fragmentation and pressure columns.

Usage: python scripts/phase10_build_land_use_grid.py [--skip-rasters]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
import zipfile
from pathlib import Path

import numpy as np
import psycopg
import rasterio
from rasterio.windows import Window, from_bounds

from db_schema import ensure_schema


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "landuse"
CELLS_FILE = ROOT / "data" / "processed" / "land_use_cells_005deg.npz"
REPORT = ROOT / "data" / "analytics" / "land_use_report.json"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia")

HANSEN_VERSION = "GFC-2024-v1.12"
TILES = ["10N_070E", "10N_090E", "20N_070E", "20N_080E", "20N_090E", "30N_060E", "30N_070E", "30N_080E", "30N_090E", "40N_070E", "40N_080E"]
CELLS_PER_DEGREE = 20  # 0.05-degree cells
PIXELS_PER_DEGREE = 4000  # Hansen 0.00025-degree pixels
PIXELS_PER_CELL = PIXELS_PER_DEGREE // CELLS_PER_DEGREE
BAND_ROWS = 1000  # read 0.25 degrees of rows at a time
FOREST_THRESHOLD = 30  # % canopy cover in 2000, the Global Forest Watch default
LOSS_YEARS = list(range(2001, 2025))
RECENT_FROM = 2015
INDIA_BOUNDS = (68.0, 6.0, 98.0, 38.0)  # west, south, east, north
ELIGIBLE_UNCERTAINTY_CLASSES = ["precise", "moderate"]


def cell_area_km2(iy: np.ndarray) -> np.ndarray:
    """Area of a 0.05-degree cell on a sphere of the WGS 84 authalic radius."""
    radius = 6371.0072
    south = np.radians(iy / CELLS_PER_DEGREE)
    north = np.radians((iy + 1) / CELLS_PER_DEGREE)
    return radius ** 2 * math.radians(1 / CELLS_PER_DEGREE) * (np.sin(north) - np.sin(south))


def block_sum(array: np.ndarray) -> np.ndarray:
    rows, cols = array.shape
    return array.reshape(rows // PIXELS_PER_CELL, PIXELS_PER_CELL, cols // PIXELS_PER_CELL, PIXELS_PER_CELL).sum(axis=(1, 3), dtype=np.int64)


def forest_edges(forest: np.ndarray) -> np.ndarray:
    """Forest pixels with at least one non-forest 4-neighbour (strip edges are treated as forest)."""
    padded = np.pad(forest, 1, mode="edge")
    interior = padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
    return forest & ~interior


def hansen_tile(tile: str) -> dict[str, np.ndarray]:
    """Pixel counts per 0.05-degree cell for one 10 x 10 degree Hansen tile."""
    paths = {layer: RAW / "hansen" / f"Hansen_{HANSEN_VERSION}_{layer}_{tile}.tif" for layer in ("treecover2000", "lossyear", "datamask")}
    with rasterio.open(paths["treecover2000"]) as cover, rasterio.open(paths["lossyear"]) as loss, rasterio.open(paths["datamask"]) as mask:
        west, north = cover.transform.c, cover.transform.f
        rows_cells, cols_cells = cover.height // PIXELS_PER_CELL, cover.width // PIXELS_PER_CELL
        land = np.zeros((rows_cells, cols_cells), np.int64)
        forest = np.zeros_like(land)
        edges = np.zeros_like(land)
        loss_by_year = np.zeros((rows_cells, cols_cells, len(LOSS_YEARS) + 1), np.int64)
        for row in range(0, cover.height, BAND_ROWS):
            window = Window(0, row, cover.width, BAND_ROWS)
            data_mask = mask.read(1, window=window)
            if not data_mask.any():
                continue
            is_land = data_mask == 1
            is_forest = is_land & (cover.read(1, window=window) >= FOREST_THRESHOLD)
            lost = np.where(is_forest, loss.read(1, window=window), 0)
            cell_rows = slice(row // PIXELS_PER_CELL, (row + BAND_ROWS) // PIXELS_PER_CELL)
            land[cell_rows] = block_sum(is_land)
            forest[cell_rows] = block_sum(is_forest)
            edges[cell_rows] = block_sum(forest_edges(is_forest))
            pixel_rows, pixel_cols = np.nonzero(lost)
            if len(pixel_rows):
                cell_index = (pixel_rows // PIXELS_PER_CELL) * cols_cells + pixel_cols // PIXELS_PER_CELL
                counts = np.bincount(cell_index * (len(LOSS_YEARS) + 1) + lost[pixel_rows, pixel_cols],
                                     minlength=(BAND_ROWS // PIXELS_PER_CELL) * cols_cells * (len(LOSS_YEARS) + 1))
                loss_by_year[cell_rows] = counts.reshape(BAND_ROWS // PIXELS_PER_CELL, cols_cells, len(LOSS_YEARS) + 1)
    ix0 = round(west * CELLS_PER_DEGREE)
    iy_top = round(north * CELLS_PER_DEGREE) - 1
    return {"ix0": ix0, "iy_top": iy_top, "land": land, "forest": forest, "edges": edges, "loss": loss_by_year[:, :, 1:]}


def ghsl_sum(zip_path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Sum a GHSL 30 arc-second raster into 0.05-degree cells over India's bounding box."""
    member = next(name for name in zipfile.ZipFile(zip_path).namelist() if name.endswith(".tif"))
    with rasterio.open(f"/vsizip/{zip_path.as_posix()}/{member}") as source:
        window = from_bounds(*INDIA_BOUNDS, transform=source.transform).round_offsets().round_lengths()
        values = source.read(1, window=window, masked=True).filled(0).astype("float64")
        values[values < 0] = 0
        transform = source.window_transform(window)
    rows, cols = np.indices(values.shape)
    lon = transform.c + (cols + 0.5) * transform.a
    lat = transform.f + (rows + 0.5) * transform.e
    ix = np.floor(lon * CELLS_PER_DEGREE).astype(np.int64)
    iy = np.floor(lat * CELLS_PER_DEGREE).astype(np.int64)
    keys = ix * 100_000 + iy
    unique, inverse = np.unique(keys.ravel(), return_inverse=True)
    sums = np.bincount(inverse, weights=values.ravel())
    return unique // 100_000, unique % 100_000, sums


def build_cells() -> dict[str, np.ndarray]:
    columns: dict[str, list[np.ndarray]] = {name: [] for name in ("ix", "iy", "land_km2", "forest_km2", "edge_share", "loss_km2")}
    for tile in TILES:
        started = time.time()
        counts = hansen_tile(tile)
        rows, cols = np.nonzero(counts["land"])
        iy = counts["iy_top"] - rows
        area = cell_area_km2(iy)
        pixels = PIXELS_PER_CELL ** 2
        forest = counts["forest"][rows, cols]
        columns["ix"].append(counts["ix0"] + cols)
        columns["iy"].append(iy)
        columns["land_km2"].append(area * counts["land"][rows, cols] / pixels)
        columns["forest_km2"].append(area * forest / pixels)
        columns["edge_share"].append(np.where(forest > 0, counts["edges"][rows, cols] / np.maximum(forest, 1), np.nan))
        columns["loss_km2"].append(area[:, None] * counts["loss"][rows, cols] / pixels)
        print(f"  {tile}: {len(rows):,} land cells ({time.time() - started:.0f}s)", flush=True)
    cells = {name: np.concatenate(parts) for name, parts in columns.items()}

    index = {(int(x), int(y)): position for position, (x, y) in enumerate(zip(cells["ix"], cells["iy"]))}
    for name, file in (("built_km2", "built.zip"), ("population", "pop.zip")):
        ix, iy, sums = ghsl_sum(RAW / "ghsl" / file)
        column = np.zeros(len(cells["ix"]))
        for x, y, value in zip(ix.tolist(), iy.tolist(), sums.tolist()):
            position = index.get((x, y))
            if position is not None:
                column[position] = value / 1e6 if name == "built_km2" else value
        cells[name] = column
        print(f"  GHSL {name} summed", flush=True)
    return cells


LOAD_SQL = """
CREATE TEMP TABLE land_use_staging (ix INT, iy INT, land_km2 FLOAT8, forest_2000_km2 FLOAT8, forest_loss_km2 FLOAT8,
                                    forest_loss_km2_by_year FLOAT8[], forest_edge_share FLOAT8, built_up_km2 FLOAT8, population FLOAT8)
"""
INSERT_SQL = """
INSERT INTO land_use_cells (ix, iy, geom, land_km2, forest_2000_km2, forest_loss_km2, forest_loss_km2_by_year,
                            forest_edge_share, built_up_km2, population)
SELECT ix, iy, ST_MakeEnvelope(ix / 20.0, iy / 20.0, (ix + 1) / 20.0, (iy + 1) / 20.0, 4326), land_km2, forest_2000_km2,
       forest_loss_km2, forest_loss_km2_by_year, forest_edge_share, built_up_km2, population
FROM land_use_staging
"""

STATE_SQL = [
    ("centroid", """UPDATE land_use_cells AS c SET state = s.state FROM reference_states_sub AS s
                    WHERE ST_Contains(s.geom, ST_Centroid(c.geom))"""),
    ("boundary", """UPDATE land_use_cells AS c SET state = (
                        SELECT s.state FROM reference_states_sub AS s WHERE ST_Intersects(s.geom, c.geom)
                        ORDER BY ST_Area(ST_Intersection(s.geom, c.geom)) DESC LIMIT 1)
                    WHERE c.state IS NULL AND EXISTS (SELECT 1 FROM reference_states_sub AS s WHERE ST_Intersects(s.geom, c.geom))"""),
    ("outside_india", "DELETE FROM land_use_cells WHERE state IS NULL"),
]

SPECIES_SQL = """
INSERT INTO species_land_pressure
WITH occupied AS (
    SELECT o.species_id, COUNT(*) AS records, floor(o.longitude * 20)::int AS ix, floor(o.latitude * 20)::int AS iy
    FROM occurrences AS o WHERE o.coordinate_uncertainty_class = ANY(%(eligible)s)
    GROUP BY 1, 3, 4
), joined AS (
    SELECT o.species_id, o.records, c.*,
           (SELECT SUM(v) FROM unnest(c.forest_loss_km2_by_year[%(recent_index)s:]) AS v) AS recent_loss_km2
    FROM occupied AS o JOIN land_use_cells AS c ON c.ix = o.ix AND c.iy = o.iy
), left_out AS (
    SELECT species_id, jsonb_object_agg(certainty, n) AS counts FROM (
        SELECT species_id, COALESCE(coordinate_uncertainty_class, 'unknown') AS certainty, COUNT(*) AS n
        FROM occurrences WHERE coordinate_uncertainty_class IS NULL OR NOT (coordinate_uncertainty_class = ANY(%(eligible)s))
        GROUP BY 1, 2) AS t GROUP BY species_id
)
SELECT j.species_id, SUM(j.records)::int, COUNT(*)::int, COALESCE(MAX(l.counts::text)::jsonb, '{}'::jsonb),
       AVG(j.forest_2000_km2 / NULLIF(j.land_km2, 0)),
       SUM(j.forest_loss_km2) / NULLIF(SUM(j.forest_2000_km2), 0),
       SUM(j.recent_loss_km2) / NULLIF(SUM(j.forest_2000_km2), 0),
       AVG((j.forest_loss_km2 > 0.01 * j.forest_2000_km2 AND j.forest_2000_km2 > 0)::int),
       AVG(j.forest_edge_share),
       AVG(j.built_up_km2 / NULLIF(j.land_km2, 0)),
       AVG(j.population / NULLIF(j.land_km2, 0))
FROM joined AS j LEFT JOIN left_out AS l ON l.species_id = j.species_id
GROUP BY j.species_id
"""

GRID_SQL = """
UPDATE analytics_grid_cells AS g SET
    forest_2000_pct = round((100 * a.forest / NULLIF(a.land, 0))::numeric, 2)::float,
    forest_loss_pct = round((100 * a.loss / NULLIF(a.forest, 0))::numeric, 2)::float,
    recent_forest_loss_pct = round((100 * a.recent / NULLIF(a.forest, 0))::numeric, 2)::float,
    forest_edge_share = round(a.edge::numeric, 3)::float,
    built_up_pct = round((100 * a.built / NULLIF(a.land, 0))::numeric, 2)::float,
    population_density_per_km2 = round((a.population / NULLIF(a.land, 0))::numeric, 1)::float
FROM (
    SELECT g2.cell_id, SUM(c.land_km2) AS land, SUM(c.forest_2000_km2) AS forest, SUM(c.forest_loss_km2) AS loss,
           SUM((SELECT SUM(v) FROM unnest(c.forest_loss_km2_by_year[%(recent_index)s:]) AS v)) AS recent,
           SUM(c.forest_edge_share * c.forest_2000_km2) / NULLIF(SUM(c.forest_2000_km2) FILTER (WHERE c.forest_edge_share IS NOT NULL), 0) AS edge,
           SUM(c.built_up_km2) AS built, SUM(c.population) AS population
    FROM analytics_grid_cells AS g2 JOIN land_use_cells AS c ON ST_Contains(g2.geom, ST_Centroid(c.geom))
    GROUP BY g2.cell_id
) AS a WHERE a.cell_id = g.cell_id
"""


def update_grid_cells(connection: psycopg.Connection) -> None:
    """Also called by phase13_build_grid_metrics.py after it rebuilds the grid."""
    connection.execute(GRID_SQL, {"recent_index": RECENT_FROM - LOSS_YEARS[0] + 1})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-rasters", action="store_true", help=f"Reuse {CELLS_FILE.name} instead of re-reading the rasters.")
    args = parser.parse_args()
    started = time.time()
    if args.skip_rasters and CELLS_FILE.exists():
        cells = dict(np.load(CELLS_FILE))
    else:
        print("Aggregating Hansen tiles to 0.05-degree cells", flush=True)
        cells = build_cells()
        CELLS_FILE.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(CELLS_FILE, **cells)

    ensure_schema(DATABASE_URL)
    step = 1 / CELLS_PER_DEGREE
    rows = [
        (int(x), int(y), float(land), float(forest), float(loss.sum()), [round(float(v), 5) for v in loss],
         None if np.isnan(edge) else round(float(edge), 4), float(built), float(pop))
        for x, y, land, forest, loss, edge, built, pop in zip(cells["ix"], cells["iy"], cells["land_km2"], cells["forest_km2"],
                                                              cells["loss_km2"], cells["edge_share"], cells["built_km2"], cells["population"])
        if INDIA_BOUNDS[0] <= x * step < INDIA_BOUNDS[2] and INDIA_BOUNDS[1] <= y * step < INDIA_BOUNDS[3]
    ]
    timings = {}
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("TRUNCATE species_land_pressure, land_use_cells")
        connection.execute(LOAD_SQL)
        with connection.cursor().copy("COPY land_use_staging FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)
        connection.execute(INSERT_SQL)
        connection.execute("ANALYZE land_use_cells")
        for name, sql in STATE_SQL:
            step_started = time.time()
            connection.execute(sql)
            timings[name] = round(time.time() - step_started)
            print(f"  state attribution: {name} ({timings[name]}s)", flush=True)
        connection.execute(SPECIES_SQL, {"eligible": ELIGIBLE_UNCERTAINTY_CLASSES, "recent_index": RECENT_FROM - LOSS_YEARS[0] + 1})
        update_grid_cells(connection)
        summary = connection.execute(
            """SELECT COUNT(*), SUM(land_km2), SUM(forest_2000_km2), SUM(forest_loss_km2), SUM(built_up_km2), SUM(population),
                      (SELECT COUNT(*) FROM species_land_pressure), (SELECT COUNT(*) FROM analytics_grid_cells WHERE forest_2000_pct IS NOT NULL)
               FROM land_use_cells""").fetchone()

    report = {
        "cells": summary[0], "land_km2": round(summary[1]), "forest_2000_km2": round(summary[2]), "forest_loss_2001_2024_km2": round(summary[3]),
        "built_up_km2": round(summary[4]), "population": round(summary[5]), "species_profiles": summary[6], "analytics_cells_updated": summary[7],
        "sources": {
            "forest": f"Hansen et al. (2013) Global Forest Change {HANSEN_VERSION}, https://glad.earthengine.app/view/global-forest-change, CC BY 4.0",
            "built_up_and_population": "GHSL R2023A GHS-BUILT-S and GHS-POP, epoch 2020, 30 arc-seconds (European Commission JRC), CC BY 4.0",
        },
        "method": {
            "cell_size_degrees": step, "forest_definition": f"tree canopy cover >= {FOREST_THRESHOLD}% in 2000",
            "loss": "pixels whose loss year is set, counted only inside year-2000 forest; gain is not included",
            "fragmentation": "forest_edge_share = share of year-2000 forest pixels (30 m) with a non-forest 4-neighbour",
            "state_attribution": "cell centroid in a state, else the state with the largest overlap; cells outside India are dropped",
        },
        "state_attribution_seconds": timings, "runtime_seconds": round(time.time() - started),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
