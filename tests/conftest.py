from pathlib import Path

import pytest

TEST_DATA_DIR = Path(__file__).parent / "data"
SAMPLE_CONFIG_PATH = TEST_DATA_DIR / "config.toml"

@pytest.fixture()
def output_filename(tmp_path):
    filename = Path(tmp_path / "output.tif")
    return filename
