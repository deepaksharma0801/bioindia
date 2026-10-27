import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase10_build_land_use_grid import PIXELS_PER_CELL, block_sum, cell_area_km2, forest_edges


class LandUseGridTests(unittest.TestCase):
    def test_block_sum_counts_pixels_per_cell(self) -> None:
        pixels = np.zeros((PIXELS_PER_CELL, 2 * PIXELS_PER_CELL), dtype=bool)
        pixels[:10, :5] = True
        pixels[0, PIXELS_PER_CELL:] = True

        self.assertEqual(block_sum(pixels).tolist(), [[50, PIXELS_PER_CELL]])

    def test_forest_edges_marks_only_boundary_pixels(self) -> None:
        forest = np.zeros((7, 7), dtype=bool)
        forest[1:6, 1:6] = True
        edges = forest_edges(forest)

        self.assertEqual(int(edges.sum()), 16)  # the ring of a 5 x 5 block
        self.assertFalse(edges[3, 3])
        self.assertFalse(edges[0, 0])  # non-forest is never an edge

    def test_solid_forest_has_no_edges(self) -> None:
        self.assertEqual(int(forest_edges(np.ones((5, 5), dtype=bool)).sum()), 0)

    def test_cell_area_shrinks_towards_the_pole(self) -> None:
        equator, north = cell_area_km2(np.array([0, 700]))  # 0 and 35 degrees north

        self.assertAlmostEqual(equator, 30.9, delta=0.2)  # 0.05 x 0.05 degrees at the equator
        self.assertAlmostEqual(north / equator, np.cos(np.radians(35.025)), delta=0.01)


if __name__ == "__main__":
    unittest.main()
