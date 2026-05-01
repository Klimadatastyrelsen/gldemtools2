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

# Base path to which the strip paths will be appended to obtain the strips'
# absolute *.tar.gz paths
basepath = "/largestorage/strips/"

[tiling]
# Origin in georeferenced coordinates
x_offset = 0.0
y_offset = 0.0

# Tile size in georeferenced coordinates
x_interval = 10000.0
y_interval = 10000.0

[processing]
# Half-width (in meters) of the confidence intervals assumed with Marzullo's
# algorithm
marzullo_halfwidth = 5.0
```

## Usage
Assuming a configuration file as described above, each output tile can be
produced by invoking `pixi run process_tile`:
```
usage: pixi run process_tile [-h] [--allow-strip-errors]
                             [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
                             config row col outdir

positional arguments:
  config                path to TOML config file
  row                   row number of requested tile
  col                   column number of requested tile
  outdir                (UNSTABLE) desired path to output directory

options:
  -h, --help            show this help message and exit
  --allow-strip-errors  continue processing upon strip read errors
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        logging level
```

The provided `outdir` will be created if it does not already exist.

For example, the following will compute tile (42, 1337) in the tiling scheme
defined by `/foo/bar/config.toml`, storing the output COG rasters in
`/foo/bar/output/42_1337/`, and instructing the program to keep going if
corrupt/missing strip files are encountered:
```
pixi run process_tile /foo/bar/config.toml 42 1337 /foo/bar/output/42_1337/ --allow-strip-errors
```

## Output
Currently, the `process_tile` utility will produce the following pixelwise
statistics as COG files in the provided output directory. All statistics are
computed exclusively from ArcticDEM "good data" (i.e. where ArcticDEM's
bitmask is 0, see
[the documentation for PGC's DEM products](https://www.pgc.umn.edu/guides/stereo-derived-elevation-models/pgc-dem-products-arcticdem-rema-and-earthdem/#section-7).)

| File | Description |
| ---- | ----------- |
| `count.tif` | Number of strips with data available |
| `mad.tif` | [Median absolute deviation from the median](https://en.wikipedia.org/wiki/Median_absolute_deviation) (MAD) |
| `marzullo.tif` | Optimal result as determined by [Marzullo's algorithm](https://en.wikipedia.org/wiki/Marzullo%27s_algorithm) |
| `marzullo_count.tif` | Number of overlapping confidence intervals at the Marzullo result |
| `max.tif` | Maximum |
| `mean.tif` | Arithmetic mean |
| `median.tif` | Median |
| `min.tif` | Minimum |
| `std.tif` | Standard deviation |
| `var.tif` | Variance |
