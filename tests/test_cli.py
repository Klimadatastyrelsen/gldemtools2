import subprocess

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

@pytest.mark.skip(reason='needs valid strip data to succeed')
def test_main(output_filename):
    subprocess.run(['process_tile', conftest.SAMPLE_CONFIG_PATH, '42', '1337', output_filename], check=True)
