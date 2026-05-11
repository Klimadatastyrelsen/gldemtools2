from pathlib import Path

import numpy as np

import gldemtools2.processing

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

    marzullo_result = gldemtools2.processing.MarzulloResult(input_strip_data, 0.1)

    assert marzullo_result.data.dtype == np.float32
    np.testing.assert_array_almost_equal(marzullo_result.data, expected_result)
    np.testing.assert_array_equal(marzullo_result.max_overlap_count, expected_overlaps)

def test_strip_list(strip_list, strip_collection):
    strip_abs_paths = strip_collection.get_listed_strips(strip_list)

    assert strip_abs_paths == [
        Path('/foo/bar/strips/2m/n60w046/SETSM_s2s041_WV02_20170925_10300100728F1E00_1030010071915C00_2m_lsf_seg1.tar.gz'),
        Path('/foo/bar/strips/2m/n60w046/SETSM_s2s041_WV03_20170925_1040010033A09E00_1040010033858F00_2m_lsf_seg1.tar.gz'),
        Path('/foo/bar/strips/2m/n60w046/SETSM_s2s041_WV02_20200225_10300100A3A86000_10300100A2664800_2m_lsf_seg1.tar.gz'),
    ]
