import argparse
from collections import OrderedDict
from enum import IntFlag
import logging
from pathlib import Path
import sys
import tomllib

import numpy as np
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

COG_DRIVER = gdal.GetDriverByName('COG')
MEM_DRIVER = gdal.GetDriverByName('MEM')

ARCTICDEM_X_GSD = 2.0
ARCTICDEM_Y_GSD = 2.0
ARCTICDEM_SRS = osr.SpatialReference()
ARCTICDEM_SRS.ImportFromEPSG(3413)

# Documented under "Bitmask Format", https://www.pgc.umn.edu/guides/stereo-derived-elevation-models/pgc-dem-products-arcticdem-rema-and-earthdem/#section-7
class ArcticDemBitmask(IntFlag):
    GOOD_DATA = 0
    BAD_EDGE_DATA = 1
    WATER = 2
    WATER_AND_EDGE = 3
    CLOUD = 4
    CLOUD_AND_EDGE = 5
    CLOUD_AND_WATER = 6
    CLOUD_AND_WATER_AND_EDGE = 7

OUTPUT_NODATA_VALUE = -9999

class Config:
    def __init__(self, path: Path) -> None:
        with open(path, 'rb') as file:
            config_dict = tomllib.load(file)
            logging.info(f'Loaded configuration file {path}')
            self.strip_index_path = Path(config_dict['strips']['index_path'])
            self.strip_path_fieldname = str(config_dict['strips']['path_fieldname'])
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

    def process_strip_data(self, strip_paths: list[Path], output_path: Path):
        tile_dem_data = np.full((len(strip_paths), self.config.tile_rows, self.config.tile_cols), np.nan, dtype=np.float32)
        tile_bitmask_data = np.full((len(strip_paths), self.config.tile_rows, self.config.tile_cols), ArcticDemBitmask.BAD_EDGE_DATA, dtype=np.uint8)

        for (i, strip_path) in enumerate(strip_paths):
            logging.debug(f'Opening strip {strip_path}...')

            strip_name = str(strip_path.name)[:-7] # remove '.tar.gz' suffix
            # Can't use pathlib's joining with GDAL VFS paths
            strip_vfs_path = '/vsitar/' + str(strip_path)
            strip_dem_path = strip_vfs_path + f'/{strip_name}_dem.tif'
            strip_bitmask_path = strip_vfs_path + f'/{strip_name}_bitmask.tif'

            logging.debug(f'Opening strip DEM {strip_dem_path}...')
            strip_dem_dataset = gdal.Open(strip_dem_path, gdal.GA_ReadOnly)
            windowed_strip_dem_dataset = self.translate_strip(strip_dem_dataset)
            windowed_strip_dem_band = windowed_strip_dem_dataset.GetRasterBand(1)
            windowed_strip_dem_nodata_value = windowed_strip_dem_band.GetNoDataValue()
            windowed_strip_dem_dataarray = windowed_strip_dem_band.ReadAsArray()
            windowed_strip_dem_dataarray[windowed_strip_dem_dataarray == windowed_strip_dem_nodata_value] = np.nan
            strip_dem_dataset = None

            logging.debug(f'Opening strip bitmask {strip_bitmask_path}...')
            strip_bitmask_dataset = gdal.Open(strip_bitmask_path, gdal.GA_ReadOnly)
            windowed_strip_bitmask_dataset = self.translate_strip(strip_bitmask_dataset)
            windowed_strip_bitmask_band = windowed_strip_bitmask_dataset.GetRasterBand(1)
            # NODATA is 1 (BAD_EDGE_DATA) for the bitmask. Keep this as is
            _windowed_strip_bitmask_nodata_value = windowed_strip_bitmask_band.GetNoDataValue()
            windowed_strip_bitmask_dataarray = windowed_strip_bitmask_band.ReadAsArray()
            strip_bitmask_dataset = None

            tile_dem_data[i] = windowed_strip_dem_dataarray
            tile_bitmask_data[i] = windowed_strip_bitmask_dataarray

        # Filter out all data not considered "good data" by PGC
        tile_dem_data[tile_bitmask_data != ArcticDemBitmask.GOOD_DATA] = np.nan
        tile_mean_dem_array = np.nanmean(tile_dem_data, axis=0)
        tile_mean_dem_array[~np.isfinite(tile_mean_dem_array)] = OUTPUT_NODATA_VALUE

        logging.info(f'Writing output data to {output_path}...')
        output_dataset = MEM_DRIVER.Create('', self.config.tile_cols, self.config.tile_rows, 1, gdal.GDT_Float32)
        output_dataset.SetGeoTransform(self.get_geotransform())
        output_band = output_dataset.GetRasterBand(1)
        output_band.SetNoDataValue(OUTPUT_NODATA_VALUE)
        output_band.WriteArray(tile_mean_dem_array)
        COG_DRIVER.CreateCopy(output_path, output_dataset)

    def translate_strip(self, strip_dataset: gdal.Dataset) -> gdal.Dataset:
        strip_dataset_band = strip_dataset.GetRasterBand(1)
        strip_data_type = strip_dataset_band.DataType
        strip_nodata_value = strip_dataset_band.GetNoDataValue()

        logging.debug('Windowing strip dataset...')
        output_dataset = MEM_DRIVER.Create('', self.config.tile_cols, self.config.tile_rows, 1, strip_data_type)
        output_dataset.SetGeoTransform(self.get_geotransform())
        output_band = output_dataset.GetRasterBand(1)
        output_band.SetNoDataValue(strip_nodata_value)
        output_band.Fill(strip_nodata_value) # otherwise, the areas corresponding to input NODATA will be 0

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
            resampleAlg=gdal.GRA_NearestNeighbour, # especially relevant for the bitmask rasters
            dstNodata=strip_nodata_value,
        )
        # FIXME: throws "Warning 1: All options related to creation ignored in update mode"
        gdal.Warp(
            output_dataset,
            strip_dataset,
            options=warp_options,
        )
        return output_dataset

class StripCollection:
    def __init__(self, config: Config) -> None:
        self.index_path = config.strip_index_path
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
            strip_path = Path(strip_feature.GetFieldAsString(self.path_fieldname))
            intersecting_strip_paths.append(strip_path)

        index_datasrc = None

        logging.info(f'Found {len(intersecting_strip_paths)} intersecting strips')
        return intersecting_strip_paths

def parse_args(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('config', type=str, help='path to TOML config file')
    parser.add_argument('row', type=int, help='row number of requested tile')
    parser.add_argument('col', type=int, help='column number of requested tile')
    parser.add_argument('out_path', type=str, help='(UNSTABLE) desired path to output TIFF file')
    parser.add_argument('--log-level', type=str, choices=LOG_LEVELS.keys(), default='WARNING', help="logging level")
    parsed_args = parser.parse_args(args)
    return parsed_args

def main():
    input_args = parse_args(sys.argv[1:])
    logging.basicConfig(level=LOG_LEVELS[input_args.log_level])
    config = Config(input_args.config)
    strip_collection = StripCollection(config)
    tile = Tile(config=config, row=input_args.row, col=input_args.col)
    output_path = Path(input_args.out_path)

    intersecting_strip_paths = strip_collection.get_intersecting_strips(tile)
    tile.process_strip_data(intersecting_strip_paths, output_path)

    logging.info('Successfully processed tile')
