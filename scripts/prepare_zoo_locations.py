"""Extract zoos and captive-animal facilities in India from the OSM extract, for the captive-record filter.

Output: data/raw/protected_areas/osm/osm_zoos.gpkg (polygons; point-only zoos are buffered)
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio


ROOT = Path(__file__).resolve().parents[1]
PBF = ROOT / "data" / "raw" / "protected_areas" / "osm" / "india-latest.osm.pbf"
OUTPUT = ROOT / "data" / "raw" / "protected_areas" / "osm" / "osm_zoos.gpkg"
POINT_ZOO_RADIUS_M = 500


def main() -> None:
    polygons = pyogrio.read_dataframe(PBF, layer="multipolygons", columns=["osm_id", "osm_way_id", "name"], where="tourism = 'zoo'")
    points = pyogrio.read_dataframe(PBF, layer="points", columns=["osm_id", "name", "other_tags"], where="other_tags LIKE '%\"tourism\"=>\"zoo\"%'")
    points = points.to_crs("EPSG:6933")
    points["geometry"] = points.geometry.buffer(POINT_ZOO_RADIUS_M)
    points = points.to_crs(polygons.crs)
    polygons["source_geometry"] = "osm_polygon"
    points["source_geometry"] = f"osm_point_buffered_{POINT_ZOO_RADIUS_M}m"
    polygons["osm_id"] = polygons["osm_id"].fillna(polygons["osm_way_id"])
    zoos = gpd.GeoDataFrame(
        pd.concat([polygons[["osm_id", "name", "source_geometry", "geometry"]], points[["osm_id", "name", "source_geometry", "geometry"]]], ignore_index=True),
        crs=polygons.crs,
    )
    zoos.to_file(OUTPUT, driver="GPKG", layer="zoos")
    print(f"Wrote {OUTPUT}: {len(polygons)} zoo outlines, {len(points)} point-only zoos")


if __name__ == "__main__":
    main()
