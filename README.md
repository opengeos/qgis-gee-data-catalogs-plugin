# Earth Engine Data Catalogs Plugin for QGIS

A comprehensive QGIS plugin for browsing, searching, and loading Google Earth Engine data catalogs directly in QGIS.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- **Dynamic Data Catalog Browser**: Automatically loads datasets from official GEE catalog and community datasets
  - [Official GEE Catalog](https://github.com/opengeos/Earth-Engine-Catalog) - 900+ datasets
  - [Awesome GEE Community Datasets](https://github.com/samapriya/awesome-gee-community-datasets) - 300+ community datasets
- **Search & Filter**: Search datasets by keywords, tags, providers, data types, and sources
- **Advanced Filtering for ImageCollections**:
  - Date range filtering
  - Bounding box (current map extent)
  - Cloud cover percentage
- **Flexible Image Loading**:
  - Load composite images (mosaic, median, mean, min, max)
  - Select and load individual images from ImageCollections
- **Code Console**: Write and execute geemap/Earth Engine Python code directly
- **Visualization Parameters**: Customize with bands, min/max values, and color palettes
- **Multiple Data Types**: Load EE Image, ImageCollection, and FeatureCollection layers
- **Integration**: Works seamlessly with [qgis-geemap-plugin](https://github.com/opengeos/qgis-geemap-plugin)
- **Update Checker**: Built-in plugin update checker from GitHub

## Data Sources

The plugin dynamically fetches catalog data from:

| Source | URL | Datasets |
|--------|-----|----------|
| Official GEE Catalog | [TSV](https://raw.githubusercontent.com/opengeos/Earth-Engine-Catalog/master/gee_catalog.tsv) / [JSON](https://raw.githubusercontent.com/opengeos/Earth-Engine-Catalog/master/gee_catalog.json) | 900+ |
| Community Datasets | [CSV](https://raw.githubusercontent.com/samapriya/awesome-gee-community-datasets/master/community_datasets.csv) / [JSON](https://raw.githubusercontent.com/samapriya/awesome-gee-community-datasets/master/community_datasets.json) | 300+ |

## Installation

### Prerequisites

1. QGIS 3.28 or later
2. Python packages:
   - `earthengine-api`: `pip install earthengine-api`
   - (Optional) `geemap`: `pip install geemap`

### From Source

1. Clone or download this repository
2. Run the installation script:

```bash
python install.py
```

3. Restart QGIS
4. Enable the plugin in **Plugins → Manage and Install Plugins → Earth Engine Data Catalogs**

### Manual Installation

1. Copy the `gee_data_catalogs` folder to your QGIS plugins directory:
   - **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **macOS**: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Windows**: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`

2. Restart QGIS and enable the plugin

## Usage

### Initialize Earth Engine

Before using the plugin, you need to authenticate with Google Earth Engine:

1. Click the **Initialize Earth Engine** button in the toolbar
2. If not authenticated, run `earthengine authenticate` in your terminal
3. Set the `EE_PROJECT_ID` environment variable for auto-initialization

### Browse Datasets

1. Click the **Data Catalog** button to open the catalog panel
2. Browse datasets by category in the **Browse** tab
3. Filter by source (Official/Community)
4. Click on a dataset to view its information
5. Click **Add to Map** to load with default visualization

### Search Datasets

1. Go to the **Search** tab
2. Enter keywords in the search box
3. Filter by category, data type, or source
4. Double-click a result to add it to the map

### Load with Custom Parameters

1. Go to the **Load** tab
2. Enter the dataset Asset ID
3. Configure filters:
   - Date range for ImageCollections
   - Cloud cover threshold
   - Spatial filter (current map extent)
4. Choose loading mode:
   - **Composite**: mosaic, median, mean, min, max
   - **Individual Images**: Select specific images to load
5. Set visualization parameters
6. Click **Load Dataset**

### Code Console

1. Go to the **Code** tab
2. Write Python/geemap code using standard geemap syntax
3. Click **Run Code** to execute

Example:
```python
import ee
import geemap

m = geemap.Map()

# Load Sentinel-2 imagery
s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')\
    .filterDate('2023-01-01', '2023-06-01')\
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))\
    .median()

m.add_layer(s2, {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 3000}, 'Sentinel-2')
```

### Notes

- **Network Timeout Warnings**: You may see timeout warnings in the QGIS log when loading Earth Engine layers. These are normal and occur due to Earth Engine's tile serving. The layers will still load successfully - just wait for the tiles to appear.
- **Performance**: For large ImageCollections, use date/spatial filters to reduce the number of images processed.

## Available Dataset Categories

- **Landsat**: Landsat 5, 7, 8, 9 Collection 2
- **Sentinel**: Sentinel-1 SAR, Sentinel-2 MSI, Sentinel-3, Sentinel-5P
- **MODIS**: Vegetation indices, surface reflectance, temperature, snow, fire
- **Elevation**: SRTM, ALOS, Copernicus DEM, ASTER GDEM
- **Land Cover**: ESA WorldCover, Dynamic World, MODIS Land Cover, NLCD
- **Climate & Weather**: ERA5, CHIRPS, GPM, TRMM
- **Boundaries**: FAO GAUL, US Census TIGER, GADM
- **Night Lights**: VIIRS, DMSP-OLS
- **Population**: WorldPop, GPW, LandScan
- **Water**: JRC Global Surface Water
- **Vegetation**: NDVI, EVI, LAI, GPP products
- **Atmosphere**: Aerosol, Ozone, NO2, CO2
- **Agriculture**: Crop maps, harvest area, irrigation
- **Soil**: Soil properties, moisture, organic carbon
- **Fire**: Active fire, burned area
- **Ocean**: SST, chlorophyll, coral reefs
- **Urban**: Built-up areas, impervious surfaces

## Configuration

Access settings via the **Settings** toolbar button:

- **General**: Auto-initialization, notifications, default category
- **Earth Engine**: Project ID, default filters, performance options
- **Display**: Layer opacity, visualization defaults

## Development

### Project Structure

```
qgis-gee-data-catalogs-plugins/
├── gee_data_catalogs/
│   ├── __init__.py
│   ├── gee_data_catalogs.py      # Main plugin class
│   ├── metadata.txt              # Plugin metadata
│   ├── core/
│   │   ├── __init__.py
│   │   ├── ee_utils.py           # Earth Engine utilities
│   │   └── catalog_data.py       # Dynamic catalog fetching
│   ├── dialogs/
│   │   ├── __init__.py
│   │   ├── catalog_dock.py       # Main catalog browser
│   │   ├── settings_dock.py      # Settings panel
│   │   └── update_checker.py     # Update checker dialog
│   └── icons/
│       ├── icon.svg
│       ├── settings.svg
│       ├── about.svg
│       └── earth.svg
├── install.py                    # Installation script
├── package_plugin.py             # Packaging script
└── README.md
```

### Packaging for Release

```bash
python package_plugin.py
```

This creates a zip file ready for upload to the QGIS plugin repository.

## Related Projects

- [geemap](https://github.com/gee-community/geemap) - A Python package for interactive mapping with Google Earth Engine
- [qgis-geemap-plugin](https://github.com/opengeos/qgis-geemap-plugin) - QGIS plugin for geemap integration
- [Earth Engine Data Catalog](https://developers.google.com/earth-engine/datasets) - Official GEE dataset documentation
- [Awesome GEE Community Datasets](https://github.com/samapriya/awesome-gee-community-datasets) - Community-contributed datasets

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
