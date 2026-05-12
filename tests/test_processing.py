from pathlib import Path

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

def test_strip_list(strip_list, strip_collection):
    strip_abs_paths = strip_collection.get_listed_strips(strip_list)

    assert strip_abs_paths == [
        Path('/foo/bar/strips/2m/n60w046/SETSM_s2s041_WV02_20170925_10300100728F1E00_1030010071915C00_2m_lsf_seg1.tar.gz'),
        Path('/foo/bar/strips/2m/n60w046/SETSM_s2s041_WV03_20170925_1040010033A09E00_1040010033858F00_2m_lsf_seg1.tar.gz'),
        Path('/foo/bar/strips/2m/n60w046/SETSM_s2s041_WV02_20200225_10300100A3A86000_10300100A2664800_2m_lsf_seg1.tar.gz'),
    ]
