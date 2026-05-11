from pathlib import Path

import pytest

import gldemtools2.processing

TEST_DATA_DIR = Path(__file__).parent / "data"
SAMPLE_CONFIG_PATH = TEST_DATA_DIR / "config.toml"
SAMPLE_STRIP_LIST_PATH = TEST_DATA_DIR / "strip-list.txt"

@pytest.fixture()
def output_filename(tmp_path):
    filename = Path(tmp_path / "output.tif")
    return filename

@pytest.fixture()
def config():
    return gldemtools2.processing.Config(SAMPLE_CONFIG_PATH)

@pytest.fixture()
def tile(config):
    return gldemtools2.processing.Tile(config, 42, 1337)

@pytest.fixture()
def strip_collection(config):
    return gldemtools2.processing.StripCollection(config)

@pytest.fixture()
def strip_list(config):
    with open(SAMPLE_STRIP_LIST_PATH) as strip_list_file:
        relative_paths = [Path(line.strip()) for line in strip_list_file]
    return relative_paths
