from pathlib import Path

import gldemtools2.cli
from . import conftest

def test_env():
    pass

def test_cli_help():
    try:
        _parsed_args = gldemtools2.cli.parse_args(['-h'])
        raise RuntimeError("didn't exit when called with '-h' argument")
    except SystemExit:
        # expected behavior
        pass

def test_load_conf():
    with open(conftest.SAMPLE_CONFIG_PATH, 'rb') as config_file:
        config = gldemtools2.cli.Config(config_file)
        assert isinstance(config.strip_index_path, Path)
        assert isinstance(config.strip_basepath, Path)
        assert isinstance(config.x_offset, float)
        assert isinstance(config.y_offset, float)
        assert isinstance(config.x_interval, float)
        assert isinstance(config.y_interval, float)
