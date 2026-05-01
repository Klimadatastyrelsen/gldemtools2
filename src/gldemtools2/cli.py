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
ARCTICDEM_SRS = osr.SpatialReference(epsg=3413)

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
            self.strip_basepath = Path(config_dict['strips']['basepath'])
            self.x_offset = float(config_dict['tiling']['x_offset'])
            self.y_offset = float(config_dict['tiling']['y_offset'])
            self.x_interval = float(config_dict['tiling']['x_interval'])
            self.y_interval = float(config_dict['tiling']['y_interval'])
            self.tile_cols = int(self.x_interval / ARCTICDEM_X_GSD)
            self.tile_rows = int(self.y_interval / ARCTICDEM_Y_GSD)

class MarzulloResult:
    def __init__(self, strip_data: np.ndarray, ci_halfwidth: float) -> None:
        logging.debug("Applying Marzullo's algorithm...")

        # Lower and upper bounds of the confidence intervals of the assumed uniform distribution
        ci_lower = strip_data - ci_halfwidth
        ci_upper = strip_data + ci_halfwidth
        ci_combined_bounds = np.concatenate([ci_lower, ci_upper])

        # +/- 1 values corresponding to the lower and upper bounds, respectively, of the confidence intervals
        plus_ones = np.ones_like(strip_data, dtype=np.int32)
        plus_ones[~np.isfinite(strip_data)] = 0 # don't let NODATA contribute
        minus_ones = -plus_ones
        ci_signs = np.concatenate([plus_ones, minus_ones])

        # Get the indices that would sort the combined lower/upper bounds
        sorting_args = np.argsort(ci_combined_bounds, axis=0)

        # Apply that sorting order to the combined lower/upper bounds and to the +/- 1 values
        ci_sorted_bounds = np.take_along_axis(ci_combined_bounds, sorting_args, axis=0)
        sorted_signs = np.take_along_axis(ci_signs, sorting_args, axis=0)

        # Get the number of overlapping confidence intervals at each bound
        overlap_counts = np.cumsum(sorted_signs, axis=0)

        # Get the maximum number of overlapping confidence intervals for each pixel
        overlap_max_val = np.max(overlap_counts, axis=0)

        # Get the indices of the lower and upper bounds of the highest-overlap interval in the sorted confidence interval bounds.
        overlap_max_lower_indices = np.argmax(overlap_counts, axis=0)
        overlap_max_upper_indices = overlap_max_lower_indices + 1

        overlap_max_lower = np.take_along_axis(ci_sorted_bounds, overlap_max_lower_indices[np.newaxis, :, :], axis=0)[0]
        overlap_max_upper = np.take_along_axis(ci_sorted_bounds, overlap_max_upper_indices[np.newaxis, :, :], axis=0)[0]
        overlap_max_middle = 0.5 * (overlap_max_lower + overlap_max_upper)

        self.data = overlap_max_middle
        self.max_overlap_count = overlap_max_val

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

    def process_strip_data(self, strip_paths: list[Path], output_dir: Path, allow_strip_errors: bool = False) -> int:
        error_strip_count = 0

        tile_dem_data = np.full((len(strip_paths), self.config.tile_rows, self.config.tile_cols), np.nan, dtype=np.float32)
        tile_bitmask_data = np.full((len(strip_paths), self.config.tile_rows, self.config.tile_cols), ArcticDemBitmask.BAD_EDGE_DATA, dtype=np.uint8)

        logging.info('Extracting strip data...')
        for (i, strip_path) in enumerate(strip_paths):
            logging.debug(f'Opening strip {strip_path} ({i+1} of {len(strip_paths)})...')

            strip_name = str(strip_path.name)[:-7] # remove '.tar.gz' suffix
            # Can't use pathlib's joining with GDAL VFS paths
            strip_vfs_path = '/vsitar/' + str(strip_path)
            strip_dem_path = strip_vfs_path + f'/{strip_name}_dem.tif'
            strip_bitmask_path = strip_vfs_path + f'/{strip_name}_bitmask.tif'

            try:
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
            except RuntimeError as e:
                if allow_strip_errors:
                    # likely corrupt/missing strip file, replace with NODATA-ish arrays
                    logging.error(f'Encountered RuntimeError, skipping strip: {e}')
                    windowed_strip_dem_dataarray = np.full((self.config.tile_rows, self.config.tile_cols), np.nan)
                    windowed_strip_bitmask_dataarray = np.ones((self.config.tile_rows, self.config.tile_cols), dtype=np.uint8)
                    error_strip_count += 1
                else:
                    raise e

            tile_dem_data[i] = windowed_strip_dem_dataarray
            tile_bitmask_data[i] = windowed_strip_bitmask_dataarray

        logging.info('Processing extracted data...')
        # Filter out all data not considered "good data" by PGC
        tile_dem_good_data = tile_dem_data.copy()
        tile_dem_good_data[tile_bitmask_data != ArcticDemBitmask.GOOD_DATA] = np.nan

        # Compute mean of good data
        tile_mean_dem_array = np.nanmean(tile_dem_good_data, axis=0)
        tile_mean_dem_array[~np.isfinite(tile_mean_dem_array)] = OUTPUT_NODATA_VALUE

        # Compute median of good data
        tile_median_dem_array = np.nanmedian(tile_dem_good_data, axis=0)
        tile_median_dem_array[~np.isfinite(tile_median_dem_array)] = OUTPUT_NODATA_VALUE

        # Compute median absolute deviation from median (MAD) of good data
        tile_median_deviation_array = np.abs(tile_dem_good_data - tile_median_dem_array)
        tile_mad_dem_array = np.nanmedian(tile_median_deviation_array, axis=0)
        tile_mad_dem_array[~np.isfinite(tile_mad_dem_array)] = OUTPUT_NODATA_VALUE

        # Compute minimum of good data
        tile_min_dem_array = np.nanmin(tile_dem_good_data, axis=0)
        tile_min_dem_array[~np.isfinite(tile_min_dem_array)] = OUTPUT_NODATA_VALUE

        # Compute maximum of good data
        tile_max_dem_array = np.nanmax(tile_dem_good_data, axis=0)
        tile_max_dem_array[~np.isfinite(tile_max_dem_array)] = OUTPUT_NODATA_VALUE

        # Compute standard deviation of good data
        tile_std_array = np.nanstd(tile_dem_good_data, axis=0)
        tile_std_array[~np.isfinite(tile_std_array)] = OUTPUT_NODATA_VALUE

        # Compute variance of good data
        tile_var_array = np.nanvar(tile_dem_good_data, axis=0)
        tile_var_array[~np.isfinite(tile_var_array)] = OUTPUT_NODATA_VALUE

         # Compute count of good data
        tile_count_array = np.sum(np.isfinite(tile_dem_good_data), axis=0)

        mean_path = output_dir / 'mean.tif'
        median_path = output_dir / 'median.tif'
        mad_path = output_dir / 'mad.tif'
        min_path = output_dir / 'min.tif'
        max_path = output_dir / 'max.tif'
        std_path = output_dir / 'std.tif'
        var_path = output_dir / 'var.tif'
        count_path = output_dir / 'count.tif'

        logging.info('Writing output data...')
        logging.debug(f'Ensuring output directory {output_dir} exists...')
        output_dir.mkdir(parents=True, exist_ok=True)

        logging.debug(f'Writing DEM mean values to {mean_path}...')
        write_cog(tile_mean_dem_array, gdal.GDT_Float32, self.get_geotransform(), OUTPUT_NODATA_VALUE, mean_path)

        logging.debug(f'Writing DEM median values to {median_path}...')
        write_cog(tile_median_dem_array, gdal.GDT_Float32, self.get_geotransform(), OUTPUT_NODATA_VALUE, median_path)

        logging.debug(f'Writing DEM MAD values to {mad_path}...')
        write_cog(tile_mad_dem_array, gdal.GDT_Float32, self.get_geotransform(), OUTPUT_NODATA_VALUE, mad_path)

        logging.debug(f'Writing DEM minimum values to {min_path}...')
        write_cog(tile_min_dem_array, gdal.GDT_Float32, self.get_geotransform(), OUTPUT_NODATA_VALUE, min_path)

        logging.debug(f'Writing DEM maximum values to {max_path}...')
        write_cog(tile_max_dem_array, gdal.GDT_Float32, self.get_geotransform(), OUTPUT_NODATA_VALUE, max_path)

        logging.debug(f'Writing DEM standard deviation values to {std_path}...')
        write_cog(tile_std_array, gdal.GDT_Float32, self.get_geotransform(), OUTPUT_NODATA_VALUE, std_path)

        logging.debug(f'Writing DEM variance values to {var_path}...')
        write_cog(tile_var_array, gdal.GDT_Float32, self.get_geotransform(), OUTPUT_NODATA_VALUE, var_path)

        logging.debug(f'Writing good-data count to {count_path}...')
        write_cog(tile_count_array, gdal.GDT_UInt16, self.get_geotransform(), 0, count_path)

        return error_strip_count

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
        self.basepath = config.strip_basepath

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
            strip_abs_path = self.basepath / strip_path
            intersecting_strip_paths.append(strip_abs_path)

        index_datasrc = None

        logging.info(f'Found {len(intersecting_strip_paths)} intersecting strips')
        return intersecting_strip_paths

