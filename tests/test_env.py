from osgeo import gdal
import numpy as np

import gldemtools2.cli

def test_env():
    pass

def test_cli_help():
    try:
        parsed_args = gldemtools2.cli.parse_args(['-h'])
        raise RuntimeError("didn't exit when called with '-h' argument")
    except SystemExit:
        # expected behavior
        pass
