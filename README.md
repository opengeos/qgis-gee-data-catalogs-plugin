# Earth Engine Data Catalogs Plugin for QGIS

A comprehensive QGIS plugin for browsing, searching, and loading Google Earth Engine data catalogs directly in QGIS.

[![QGIS Plugin](https://img.shields.io/badge/QGIS-Plugin-green.svg)](https://plugins.qgis.org/plugins/gee_data_catalogs)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- **Dynamic Data Catalog Browser**: Automatically loads datasets from official GEE catalog and community datasets
  - [Official Earth Engine Data Catalog](https://github.com/opengeos/Earth-Engine-Catalog) - 780+ datasets
  - [Awesome GEE Community Catalog](https://github.com/samapriya/awesome-gee-community-datasets) - 4,360+ community datasets
- **Search & Filter**: Search datasets by keywords, tags, providers, data types, and sources
- **Advanced Filtering for ImageCollections**:
  - Date range filtering
  - Bounding box (current map extent)
  - Cloud cover percentage
- **Time Series**: Create time series layers from ImageCollections
- **Pixel Time Series Inspector**: Click on the map to extract and chart time series at a point (similar to Earth Engine's `ui.Chart.image.series`)
- **Flexible Image Loading**:
  - Load composite images (mosaic, median, mean, min, max)
  - Select and load individual images from ImageCollections
- **Code Console**: Write and execute geemap/Earth Engine Python code directly
- **Visualization Parameters**: Customize with bands, min/max values, and color palettes
- **Conversion**: Convert Earth Engine JavaScript API to Python API
- **Inspector**: Inspect Earth Engine layer values at specific locations
- **Export**: Export Earth Engine layers to various file formats
- **Multiple Data Types**: Load EE Image, ImageCollection, and FeatureCollection layers
- **Integration**: Works seamlessly with [qgis-geemap-plugin](https://github.com/opengeos/qgis-geemap-plugin)
- **Update Checker**: Built-in plugin update checker from GitHub

## Data Sources

The plugin dynamically fetches catalog data from:

| Source                             | URL                                                                                                                                                                                                                                 | Datasets |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| Official Earth Engine Data Catalog | [TSV](https://raw.githubusercontent.com/opengeos/Earth-Engine-Catalog/master/gee_catalog.tsv) / [JSON](https://raw.githubusercontent.com/opengeos/Earth-Engine-Catalog/master/gee_catalog.json)                                     | 780+     |
| Awesome GEE Community Catalog      | [CSV](https://raw.githubusercontent.com/samapriya/awesome-gee-community-datasets/master/community_datasets.csv) / [JSON](https://raw.githubusercontent.com/samapriya/awesome-gee-community-datasets/master/community_datasets.json) | 4,360+   |

## Video Tutorials

👉 [This QGIS Plugin Unlocks 80 Petabytes of Satellite Data – For Free!](https://youtu.be/nZ3D6wLKJQw)

[![Earth Engine Data Catalogs Plugin for QGIS](https://github.com/user-attachments/assets/1f6af038-a028-470a-bc43-8ee8394e2c08)](https://youtu.be/nZ3D6wLKJQw)


👉 [Create Stunning Time-Series Satellite Images in Seconds!](https://youtu.be/8IW6XqnUjgg)

[![Create Stunning Time-Series Satellite Images in Seconds](https://github.com/user-attachments/assets/09e6a5a8-db7f-46f7-84d4-0c272a6cae4b)](https://youtu.be/8IW6XqnUjgg)

## Installation

### Prerequisites

1. **QGIS 3.28 or higher**
2. **Google Earth Engine Account**: Sign up at [earthengine.google.com](https://earthengine.google.com/)

### Install QGIS and Google Earth Engine

#### 1) Install Pixi

#### Linux/macOS (bash/zsh)

```bash
curl -fsSL https://pixi.sh/install.sh | sh
```

Close and re-open your terminal (or reload your shell) so `pixi` is on your `PATH`. Then confirm:

```bash
pixi --version
```

#### Windows (PowerShell)

Open **PowerShell** (preferably as a normal user, Admin not required), then run:

```powershell
powershell -ExecutionPolicy Bypass -c "irm -useb https://pixi.sh/install.ps1 | iex"
```

Close and re-open PowerShell, then confirm:

```powershell
pixi --version
```

---

#### 2) Create a Pixi project

Navigate to a directory where you want to create the project and run:

```bash
pixi init geo
cd geo
```

#### 3) Install the environment

From the `geo` folder:

```bash
pixi add qgis geemap geopandas xee rioxarray
```

#### 4) Authenticate Earth Engine

```bash
pixi run earthengine authenticate
```

### Installing the Plugin

#### Method 1: From QGIS Plugin Manager (Recommended)

1. Open QGIS using `pixi run qgis`
2. Go to **Plugins** → **Manage and Install Plugins...**
3. Go to the **Settings** tab
4. Click **Add...** under "Plugin Repositories"
5. Give a name for the repository, e.g., "OpenGeos"
6. Enter the URL of the repository: https://qgis.gishub.org/plugins.xml
7. Click **OK**
8. Go to the **All** tab
9. Search for "Earth Engine Data Catalogs"
10. Select "Earth Engine Data Catalogs" from the list and click **Install Plugin**

#### Method 2: From ZIP File

1. Download the latest release ZIP from <https://qgis.gishub.org>
2. In QGIS, go to `Plugins` → `Manage and Install Plugins`
3. Click `Install from ZIP` and select the downloaded file
4. Enable the plugin in the `Installed` tab

#### Method 3: Manual Installation

1. Clone or download this repository
2. Copy the `gee_data_catalogs` folder to your QGIS plugins directory:
   - **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Windows**: `C:\Users\<username>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\`
   - **macOS**: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
3. Restart QGIS and enable the plugin

### Uninstalling

```bash
python install.py --remove
# or
./install.sh --remove
```

## Usage

### Initialize Earth Engine

Before using the plugin, you need to authenticate with Google Earth Engine:

1. Click the **Initialize Earth Engine** button in the toolbar
2. If not authenticated, run `earthengine authenticate` in your terminal
3. Set the `EE_PROJECT_ID` environment variable for auto-initialization

![](https://github.com/user-attachments/assets/4d23e72d-1995-436c-9ad2-6fbd1bedcc02)

### Browse Datasets

1. Click the **Data Catalog** button to open the catalog panel
2. Browse datasets by category in the **Browse** tab
3. Filter by source (Official/Community)
4. Click on a dataset to view its information
5. Click **Add to Map** to load with default visualization

![](https://github.com/user-attachments/assets/f4deada0-21bb-4b05-8b2a-7b69a1c21f90)

### Search Datasets

1. Go to the **Search** tab
2. Enter keywords in the search box
3. Filter by category, data type, or source
4. Double-click a result to add it to the map

![](https://github.com/user-attachments/assets/9c0f0eca-c232-41bc-bc86-03364b238eda)

### Time Series

1. Go to the **Time Series** tab
2. Enter the dataset Asset ID
3. Set the date range and optional filters
4. Choose a frequency (e.g., month, year)
5. Choose a reducer (e.g., mean, median)
5. Click **Create Time Series** to create a time series layer
6. Click **Next** or **Previous** to navigate through the time series

![](https://github.com/user-attachments/assets/4def57a8-083d-49de-ad35-b54904928681)

### Pixel Time Series Inspector

The **Pixel Time Series Inspector** allows you to interactively click on the map and extract time series data at that point location, similar to Earth Engine's `ui.Chart.image.series` functionality.

1. Go to the **Time Series** tab
2. Enter the dataset Asset ID and configure date range/filters
3. Scroll down to the **Pixel Time Series Inspector** section
4. Click **Start Pixel Inspector** to activate the map click tool
5. Click anywhere on the map to select a pixel location
6. (Optional) Specify bands to extract and set the scale (resolution)
7. Click **Extract & Chart** to:
   - Extract pixel values for each image in the collection
   - Display an interactive chart with the time series
8. In the chart dialog:
   - Select/deselect bands to display
   - Toggle data points, grid, and line connections
   - View statistics (min, max, mean, std) for each band
   - Export data to CSV, JSON, or PNG
   - Copy data to clipboard

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

![](https://github.com/user-attachments/assets/75e0d1da-3848-4394-9832-8f484ba22231)

### Code Console

1. Go to the **Code** tab
2. Write Python code using the standard Earth Engine Python API and geemap syntax
3. Click **Run Code** to execute the code

![](https://github.com/user-attachments/assets/a394f9cb-be5c-42d3-93cd-84bc4f8bba7c)

### Conversion

1. Go to the **Conversion** tab
2. Select an input layer
3. Choose the conversion type (Image, ImageCollection, or FeatureCollection)
4. Configure the output options

![](https://github.com/user-attachments/assets/2d408de7-419c-4647-a689-923bdc470631)

### Inspector

1. Go to the **Inspector** tab
2. Click the **Start Inspector** button
3. Click on the map to inspect Earth Engine layer values at that location
4. Click the **Clear** button to clear the inspector
5. Click the **Refresh Layers** button to refresh the layers

![](https://github.com/user-attachments/assets/db0868e8-73de-4384-9ce3-b1f3d005cc7e)

### Export

1. Go to the **Export** tab
2. Select an EE layer to export
3. Choose the export region (map extent, vector bounds, drawn, or custom)
4. Set export options (scale, CRS, and format)
5. Choose an output file or leave it blank for a temporary export
6. Click **Export**

![](https://github.com/user-attachments/assets/aa069953-aa6b-467f-990f-5f0f69da7f8d)

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

![](https://github.com/user-attachments/assets/f4914220-e5e7-48a8-af6b-0b59b0f677ba)

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

## Troubleshooting

If you encounter the error "Failed to initialize Google Earth Engine", you can try the following:

### Method 1: Manually Authenticate Earth Engine in QGIS Python Console

- Ensure you have an active Earth Engine account
- Log in to your Earth Engine account at <https://code.earthengine.google.com> to get your Project ID
- Open the QGIS Python Console (QGIS -> Plugins -> Python Console) and run the following Python code to authenticate and initialize Earth Engine. Make sure to replace `your-ee-project` with your actual Earth Engine Project ID.

```python
import ee
ee.Authenticate()
ee.Initialize(project="your-ee-project")
```

![](https://github.com/user-attachments/assets/a7321180-1261-4c82-b545-9dbe676a864c)

### Method 2: Set `EE_PROJECT_ID` Environment Variable

- Set the `EE_PROJECT_ID` environment variable in your system or QGIS profile.

![](https://github.com/user-attachments/assets/952959df-5b13-44ec-a73d-cbb6b404d252)

### Method 3: Enter Project ID in the **Settings** tab of the plugin

![](https://github.com/user-attachments/assets/1a865934-2f40-4bbf-9b4c-a90b2a4a7dfa)

## Related Projects

- [geemap](https://github.com/gee-community/geemap) - A Python package for interactive mapping with Google Earth Engine
- [qgis-geemap-plugin](https://github.com/opengeos/qgis-geemap-plugin) - QGIS plugin for geemap integration
- [Earth Engine Data Catalog](https://developers.google.com/earth-engine/datasets) - Official GEE dataset documentation
- [Awesome GEE Community Datasets](https://github.com/samapriya/awesome-gee-community-datasets) - Community-contributed datasets

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