def write_cog(data_array, gdal_datatype, geotransform, nodata_value, path):
    rows, cols = data_array.shape
    output_dataset = MEM_DRIVER.Create('', cols, rows, 1, gdal_datatype)
    output_dataset.SetSpatialRef(ARCTICDEM_SRS)
    output_dataset.SetGeoTransform(geotransform)
    output_band = output_dataset.GetRasterBand(1)
    output_band.SetNoDataValue(nodata_value)
    output_band.WriteArray(data_array)
    COG_DRIVER.CreateCopy(path, output_dataset)

def parse_args(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('config', type=str, help='path to TOML config file')
    parser.add_argument('row', type=int, help='row number of requested tile')
    parser.add_argument('col', type=int, help='column number of requested tile')
    parser.add_argument('outdir', type=str, help='(UNSTABLE) desired path to output directory')
    parser.add_argument('--allow-strip-errors', action='store_true', help='continue processing upon strip read errors')
    parser.add_argument('--log-level', type=str, choices=LOG_LEVELS.keys(), default='WARNING', help="logging level")
    parsed_args = parser.parse_args(args)
    return parsed_args

def main():
    input_args = parse_args(sys.argv[1:])
    logging.basicConfig(level=LOG_LEVELS[input_args.log_level])
    config = Config(input_args.config)
    strip_collection = StripCollection(config)
    tile = Tile(config=config, row=input_args.row, col=input_args.col)
    output_dir = Path(input_args.outdir)
    allow_strip_errors = input_args.allow_strip_errors

    intersecting_strip_paths = strip_collection.get_intersecting_strips(tile)
    error_count = tile.process_strip_data(intersecting_strip_paths, output_dir, allow_strip_errors)

    if error_count == 0:
        logging.info('Successfully processed tile')
    else:
        logging.info(f'Finished processing tile, {error_count} strip read error(s) encountered')
