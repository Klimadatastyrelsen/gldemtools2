from pathlib import Path
import subprocess

import gldemtools2.cli
from . import conftest

def test_help():
    try:
        _parsed_args = gldemtools2.cli.parse_args(['-h'])
        raise RuntimeError("didn't exit when called with '-h' argument")
    except SystemExit:
        # expected behavior
        pass

def test_load_conf():
    config = gldemtools2.cli.Config(conftest.SAMPLE_CONFIG_PATH)
    assert isinstance(config.strip_index_path, Path)
    assert isinstance(config.strip_basepath, Path)
    assert isinstance(config.x_offset, float)
    assert isinstance(config.y_offset, float)
    assert isinstance(config.x_interval, float)
    assert isinstance(config.y_interval, float)

def test_main(output_filename):
    subprocess.run(['process_tile', conftest.SAMPLE_CONFIG_PATH, '42', '1337', output_filename], check=True)

def test_tile_geotransform():
    config = gldemtools2.cli.Config(conftest.SAMPLE_CONFIG_PATH)
    tile = gldemtools2.cli.Tile(config, 42, 1337)
    expected_tile_geotransform = [13370000.0, 2.0, 0.0,
                                  430000.0, 0.0, -2.0]
    actual_tile_geotransform = tile.get_geotransform()
    assert expected_tile_geotransform == actual_tile_geotransform
