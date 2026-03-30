from pathlib import Path

import pytest

import gldemtools2

TEST_DATA_DIR = Path(__file__).parent / "data"
SAMPLE_CONFIG_PATH = TEST_DATA_DIR / "config.toml"

@pytest.fixture()
def output_filename(tmp_path):
    filename = Path(tmp_path / "output.tif")
    return filename

@pytest.fixture()
def config():
    return gldemtools2.cli.Config(SAMPLE_CONFIG_PATH)

@pytest.fixture()
def tile(config):
    return gldemtools2.cli.Tile(config, 42, 1337)
