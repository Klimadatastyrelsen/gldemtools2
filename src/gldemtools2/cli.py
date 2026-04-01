import argparse
from collections import OrderedDict
import logging
from pathlib import Path
import sys
import tomllib

from osgeo import gdal, ogr, osr

gdal.UseExceptions()
ogr.UseExceptions()
osr.UseExceptions()

LOG_LEVELS = OrderedDict([
    ('DEBUG', logging.DEBUG),
    ('INFO', logging.INFO),
    ('WARNING', logging.WARNING),
    ('ERROR', logging.ERROR),
    ('CRITICAL', logging.CRITICAL)
])
MEM_DRIVER = gdal.GetDriverByName('MEM')
ARCTICDEM_X_GSD = 2.0
ARCTICDEM_Y_GSD = 2.0
ARCTICDEM_SRS = osr.SpatialReference()
ARCTICDEM_SRS.ImportFromEPSG(3413)
NODATA_VALUE = -9999

class Config:
    def __init__(self, path: Path) -> None:
        with open(path, 'rb') as file:
            config_dict = tomllib.load(file)
            logging.info(f'Loaded configuration file {path}')
            self.strip_index_path = Path(config_dict['strips']['index_path'])
            self.strip_path_fieldname = str(config_dict['strips']['path_fieldname'])
            self.strip_basepath = Path(config_dict['strips']['basepath'])
            self.x_offset = float(config_dict['tiling']['x_offset'])
            self.y_offset = float(config_dict['tiling']['y_offset'])
            self.x_interval = float(config_dict['tiling']['x_interval'])
            self.y_interval = float(config_dict['tiling']['y_interval'])
            self.tile_cols = int(self.x_interval / ARCTICDEM_X_GSD)
            self.tile_rows = int(self.y_interval / ARCTICDEM_Y_GSD)

class Tile:
    def __init__(self, config: Config, row: int, col: int) -> None:
        self.config = config
        self.row = row
        self.col = col
        logging.debug(f'Created Tile with row={row}, col={col}')

    def get_footprint_geometry(self) -> ogr.Geometry:
        x_min = self.config.x_offset + self.col * self.config.x_interval
        x_max = self.config.x_offset + (self.col + 1) * self.config.x_interval
        y_min = self.config.y_offset + self.row * self.config.y_interval
        y_max = self.config.y_offset + (self.row + 1) * self.config.y_interval

        ring = ogr.Geometry(ogr.wkbLinearRing)
        ring.AddPoint(x_min, y_min)
        ring.AddPoint(x_max, y_min)
        ring.AddPoint(x_max, y_max)
        ring.AddPoint(x_min, y_max)
        ring.AddPoint(x_min, y_min)

        geometry = ogr.Geometry(ogr.wkbPolygon)
        geometry.AddGeometry(ring)
        geometry.AssignSpatialReference(ARCTICDEM_SRS)

        return geometry

    def get_geotransform(self) -> list[float]:
        geotransform = [
            self.config.x_offset + self.col * self.config.x_interval, ARCTICDEM_X_GSD, 0.0,
            self.config.y_offset + (self.row+1) * self.config.y_interval, 0.0, -ARCTICDEM_Y_GSD,
        ]
        return geotransform

    def translate_strip(self, strip_dataset) -> gdal.Dataset:
        logging.info('Windowing strip dataset...')
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

class StripCollection:
    def __init__(self, config: Config) -> None:
        self.index_path = config.strip_index_path
        # self.basepath = config.strip_basepath
        self.path_fieldname = config.strip_path_fieldname

    def get_intersecting_strips(self, tile: Tile) -> list[Path]:
        logging.info('Finding strip intersections with tile...')
        intersecting_strip_paths = []
        tile_footprint = tile.get_footprint_geometry() # to be transformed to the index' SRS
        tile_footprint_wkt = tile_footprint.ExportToWkt()
        logging.debug(f'Tile footprint in working SRS is {tile_footprint_wkt}')

        index_datasrc = ogr.Open(self.index_path)
        index_srs = index_datasrc.GetSpatialRef()
        index_srs_name = index_srs.GetName()
        index_layer = index_datasrc.GetLayer()

        tile_footprint.TransformTo(index_srs)
        logging.debug(f'Strip index SRS is {index_srs_name}')
        index_layer.SetSpatialFilter(tile_footprint)
        spatial_filter_wkt = index_layer.GetSpatialFilter().ExportToWkt()
        logging.debug(f'Strip spatial filter (in strip index SRS) is {spatial_filter_wkt}')

        for strip_feature in index_layer:
            strip_fid = strip_feature.GetFID()
            logging.debug(f'Found strip intersection with FID {strip_fid}')
            strip_path = strip_feature.GetFieldAsString(self.path_fieldname)
            intersecting_strip_paths.append(strip_path)

        index_datasrc = None

        logging.info(f'Found {len(intersecting_strip_paths)} intersecting strips')
        return intersecting_strip_paths

def parse_args(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('config', type=str)
    parser.add_argument('row', type=int)
    parser.add_argument('col', type=int)
    parser.add_argument('out_path', type=str)
    parser.add_argument('--log-level', type=str, choices=LOG_LEVELS.keys(), default='WARNING', help="logging level")
    parsed_args = parser.parse_args(args)
    return parsed_args

def main():
    input_args = parse_args(sys.argv[1:])
    logging.basicConfig(level=LOG_LEVELS[input_args.log_level])
    config = Config(input_args.config)
    strip_collection = StripCollection(config)
    tile = Tile(config=config, row=input_args.row, col=input_args.col)

    _intersecting_strips = strip_collection.get_intersecting_strips(tile)
