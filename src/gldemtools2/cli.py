import argparse
from pathlib import Path
import sys
import tomllib

from osgeo import gdal

gdal.UseExceptions()

MEM_DRIVER = gdal.GetDriverByName('MEM')
ARCTICDEM_X_GSD = 2.0
ARCTICDEM_Y_GSD = 2.0
NODATA_VALUE = -9999

class Config:
    def __init__(self, path) -> None:
        with open(path, 'rb') as file:
            config_dict = tomllib.load(file)
            self.strip_index_path = Path(config_dict['input']['strip_index_path'])
            self.strip_basepath = Path(config_dict['input']['strip_basepath'])
            self.x_offset = float(config_dict['tiling']['x_offset'])
            self.y_offset = float(config_dict['tiling']['y_offset'])
            self.x_interval = float(config_dict['tiling']['x_interval'])
            self.y_interval = float(config_dict['tiling']['y_interval'])
            self.tile_cols = int(self.x_interval / ARCTICDEM_X_GSD)
            self.tile_rows = int(self.y_interval / ARCTICDEM_Y_GSD)

class Tile:
    def __init__(self, config, row: int, col: int) -> None:
        self.config = config
        self.row = row
        self.col = col

    def get_geotransform(self) -> list[float]:
        geotransform = [
            self.config.x_offset + self.col * self.config.x_interval, ARCTICDEM_X_GSD, 0.0,
            self.config.y_offset + (self.row+1) * self.config.y_interval, 0.0, -ARCTICDEM_Y_GSD,
        ]
        return geotransform

    def translate_strip(self, strip_dataset) -> gdal.Dataset:
        output_dataset = MEM_DRIVER.Create('', self.config.tile_cols, self.config.tile_rows, 1, gdal.GDT_Float32)
        output_dataset.SetGeoTransform(self.get_geotransform())
        output_band = output_dataset.GetRasterBand(1)
        output_band.SetNoDataValue(NODATA_VALUE)
        output_band.Fill(NODATA_VALUE) # otherwise, the areas corresponding to input NODATA will be 0

        # (minX, minY, maxX, maxY)
        output_bounds = (
            self.config.x_offset + self.col * self.config.x_interval,
            self.config.y_offset + self.row * self.config.y_interval,
            self.config.x_offset + (self.col + 1) * self.config.x_interval,
            self.config.y_offset + (self.row + 1) * self.config.y_interval,
        )
        # gdal.Translate() needs a named output, so we use gdal.Warp() instead
        warp_options = gdal.WarpOptions(
            outputBounds=output_bounds,
            dstNodata=NODATA_VALUE,
        )
        gdal.Warp(
            output_dataset,
            strip_dataset,
            options=warp_options,
        )
        return output_dataset

def parse_args(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('config', type=str)
    parser.add_argument('row', type=int)
    parser.add_argument('col', type=int)
    parser.add_argument('out_path', type=str)
    parsed_args = parser.parse_args(args)
    return parsed_args

def main():
    input_args = parse_args(sys.argv[1:])
    _config = Config(input_args.config)
