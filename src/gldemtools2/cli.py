import argparse
from collections import OrderedDict
import logging
from pathlib import Path
import sys

from gldemtools2.processing import Config, StripCollection, Tile

LOG_LEVELS = OrderedDict([
    ('DEBUG', logging.DEBUG),
    ('INFO', logging.INFO),
    ('WARNING', logging.WARNING),
    ('ERROR', logging.ERROR),
    ('CRITICAL', logging.CRITICAL)
])

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
