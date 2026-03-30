import argparse
from pathlib import Path
import sys
import tomllib

ARCTICDEM_X_GSD = 2.0
ARCTICDEM_Y_GSD = 2.0

class Config:
    def __init__(self, path):
        with open(path, 'rb') as file:
            config_dict = tomllib.load(file)
            self.strip_index_path = Path(config_dict['input']['strip_index_path'])
            self.strip_basepath = Path(config_dict['input']['strip_basepath'])
            self.x_offset = config_dict['tiling']['x_offset']
            self.y_offset = config_dict['tiling']['y_offset']
            self.x_interval = config_dict['tiling']['x_interval']
            self.y_interval = config_dict['tiling']['y_interval']
            self.num_cols = self.x_interval / ARCTICDEM_X_GSD
            self.num_rows = self.y_interval / ARCTICDEM_Y_GSD

class Tile:
    def __init__(self, config, row, col):
        self.config = config
        self.row = row
        self.col = col

    def get_geotransform(self):
        geotransform = [
            self.config.x_offset + self.col * self.config.x_interval, ARCTICDEM_X_GSD, 0.0,
            self.config.y_offset + (self.row+1) * self.config.y_interval, 0.0, -ARCTICDEM_Y_GSD,
        ]
        return geotransform

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
