# gldemtools2
Processing tools to generate DEM of Greenland, take 2

## Installation
To use the software, ensure you have [Pixi](https://pixi.prefix.dev/)
installed.

Clone this repo, and from the root directory of this folder you can run the
following checks:
* `pixi run test`: Checks functionality
* `pixi run format`: Checks formatting/linting
* `pixi run typecheck`: Checks optional type annotations

## Configuration
The software assumes a tiling scheme in the native SRS (EPSG:3413) of
ArcticDEM strips. The processing details are controlled through a TOML file as
follows:
```TOML
[strips]
# Path to an OGR-readable index of ArcticDEM strips
index_path = "/foo/bar/strip_index.gpkg"

# In the above index, the name of the field containing the strip path
# (*.tar.gz) for each feature
path_fieldname = "fileurl"

# TODO: not currently used
basepath = "/foo/bar/strips"

[tiling]
# Origin in georeferenced coordinates
x_offset = 0.0
y_offset = 0.0

# Tile size in georeferenced coordinates
x_interval = 10000.0
y_interval = 10000.0
```

## Usage
Assuming a configuration file as described above, each output tile can be
produced by invoking `pixi run process_tile`:
```
usage: pixi run process_tile [-h]
                             [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
                             config row col out_path

positional arguments:
  config                path to TOML config file
  row                   row number of requested tile
  col                   column number of requested tile
  out_path              (UNSTABLE) desired path to output TIFF file

options:
  -h, --help            show this help message and exit
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        logging level
```

For example, the following will compute tile (42, 1337) in the tiling scheme
defined by `config.toml`, storing the output in `/foo/bar/dem_42_1337.tif`:
```
pixi run process_tile config.toml 42 1337 /foo/bar/dem_42_1337.tif
```
