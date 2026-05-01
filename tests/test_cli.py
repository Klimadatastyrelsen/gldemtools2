from pathlib import Path
import subprocess

import numpy as np
import pytest

import gldemtools2.cli
from . import conftest

def test_help():
    try:
        _parsed_args = gldemtools2.cli.parse_args(['-h'])
        raise RuntimeError("didn't exit when called with '-h' argument")
    except SystemExit:
        # expected behavior
        pass

def test_load_conf(config):
    assert isinstance(config.strip_index_path, Path)
    assert isinstance(config.strip_path_fieldname, str)
    assert isinstance(config.strip_basepath, Path)
    assert isinstance(config.x_offset, float)
    assert isinstance(config.y_offset, float)
    assert isinstance(config.x_interval, float)
    assert isinstance(config.y_interval, float)
    assert isinstance(config.tile_cols, int)
    assert isinstance(config.tile_rows, int)

@pytest.mark.skip(reason='needs valid strip data to succeed')
def test_main(output_filename):
    subprocess.run(['process_tile', conftest.SAMPLE_CONFIG_PATH, '42', '1337', output_filename], check=True)

def test_tile_geotransform(tile):
    expected_tile_geotransform = [13370000.0, 2.0, 0.0,
                                  430000.0, 0.0, -2.0]
    actual_tile_geotransform = tile.get_geotransform()
    assert expected_tile_geotransform == actual_tile_geotransform

def test_marzullo():
    input_strip_data = np.array([
        [
            [0.5, 0.5, np.nan,],
            [0.5, 0.5, np.nan,]
        ],
        [
            [0.5, 0.45, 0.45,],
            [0.25, 0.75, np.nan,],
        ],
        [
            [0.5, 0.55, 0.55],
            [0.75, 0.5, np.nan,],
        ],
    ], dtype=np.float32)

    expected_result = np.array([
        [0.5, 0.5, 0.5,],
        [0.25, 0.5, np.nan,],
    ], dtype=np.float32)
    expected_overlaps = np.array([
        [3, 3, 2,],
        [1, 2, 0,],
    ])

    marzullo_result = gldemtools2.cli.MarzulloResult(input_strip_data, 0.1)

    assert marzullo_result.data.dtype == np.float32
    np.testing.assert_array_almost_equal(marzullo_result.data, expected_result)
    np.testing.assert_array_equal(marzullo_result.max_overlap_count, expected_overlaps)
