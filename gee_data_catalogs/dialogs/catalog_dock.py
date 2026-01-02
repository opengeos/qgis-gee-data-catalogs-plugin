"""
Catalog Dock Widget for GEE Data Catalogs

This module provides the main catalog browser panel for discovering
and loading Google Earth Engine datasets.
"""

from datetime import datetime, timedelta

from qgis.PyQt.QtCore import Qt, QCoreApplication, QThread, pyqtSignal, QTimer
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextEdit,
    QTextBrowser,
    QGroupBox,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QFormLayout,
    QMessageBox,
    QProgressBar,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QSplitter,
    QScrollArea,
    QDateEdit,
    QApplication,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QRadioButton,
    QButtonGroup,
    QSlider,
    QFileDialog,
)
from qgis.PyQt.QtGui import QFont, QCursor
from qgis.core import QgsProject, QgsRectangle, QgsMessageLog, Qgis

try:
    import ee
except ImportError:
    ee = None


class CatalogLoaderThread(QThread):
    """Thread for loading catalog data in background."""

    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, include_community: bool = True):
        super().__init__()
        self.include_community = include_community

    def run(self):
        try:
            from ..core.catalog_data import get_catalog_data, refresh_catalogs

            self.progress.emit("Fetching catalogs from GitHub...")
            result = refresh_catalogs()
            self.progress.emit(f"Loaded {result['total_count']} datasets")

            catalog = get_catalog_data(include_community=self.include_community)
            self.finished.emit(catalog)
        except Exception as e:
            self.error.emit(str(e))


class PreviewInfoThread(QThread):
    """Thread for getting dataset preview information."""

    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(
        self,
        asset_id: str,
        use_date_filter: bool = False,
        start_date: str = None,
        end_date: str = None,
        selected_images: list = None,
    ):
        super().__init__()
        self.asset_id = asset_id
        self.use_date_filter = use_date_filter
        self.start_date = start_date
        self.end_date = end_date
        self.selected_images = selected_images  # List of {"id": ..., "date": ...}

    def run(self):
        try:
            import ee
            from ..core.ee_utils import detect_asset_type

            # If selected images are provided, show info as an ImageCollection
            if self.selected_images:
                self.progress.emit(
                    f"Getting info for {len(self.selected_images)} image(s)..."
                )

                # Create an ImageCollection from the selected images
                image_ids = [img_info["id"] for img_info in self.selected_images]
                collection = ee.ImageCollection(image_ids)

                size = collection.size().getInfo()
                info_text = f"Type: ImageCollection (filtered)\n"
                info_text += f"From: {self.asset_id}\n"
                info_text += f"Size: {size} images\n\n"

                # Get date range
                dates = [
                    img_info.get("date", "")
                    for img_info in self.selected_images
                    if img_info.get("date")
                ]
                if dates:
                    dates_sorted = sorted(dates)
                    info_text += (
                        f"Date Range: {dates_sorted[0]} to {dates_sorted[-1]}\n\n"
                    )

                # Get bands from first image
                if size > 0:
                    first = collection.first()
                    bands = first.bandNames().getInfo()
                    info_text += f"Bands per image: {len(bands)}\n"
                    for band in bands[:10]:
                        info_text += f"  - {band}\n"
                    if len(bands) > 10:
                        info_text += f"  ... and {len(bands) - 10} more\n"

                self.finished.emit(info_text)
                return

            self.progress.emit(f"Detecting asset type...")

            data_type = detect_asset_type(self.asset_id)
            info_text = f"Type: {data_type}\nID: {self.asset_id}\n\n"

            self.progress.emit(f"Getting info...")

            if data_type == "Image":
                image = ee.Image(self.asset_id)
                bands = image.bandNames().getInfo()
                info_text += f"Bands: {len(bands)}\n"
                for band in bands[:10]:
                    info_text += f"  - {band}\n"
                if len(bands) > 10:
                    info_text += f"  ... and {len(bands) - 10} more\n"

            elif data_type == "ImageCollection":
                collection = ee.ImageCollection(self.asset_id)
                if self.use_date_filter and self.start_date and self.end_date:
                    collection = collection.filterDate(self.start_date, self.end_date)

                size = collection.size().getInfo()
                info_text += f"Size: {size} images\n"

                if size > 0:
                    first = collection.first()
                    bands = first.bandNames().getInfo()
                    info_text += f"\nBands per image: {len(bands)}\n"
                    for band in bands[:10]:
                        info_text += f"  - {band}\n"
                    if len(bands) > 10:
                        info_text += f"  ... and {len(bands) - 10} more\n"

                info_text += (
                    "\nNote: For large collections, fetching images may take time."
                )

            elif data_type == "FeatureCollection":
                fc = ee.FeatureCollection(self.asset_id)
                size = fc.size().getInfo()
                info_text += f"Size: {size} features\n"
            else:
                info_text += "Could not determine asset type.\n"
                info_text += "Try loading the asset directly."

            self.finished.emit(info_text)
        except Exception as e:
            self.error.emit(str(e))


class ThumbnailLoaderThread(QThread):
    """Thread for loading dataset thumbnail images."""

    finished = pyqtSignal(str)  # base64 encoded image
    error = pyqtSignal(str)

    def __init__(self, thumbnail_url: str):
        super().__init__()
        self.thumbnail_url = thumbnail_url

    def run(self):
        try:
            import base64
            from urllib.request import urlopen, Request

            # Add user agent to avoid 403 errors
            req = Request(self.thumbnail_url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=10) as response:
                img_data = response.read()
                img_base64 = base64.b64encode(img_data).decode("utf-8")
                # Determine image format from URL
                img_format = "png" if self.thumbnail_url.endswith(".png") else "jpeg"
                self.finished.emit(f"data:image/{img_format};base64,{img_base64}")
        except Exception as e:
            self.error.emit(str(e))


class ImageListLoaderThread(QThread):
    """Thread for loading images from an ImageCollection."""

    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, collection, limit: int = 100):
        super().__init__()
        self.collection = collection
        self.limit = limit

    def run(self):
        try:
            import ee

            self.progress.emit("Fetching image list (this may take a moment)...")

            # More efficient approach: only fetch the metadata we need
            # Use reduceColumns to get only IDs and dates in a single call
            limited = self.collection.limit(self.limit)

            # Get IDs and timestamps in a single efficient call
            info_list = limited.aggregate_array("system:id").getInfo()
            time_list = limited.aggregate_array("system:time_start").getInfo()

            images_info = []
            for i, image_id in enumerate(info_list):
                # Try to get date
                date_str = "Unknown date"
                if i < len(time_list) and time_list[i]:
                    try:
                        timestamp = time_list[i]
                        date_str = datetime.fromtimestamp(timestamp / 1000).strftime(
                            "%Y-%m-%d"
                        )
                    except Exception:
                        pass

                images_info.append(
                    {
                        "id": image_id,
                        "date": date_str,
                        "properties": {},  # Don't fetch full properties for speed
                    }
                )

            self.progress.emit(f"Found {len(images_info)} images")
            self.finished.emit(images_info)
        except Exception as e:
            self.error.emit(str(e))


class TimeSeriesLoaderThread(QThread):
    """Thread for creating time series from ImageCollection."""

    finished = pyqtSignal(list, list)  # (images_list, labels_list)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(
        self,
        asset_id: str,
        start_date: str,
        end_date: str,
        frequency: str = "month",
        reducer: str = "median",
        bands: list = None,
        region: list = None,  # [west, south, east, north]
        cloud_cover: int = None,
        cloud_property: str = "CLOUDY_PIXEL_PERCENTAGE",
        property_filters: list = None,  # [(prop, op, value), ...]
    ):
        super().__init__()
        self.asset_id = asset_id
        self.start_date = start_date
        self.end_date = end_date
        self.frequency = frequency
        self.reducer = reducer
        self.bands = bands
        self.region = region
        self.cloud_cover = cloud_cover
        self.cloud_property = cloud_property
        self.property_filters = property_filters or []

    def _apply_property_filters(self, collection):
        """Apply property filters to collection."""
        import ee

        for prop_name, op, value in self.property_filters:
            if op == "==":
                collection = collection.filter(ee.Filter.eq(prop_name, value))
            elif op == "!=":
                collection = collection.filter(ee.Filter.neq(prop_name, value))
            elif op == ">":
                collection = collection.filter(ee.Filter.gt(prop_name, value))
            elif op == ">=":
                collection = collection.filter(ee.Filter.gte(prop_name, value))
            elif op == "<":
                collection = collection.filter(ee.Filter.lt(prop_name, value))
            elif op == "<=":
                collection = collection.filter(ee.Filter.lte(prop_name, value))
        return collection

    def run(self):
        try:
            import ee
            from datetime import datetime
            from dateutil.relativedelta import relativedelta

            self.progress.emit(
                f"Creating time series with {self.frequency} frequency..."
            )

            # Load the collection
            collection = ee.ImageCollection(self.asset_id)

            # Apply date filter
            collection = collection.filterDate(self.start_date, self.end_date)

            # Apply region filter if provided
            region = None
            if self.region:
                region = ee.Geometry.Rectangle(self.region)
                collection = collection.filterBounds(region)

            # Apply cloud filter if provided
            if self.cloud_cover is not None:
                collection = collection.filter(
                    ee.Filter.lt(self.cloud_property, self.cloud_cover)
                )

            # Apply property filters
            if self.property_filters:
                collection = self._apply_property_filters(collection)

            # Select bands if specified
            if self.bands:
                collection = collection.select(self.bands)

            # Get frequency settings
            freq_dict = {
                "day": ("YYYY-MM-dd", "day", 1),
                "week": ("YYYY-MM-dd", "week", 1),
                "month": ("YYYY-MM", "month", 1),
                "quarter": ("YYYY-MM", "month", 3),
                "year": ("YYYY", "year", 1),
            }

            date_format, unit, step = freq_dict.get(
                self.frequency, ("YYYY-MM", "month", 1)
            )

            # Generate date sequence
            start_dt = datetime.strptime(self.start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(self.end_date, "%Y-%m-%d")

            dates = []
            current = start_dt
            while current < end_dt:
                dates.append(current.strftime("%Y-%m-%d"))
                if unit == "day":
                    current += relativedelta(days=step)
                elif unit == "week":
                    current += relativedelta(weeks=step)
                elif unit == "month":
                    current += relativedelta(months=step)
                elif unit == "year":
                    current += relativedelta(years=step)

            if not dates:
                self.error.emit("No dates in the specified range")
                return

            self.progress.emit(f"Processing {len(dates)} time steps...")

            # Get reducer function
            reducer_func = getattr(ee.Reducer, self.reducer)()

            # Create composite for each time step
            images_data = []
            labels = []

            for i, date_str in enumerate(dates):
                start = ee.Date(date_str)
                if unit == "day":
                    end = start.advance(step, "day")
                elif unit == "week":
                    end = start.advance(step * 7, "day")
                elif unit == "month":
                    end = start.advance(step, "month")
                elif unit == "year":
                    end = start.advance(step, "year")

                # Filter collection for this time period
                sub_col = collection.filterDate(start, end)

                # Reduce to single image
                image = sub_col.reduce(reducer_func)

                # Format label based on frequency
                if self.frequency == "day":
                    label = date_str
                elif self.frequency == "week":
                    label = f"Week of {date_str}"
                elif self.frequency == "month":
                    label = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m")
                elif self.frequency == "quarter":
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    quarter = (dt.month - 1) // 3 + 1
                    label = f"{dt.year} Q{quarter}"
                elif self.frequency == "year":
                    label = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y")
                else:
                    label = date_str

                images_data.append(
                    {
                        "start_date": date_str,
                        "end_date": end.format("YYYY-MM-dd").getInfo(),
                        "label": label,
                    }
                )
                labels.append(label)
                self.progress.emit(f"Processed {i+1}/{len(dates)} time steps...")

            if not images_data:
                self.error.emit("No images found in the specified date range")
                return

            self.progress.emit(f"Created time series with {len(images_data)} images")
            self.finished.emit(images_data, labels)

        except Exception as e:
            import traceback

            self.error.emit(f"{str(e)}\n{traceback.format_exc()}")


class InspectorWorker(QThread):
    """Thread for inspecting Earth Engine data at a point."""

    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, ee_layers: dict, point: tuple, scale: int = 30):
        super().__init__()
        self.ee_layers = ee_layers
        self.lon, self.lat = point
        self.scale = scale

    def run(self):
        try:
            import ee

            if not self.ee_layers:
                self.finished.emit({})
                return

            results = {}
            point_geom = ee.Geometry.Point([self.lon, self.lat])

            for layer_name, (ee_object, vis_params) in self.ee_layers.items():
                try:
                    self.progress.emit(f"Inspecting {layer_name}...")

                    if isinstance(ee_object, ee.Image):
                        # Sample the image at the point
                        sample = ee_object.sample(
                            region=point_geom, scale=self.scale, geometries=True
                        ).first()
                        props = sample.getInfo()

                        if props and "properties" in props:
                            results[layer_name] = {
                                "type": "Image",
                                "properties": props["properties"],
                            }

                    elif isinstance(ee_object, ee.ImageCollection):
                        # Mosaic and sample
                        image = ee_object.mosaic()
                        sample = image.sample(
                            region=point_geom, scale=self.scale, geometries=True
                        ).first()
                        props = sample.getInfo()

                        if props and "properties" in props:
                            results[layer_name] = {
                                "type": "ImageCollection",
                                "properties": props["properties"],
                            }

                    elif isinstance(ee_object, ee.FeatureCollection):
                        # Filter features at the point
                        filtered = ee_object.filterBounds(point_geom)

                        # First check if there are any features (fast operation)
                        count = filtered.size().getInfo()

                        if count > 0:
                            # Remove geometries to improve performance
                            # By removing geometries, we reduce data transfer significantly
                            # This is critical for FeatureCollections with complex geometries
                            features_without_geom = filtered.map(
                                lambda f: ee.Feature(
                                    None, f.toDictionary(f.propertyNames())
                                )
                            )

                            # Limit to 10 features for display and get the data
                            limited = features_without_geom.limit(10)
                            features_info = limited.getInfo()

                            results[layer_name] = {
                                "type": "FeatureCollection",
                                "count": count,
                                "features": features_info.get("features", []),
                            }

                except Exception as e:
                    results[layer_name] = {"type": "Error", "error": str(e)}

            self.finished.emit(results)

        except Exception as e:
            self.error.emit(str(e))


class ExportWorkerThread(QThread):
    """Thread for exporting Earth Engine data in background."""

    finished = pyqtSignal(str)  # output_path
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(
        self,
        export_type: str,  # "image" or "features"
        ee_object,
        region,
        output_path: str,
        scale: int = 30,
        crs: str = "EPSG:3857",
        vector_format: str = "GeoJSON",
    ):
        super().__init__()
        self.export_type = export_type
        self.ee_object = ee_object
        self.region = region
        self.output_path = output_path
        self.scale = scale
        self.crs = crs
        self.vector_format = vector_format

    def run(self):
        try:
            if self.export_type == "image":
                self._export_image()
            else:
                self._export_features()
        except Exception as e:
            import traceback

            self.error.emit(f"{str(e)}\n\n{traceback.format_exc()}")

    def _export_image(self):
        """Export an ee.Image or ee.ImageCollection as COG."""
        import sys
        import ee

        try:
            import xarray as xr
            import xee
        except ImportError as e:
            raise ImportError(
                f"Required packages not available: {e}\n"
                "Please install xarray and xee: pip install xarray xee"
            )

        self.progress.emit("Opening dataset with xee...")

        # Convert ImageCollection to Image if needed
        ee_object = self.ee_object
        type_name = type(ee_object).__name__
        if isinstance(ee_object, ee.ImageCollection) or type_name == "ImageCollection":
            ee_object = ee_object.mosaic()

        # Clip to region
        ee_object = ee_object.clip(self.region)

        # Open with xee
        ds = xr.open_dataset(
            ee_object,
            engine=xee.EarthEngineBackendEntrypoint,
            crs=self.crs,
            scale=self.scale,
            geometry=self.region,
        )

        self.progress.emit("Processing dataset...")

        # Ensure output has .tif extension
        output_path = self.output_path
        if not output_path.lower().endswith(".tif"):
            output_path += ".tif"

        # Write as COG using rioxarray
        try:
            import rioxarray  # noqa: F401
        except ImportError:
            raise ImportError(
                "rioxarray is required for COG export.\n"
                "Please install it: pip install rioxarray"
            )

        # Handle xee dimension naming for rioxarray
        rename_dims = {}
        for old_x in ["X", "lon", "longitude"]:
            if old_x in ds.dims:
                rename_dims[old_x] = "x"
                break
        for old_y in ["Y", "lat", "latitude"]:
            if old_y in ds.dims:
                rename_dims[old_y] = "y"
                break
        if rename_dims:
            ds = ds.rename(rename_dims)

        # Drop time dimension if present
        if "time" in ds.dims:
            ds = ds.isel(time=0)

        # Verify spatial dims exist
        if "x" not in ds.dims or "y" not in ds.dims:
            raise ValueError(
                f"Could not find spatial dimensions. Available dims: {list(ds.dims)}"
            )

        # Set CRS and spatial dims
        ds = ds.rio.write_crs(self.crs)
        ds = ds.rio.set_spatial_dims(x_dim="x", y_dim="y")

        # Get data variables
        data_vars = list(ds.data_vars)
        if not data_vars:
            raise ValueError("No data variables found in the dataset")

        self.progress.emit("Writing COG file...")

        # Export to COG
        if len(data_vars) > 1:
            import numpy as np

            arrays = []
            for var in data_vars:
                da = ds[var]
                if da.dims != ("y", "x"):
                    da = da.transpose("y", "x")
                arrays.append(da.values)

            stacked = np.stack(arrays, axis=0)

            da = xr.DataArray(
                stacked,
                dims=["band", "y", "x"],
                coords={
                    "band": list(range(1, len(data_vars) + 1)),
                    "y": ds.y,
                    "x": ds.x,
                },
            )
            da = da.rio.write_crs(self.crs)
            da = da.rio.set_spatial_dims(x_dim="x", y_dim="y")
            da.rio.to_raster(output_path, driver="COG")
        else:
            da = ds[data_vars[0]]
            if da.dims != ("y", "x"):
                da = da.transpose("y", "x")
            da.rio.to_raster(output_path, driver="COG")

        self.finished.emit(output_path)

    def _export_features(self):
        """Export an ee.FeatureCollection or ee.Feature."""
        import ee

        self.progress.emit("Filtering features by region...")

        # Convert Feature to FeatureCollection if needed
        ee_object = self.ee_object
        type_name = type(ee_object).__name__
        if isinstance(ee_object, ee.Feature) or type_name == "Feature":
            ee_object = ee.FeatureCollection([ee_object])

        # Filter by region
        ee_object = ee_object.filterBounds(self.region)

        self.progress.emit("Fetching features from Earth Engine...")

        # Format mapping
        format_map = {
            "GeoJSON": ("GeoJSON", ".geojson"),
            "GPKG (GeoPackage)": ("GPKG", ".gpkg"),
            "ESRI Shapefile": ("ESRI Shapefile", ".shp"),
            "FlatGeobuf": ("FlatGeobuf", ".fgb"),
            "Parquet (GeoParquet)": ("Parquet", ".parquet"),
            "GeoJSONSeq": ("GeoJSONSeq", ".geojsonl"),
            "CSV": ("CSV", ".csv"),
            "KML": ("KML", ".kml"),
            "GML": ("GML", ".gml"),
        }

        driver, ext = format_map.get(self.vector_format, ("GeoJSON", ".geojson"))

        output_path = self.output_path
        if not output_path.lower().endswith(ext):
            output_path += ext

        try:
            import geopandas as gpd
        except ImportError:
            raise ImportError(
                "geopandas is required for vector export.\n"
                "Please install it: pip install geopandas"
            )

        try:
            gdf = ee.data.computeFeatures(
                {
                    "expression": ee_object,
                    "fileFormat": "GEOPANDAS_GEODATAFRAME",
                }
            )
        except Exception:
            self.progress.emit("Fetching features (fallback method)...")
            result = ee_object.getInfo()
            if "features" in result:
                gdf = gpd.GeoDataFrame.from_features(result["features"])
            else:
                raise RuntimeError("Failed to get features from Earth Engine")

        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")

        self.progress.emit("Writing output file...")

        if self.vector_format == "GeoJSON":
            gdf.to_file(output_path, driver="GeoJSON")
        elif driver == "Parquet":
            gdf.to_parquet(output_path)
        else:
            gdf.to_file(output_path, driver=driver)

        self.finished.emit(output_path)


class InspectorMapTool:
    """Map tool for clicking to inspect Earth Engine data."""

    def __init__(self, iface, inspector_callback):
        """Initialize the map tool.

        Args:
            iface: QGIS interface instance.
            inspector_callback: Function to call with (lon, lat) when map is clicked.
        """
        from qgis.gui import QgsMapTool
        from qgis.PyQt.QtCore import Qt

        class ClickTool(QgsMapTool):
            def __init__(self, canvas, callback):
                super().__init__(canvas)
                self.callback = callback
                self.setCursor(Qt.CrossCursor)

            def canvasReleaseEvent(self, event):
                # Get click coordinates
                point = self.toMapCoordinates(event.pos())

                # Transform to EPSG:4326
                from qgis.core import (
                    QgsCoordinateReferenceSystem,
                    QgsCoordinateTransform,
                    QgsProject,
                )

                map_crs = self.canvas().mapSettings().destinationCrs()
                wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")

                if map_crs.authid() != "EPSG:4326":
                    transform = QgsCoordinateTransform(
                        map_crs, wgs84, QgsProject.instance()
                    )
                    point = transform.transform(point)

                self.callback(point.x(), point.y())

        self.tool = ClickTool(iface.mapCanvas(), inspector_callback)

    def activate(self):
        """Activate the map tool."""
        from qgis.utils import iface

        iface.mapCanvas().setMapTool(self.tool)

    def deactivate(self):
        """Deactivate the map tool."""
        from qgis.utils import iface

        iface.mapCanvas().unsetMapTool(self.tool)


class CatalogDockWidget(QDockWidget):
    """Main catalog browser panel for GEE datasets."""

    def __init__(self, iface, parent=None):
        """Initialize the dock widget.

        Args:
            iface: QGIS interface instance.
            parent: Parent widget.
        """
        super().__init__("GEE Data Catalogs", parent)
        self.iface = iface
        self._selected_dataset = None
        self._catalog_thread = None
        self._image_list_thread = None
        self._preview_thread = None
        self._thumbnail_thread = None
        self._current_collection = None
        self._filtered_collection = None
        self._current_info_html = ""
        self._inspector_thread = None
        self._inspector_map_tool = None
        self._inspector_active = False
        self._js_code_cache = None  # Cache for f.json JavaScript code snippets

        # Time series related attributes
        self._timeseries_thread = None
        self._timeseries_images = []
        self._timeseries_labels = []
        self._timeseries_collection = None
        self._timeseries_vis_params = {}
        self._timeseries_timer = None
        self._timeseries_playing = False
        self._timeseries_current_index = 0

        # Drawn bounding box storage
        self._ts_drawn_bbox = None  # [west, south, east, north]
        self._load_drawn_bbox = None
        self._bbox_drawing_mode = None  # 'ts' or 'load'
        self._bbox_rubber_band = None
        self._bbox_map_tool = None

        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setMinimumWidth(380)

        self._setup_ui()
        self._start_catalog_load()

    def _setup_ui(self):
        """Set up the dock widget UI."""
        # Main widget
        main_widget = QWidget()
        self.setWidget(main_widget)

        # Main layout
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(8)

        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("Earth Engine Data Catalogs")
        header_font = QFont()
        header_font.setPointSize(12)
        header_font.setBold(True)
        header_label.setFont(header_font)
        header_layout.addWidget(header_label)

        # Refresh button
        self.refresh_btn = QPushButton("↻ Refresh")
        self.refresh_btn.setMaximumWidth(80)
        self.refresh_btn.clicked.connect(self._refresh_catalog)
        header_layout.addWidget(self.refresh_btn)

        layout.addLayout(header_layout)

        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tab_widget)

        # Browse tab
        browse_tab = self._create_browse_tab()
        self.tab_widget.addTab(browse_tab, "Browse")

        # Search tab
        search_tab = self._create_search_tab()
        self.tab_widget.addTab(search_tab, "Search")

        # Time Series tab
        timeseries_tab = self._create_timeseries_tab()
        self.tab_widget.addTab(timeseries_tab, "Time Series")

        # Load tab
        load_tab = self._create_load_tab()
        self.tab_widget.addTab(load_tab, "Load")

        # Code tab
        code_tab = self._create_code_tab()
        self.tab_widget.addTab(code_tab, "Code")

        # Conversion tab
        conversion_tab = self._create_conversion_tab()
        self.tab_widget.addTab(conversion_tab, "Conversion")

        # Inspector tab
        inspector_tab = self._create_inspector_tab()
        self.tab_widget.addTab(inspector_tab, "Inspector")

        # Export tab
        export_tab = self._create_export_tab()
        self.tab_widget.addTab(export_tab, "Export")

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Loading catalogs...")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.status_label)

    def _get_map_extent_wgs84(self):
        """Get the current map extent in WGS84 (EPSG:4326) coordinates.

        Returns:
            List of [west, south, east, north] in EPSG:4326, or None if error.
        """
        try:
            from qgis.core import (
                QgsCoordinateReferenceSystem,
                QgsCoordinateTransform,
                QgsProject,
                QgsPointXY,
            )

            extent = self.iface.mapCanvas().extent()
            map_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
            wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")

            # Transform extent to WGS84 if needed
            if map_crs.authid() != "EPSG:4326":
                transform = QgsCoordinateTransform(
                    map_crs, wgs84, QgsProject.instance()
                )
                # Transform the corner points
                sw_point = transform.transform(
                    QgsPointXY(extent.xMinimum(), extent.yMinimum())
                )
                ne_point = transform.transform(
                    QgsPointXY(extent.xMaximum(), extent.yMaximum())
                )
                return [sw_point.x(), sw_point.y(), ne_point.x(), ne_point.y()]
            else:
                return [
                    extent.xMinimum(),
                    extent.yMinimum(),
                    extent.xMaximum(),
                    extent.yMaximum(),
                ]
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error getting map extent in WGS84: {e}",
                "GEE Data Catalogs",
                Qgis.Warning,
            )
            return None

    def _get_cloud_property(self, asset_id: str, custom_property: str = None) -> str:
        """Determine the correct cloud cover property based on the asset ID.

        Args:
            asset_id: The Earth Engine asset ID.
            custom_property: Optional custom property name provided by user.

        Returns:
            The cloud cover property name for the dataset.
        """
        # Use custom property if provided
        if custom_property and custom_property.strip():
            return custom_property.strip()

        asset_upper = asset_id.upper()

        # Landsat collections use CLOUD_COVER
        if "LANDSAT" in asset_upper:
            return "CLOUD_COVER"

        # NASA HLS uses CLOUD_COVERAGE
        if "NASA/HLS" in asset_upper or "HLS" in asset_upper:
            return "CLOUD_COVERAGE"

        # MODIS uses different properties but typically doesn't have per-scene cloud
        if "MODIS" in asset_upper:
            return "CLOUD_COVER"

        # Sentinel-2 uses CLOUDY_PIXEL_PERCENTAGE
        if "SENTINEL" in asset_upper or "COPERNICUS/S2" in asset_upper:
            return "CLOUDY_PIXEL_PERCENTAGE"

        # Default to CLOUDY_PIXEL_PERCENTAGE (most common for optical imagery)
        return "CLOUDY_PIXEL_PERCENTAGE"

    def _parse_property_filters(self, filter_text: str) -> list:
        """Parse property filter text into a list of filter specifications.

        Args:
            filter_text: Multi-line text with filters like "PROPERTY > value"

        Returns:
            List of tuples: [(property_name, operator, value), ...]
        """
        import re

        filters = []
        if not filter_text or not filter_text.strip():
            return filters

        # Regex to match: property operator value
        pattern = re.compile(r"^\s*(\S+)\s*(==|!=|>=|<=|>|<)\s*(.+?)\s*$")

        for line in filter_text.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            match = pattern.match(line)
            if not match:
                continue

            prop_name, op, value_str = match.groups()
            value_str = value_str.strip()

            # Try to convert value to appropriate type
            try:
                # Try as float first
                value = float(value_str)
                if value.is_integer():
                    value = int(value)
            except ValueError:
                # Keep as string (strip quotes if present)
                value = value_str.strip("\"'")

            filters.append((prop_name, op, value))
        return filters

    def _apply_property_filters(self, collection, filters: list):
        """Apply property filters to an ImageCollection.

        Args:
            collection: ee.ImageCollection
            filters: List of (property_name, operator, value) tuples

        Returns:
            Filtered collection
        """
        if not filters:
            return collection

        for prop_name, op, value in filters:
            if op == "==":
                collection = collection.filter(ee.Filter.eq(prop_name, value))
            elif op == "!=":
                collection = collection.filter(ee.Filter.neq(prop_name, value))
            elif op == ">":
                collection = collection.filter(ee.Filter.gt(prop_name, value))
            elif op == ">=":
                collection = collection.filter(ee.Filter.gte(prop_name, value))
            elif op == "<":
                collection = collection.filter(ee.Filter.lt(prop_name, value))
            elif op == "<=":
                collection = collection.filter(ee.Filter.lte(prop_name, value))

        return collection

    def _start_draw_bbox_ts(self):
        """Start drawing bounding box for Time Series tab."""
        self._bbox_drawing_mode = "ts"
        self._start_bbox_drawing()

    def _start_draw_bbox_load(self):
        """Start drawing bounding box for Load tab."""
        self._bbox_drawing_mode = "load"
        self._start_bbox_drawing()

    def _start_bbox_drawing(self):
        """Start the bounding box drawing tool."""
        from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand
        from qgis.core import QgsWkbTypes, QgsPointXY, QgsRectangle
        from qgis.PyQt.QtGui import QColor
        from qgis.PyQt.QtCore import Qt

        canvas = self.iface.mapCanvas()
        dock_widget = self

        # Create a custom rectangle drawing tool with red outline
        class BBoxDrawTool(QgsMapToolEmitPoint):
            def __init__(self, canvas, callback):
                super().__init__(canvas)
                self.canvas = canvas
                self.callback = callback
                self.rubberBand = None
                self.startPoint = None
                self.endPoint = None
                self.isDrawing = False

            def canvasPressEvent(self, event):
                self.startPoint = self.toMapCoordinates(event.pos())
                self.endPoint = self.startPoint
                self.isDrawing = True
                self._showRubberBand()

            def canvasMoveEvent(self, event):
                if not self.isDrawing:
                    return
                self.endPoint = self.toMapCoordinates(event.pos())
                self._showRubberBand()

            def canvasReleaseEvent(self, event):
                self.isDrawing = False
                if self.startPoint and self.endPoint:
                    rect = QgsRectangle(self.startPoint, self.endPoint)
                    if rect.width() > 0 and rect.height() > 0:
                        self.callback(rect)
                    else:
                        QMessageBox.warning(
                            dock_widget,
                            "Invalid rectangle",
                            "Please draw a valid rectangle by clicking and dragging on the map.",
                        )
                self._hideRubberBand()

            def _showRubberBand(self):
                if self.rubberBand is None:
                    self.rubberBand = QgsRubberBand(
                        self.canvas, QgsWkbTypes.PolygonGeometry
                    )
                    self.rubberBand.setColor(QColor(255, 0, 0, 50))  # Light red fill
                    self.rubberBand.setStrokeColor(
                        QColor(255, 0, 0, 255)
                    )  # Red outline
                    self.rubberBand.setWidth(2)

                self.rubberBand.reset(QgsWkbTypes.PolygonGeometry)
                if self.startPoint and self.endPoint:
                    point1 = QgsPointXY(self.startPoint.x(), self.startPoint.y())
                    point2 = QgsPointXY(self.endPoint.x(), self.startPoint.y())
                    point3 = QgsPointXY(self.endPoint.x(), self.endPoint.y())
                    point4 = QgsPointXY(self.startPoint.x(), self.endPoint.y())
                    self.rubberBand.addPoint(point1, False)
                    self.rubberBand.addPoint(point2, False)
                    self.rubberBand.addPoint(point3, False)
                    self.rubberBand.addPoint(point4, True)
                    self.rubberBand.show()

            def _hideRubberBand(self):
                if self.rubberBand:
                    self.rubberBand.hide()
                    self.canvas.scene().removeItem(self.rubberBand)
                    self.rubberBand = None

            def deactivate(self):
                self._hideRubberBand()
                super().deactivate()

        self._bbox_map_tool = BBoxDrawTool(canvas, self._on_bbox_drawn)
        canvas.setMapTool(self._bbox_map_tool)

        # Update status
        if self._bbox_drawing_mode == "ts":
            self.ts_bbox_label.setText("Draw a rectangle on the map...")
            self.ts_bbox_label.setStyleSheet("color: #ffaa00; font-size: 9px;")
        else:
            self.load_bbox_label.setText("Draw a rectangle on the map...")
            self.load_bbox_label.setStyleSheet("color: #ffaa00; font-size: 9px;")

    def _on_bbox_drawn(self, extent):
        """Handle drawn bounding box extent."""
        from qgis.core import (
            QgsCoordinateReferenceSystem,
            QgsCoordinateTransform,
            QgsProject,
            QgsPointXY,
        )

        try:
            # Transform to WGS84
            map_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
            wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")

            if map_crs.authid() != "EPSG:4326":
                transform = QgsCoordinateTransform(
                    map_crs, wgs84, QgsProject.instance()
                )
                sw_point = transform.transform(
                    QgsPointXY(extent.xMinimum(), extent.yMinimum())
                )
                ne_point = transform.transform(
                    QgsPointXY(extent.xMaximum(), extent.yMaximum())
                )
                bbox = [sw_point.x(), sw_point.y(), ne_point.x(), ne_point.y()]
            else:
                bbox = [
                    extent.xMinimum(),
                    extent.yMinimum(),
                    extent.xMaximum(),
                    extent.yMaximum(),
                ]

            # Store the bbox
            if self._bbox_drawing_mode == "ts":
                self._ts_drawn_bbox = bbox
                self.ts_bbox_label.setText(
                    f"Bounds: [{bbox[0]:.4f}, {bbox[1]:.4f}, {bbox[2]:.4f}, {bbox[3]:.4f}]"
                )
                self.ts_bbox_label.setStyleSheet("color: #00cc66; font-size: 9px;")
                self.ts_clear_bbox_btn.setEnabled(True)
            else:
                self._load_drawn_bbox = bbox
                self.load_bbox_label.setText(
                    f"Bounds: [{bbox[0]:.4f}, {bbox[1]:.4f}, {bbox[2]:.4f}, {bbox[3]:.4f}]"
                )
                self.load_bbox_label.setStyleSheet("color: #00cc66; font-size: 9px;")
                self.load_clear_bbox_btn.setEnabled(True)

            # Restore previous map tool
            self.iface.mapCanvas().unsetMapTool(self._bbox_map_tool)

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error drawing bounding box: {e}",
                "GEE Data Catalogs",
                Qgis.Warning,
            )

    def _clear_drawn_bbox_ts(self):
        """Clear the drawn bounding box for Time Series tab."""
        self._ts_drawn_bbox = None
        self.ts_bbox_label.setText("")
        self.ts_clear_bbox_btn.setEnabled(False)

    def _clear_drawn_bbox_load(self):
        """Clear the drawn bounding box for Load tab."""
        self._load_drawn_bbox = None
        self.load_bbox_label.setText("")
        self.load_clear_bbox_btn.setEnabled(False)

    def _get_spatial_filter_ts(self):
        """Get the spatial filter for Time Series tab.

        Returns:
            List [west, south, east, north] or None
        """
        if self.ts_spatial_extent.isChecked():
            return self._get_map_extent_wgs84()
        elif self.ts_spatial_draw.isChecked() and self._ts_drawn_bbox:
            return self._ts_drawn_bbox
        return None

    def _get_spatial_filter_load(self):
        """Get the spatial filter for Load tab.

        Returns:
            List [west, south, east, north] or None
        """
        if self.load_spatial_extent.isChecked():
            return self._get_map_extent_wgs84()
        elif self.load_spatial_draw.isChecked() and self._load_drawn_bbox:
            return self._load_drawn_bbox
        return None

    def _create_browse_tab(self):
        """Create the browse tab with category tree."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Source filter
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("Source:"))
        self.source_filter = QComboBox()
        self.source_filter.addItem("All Catalogs", None)
        self.source_filter.addItem("Official GEE Data Catalog", "official")
        self.source_filter.addItem("Community Catalog", "community")
        self.source_filter.currentIndexChanged.connect(self._filter_tree_by_source)
        source_layout.addWidget(self.source_filter)
        layout.addLayout(source_layout)

        # Splitter for tree and details
        splitter = QSplitter(Qt.Vertical)
        layout.addWidget(splitter)

        # Category tree
        self.catalog_tree = QTreeWidget()
        self.catalog_tree.setHeaderLabels(["Dataset", "Type", "Source"])
        self.catalog_tree.setAlternatingRowColors(True)
        self.catalog_tree.setColumnWidth(0, 220)
        self.catalog_tree.setColumnWidth(1, 100)
        self.catalog_tree.setColumnWidth(2, 80)
        self.catalog_tree.itemClicked.connect(self._on_dataset_selected)
        self.catalog_tree.itemDoubleClicked.connect(self._on_dataset_double_clicked)
        splitter.addWidget(self.catalog_tree)

        # Dataset info panel
        info_group = QGroupBox("Dataset Information")
        info_layout = QVBoxLayout(info_group)

        self.info_text = QTextBrowser()
        self.info_text.setReadOnly(True)
        self.info_text.setPlaceholderText("Select a dataset to view details...")
        self.info_text.setOpenExternalLinks(True)
        info_layout.addWidget(self.info_text)

        # Add to Map button
        btn_layout = QHBoxLayout()
        self.add_map_btn = QPushButton("Add to Map")
        self.add_map_btn.setEnabled(False)
        self.add_map_btn.clicked.connect(self._add_selected_to_map)
        btn_layout.addWidget(self.add_map_btn)

        self.configure_btn = QPushButton("Configure && Add")
        self.configure_btn.setEnabled(False)
        self.configure_btn.clicked.connect(self._configure_and_add)
        btn_layout.addWidget(self.configure_btn)

        info_layout.addLayout(btn_layout)

        # Second row of buttons for Time Series
        btn_layout2 = QHBoxLayout()
        self.timeseries_btn = QPushButton("📈 Time Series")
        self.timeseries_btn.setEnabled(False)
        self.timeseries_btn.setToolTip(
            "Configure and create time series from this dataset"
        )
        self.timeseries_btn.clicked.connect(self._configure_timeseries)
        btn_layout2.addWidget(self.timeseries_btn)
        info_layout.addLayout(btn_layout2)

        splitter.addWidget(info_group)

        splitter.setSizes([300, 200])

        return widget

    def _create_search_tab(self):
        """Create the search tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Search box
        search_group = QGroupBox("Search Datasets")
        search_layout = QFormLayout(search_group)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter keywords...")
        self.search_input.returnPressed.connect(self._perform_search)
        search_layout.addRow("Keywords:", self.search_input)

        # Category filter
        self.category_filter = QComboBox()
        self.category_filter.addItem("All Categories", None)
        search_layout.addRow("Category:", self.category_filter)

        # Type filter
        self.type_filter = QComboBox()
        self.type_filter.addItem("All Types", None)
        self.type_filter.addItem("Image", "Image")
        self.type_filter.addItem("ImageCollection", "ImageCollection")
        self.type_filter.addItem("FeatureCollection", "FeatureCollection")
        search_layout.addRow("Type:", self.type_filter)

        # Source filter for search
        self.search_source_filter = QComboBox()
        self.search_source_filter.addItem("All Sources", None)
        self.search_source_filter.addItem("Official", "official")
        self.search_source_filter.addItem("Community", "community")
        search_layout.addRow("Source:", self.search_source_filter)

        # Search button
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._perform_search)
        search_layout.addRow("", search_btn)

        layout.addWidget(search_group)

        # Splitter for results and details
        splitter = QSplitter(Qt.Vertical)
        layout.addWidget(splitter)

        # Results
        self.search_results = QTreeWidget()
        self.search_results.setHeaderLabels(["Dataset", "Type", "Source"])
        self.search_results.setAlternatingRowColors(True)
        self.search_results.setColumnWidth(0, 200)
        self.search_results.itemClicked.connect(self._on_search_result_selected)
        self.search_results.itemDoubleClicked.connect(
            self._on_search_result_double_clicked
        )
        splitter.addWidget(self.search_results)

        # Dataset info panel for search results
        search_info_group = QGroupBox("Dataset Information")
        search_info_layout = QVBoxLayout(search_info_group)

        self.search_info_text = QTextBrowser()
        self.search_info_text.setReadOnly(True)
        self.search_info_text.setPlaceholderText(
            "Select a search result to view details..."
        )
        self.search_info_text.setOpenExternalLinks(True)
        search_info_layout.addWidget(self.search_info_text)

        # Add buttons
        search_btn_layout = QHBoxLayout()

        add_result_btn = QPushButton("Add to Map")
        add_result_btn.clicked.connect(self._add_search_result_to_map)
        search_btn_layout.addWidget(add_result_btn)

        self.search_configure_btn = QPushButton("Configure && Add")
        self.search_configure_btn.clicked.connect(self._configure_search_result)
        search_btn_layout.addWidget(self.search_configure_btn)

        search_info_layout.addLayout(search_btn_layout)

        # Second row of buttons for Time Series
        search_btn_layout2 = QHBoxLayout()
        self.search_timeseries_btn = QPushButton("📈 Time Series")
        self.search_timeseries_btn.setEnabled(False)
        self.search_timeseries_btn.setToolTip(
            "Configure and create time series from this dataset"
        )
        self.search_timeseries_btn.clicked.connect(self._configure_search_timeseries)
        search_btn_layout2.addWidget(self.search_timeseries_btn)
        search_info_layout.addLayout(search_btn_layout2)

        splitter.addWidget(search_info_group)

        splitter.setSizes([250, 250])

        return widget

    def _create_timeseries_tab(self):
        """Create the Time Series tab for creating and visualizing time series."""
        widget = QWidget()

        # Scroll area for many options
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)

        # Dataset ID input group
        id_group = QGroupBox("Dataset")
        id_layout = QFormLayout(id_group)

        self.ts_dataset_id_input = QLineEdit()
        self.ts_dataset_id_input.setPlaceholderText("e.g., COPERNICUS/S2_SR_HARMONIZED")
        id_layout.addRow("Asset ID:", self.ts_dataset_id_input)

        self.ts_layer_name_input = QLineEdit()
        self.ts_layer_name_input.setPlaceholderText("Time series layer name")
        self.ts_layer_name_input.setText("Time Series")
        id_layout.addRow("Layer Name:", self.ts_layer_name_input)

        layout.addWidget(id_group)

        # Date range group
        date_group = QGroupBox("Date Range")
        date_layout = QFormLayout(date_group)

        today = datetime.now()
        one_year_ago = today - timedelta(days=365)

        self.ts_start_date = QDateEdit()
        self.ts_start_date.setDate(one_year_ago)
        self.ts_start_date.setCalendarPopup(True)
        self.ts_start_date.setDisplayFormat("yyyy-MM-dd")
        date_layout.addRow("Start Date:", self.ts_start_date)

        self.ts_end_date = QDateEdit()
        self.ts_end_date.setDate(today)
        self.ts_end_date.setCalendarPopup(True)
        self.ts_end_date.setDisplayFormat("yyyy-MM-dd")
        date_layout.addRow("End Date:", self.ts_end_date)

        layout.addWidget(date_group)

        # Filters group
        filters_group = QGroupBox("Filters")
        filters_layout = QFormLayout(filters_group)

        # Cloud cover
        cloud_layout = QHBoxLayout()
        self.ts_cloud_cover_spin = QSpinBox()
        self.ts_cloud_cover_spin.setRange(0, 100)
        self.ts_cloud_cover_spin.setValue(20)
        self.ts_cloud_cover_spin.setSuffix("%")
        cloud_layout.addWidget(self.ts_cloud_cover_spin)

        self.ts_cloud_property_input = QLineEdit()
        self.ts_cloud_property_input.setPlaceholderText("Property name (auto-detect)")
        self.ts_cloud_property_input.setToolTip(
            "Cloud cover property name. Leave empty for auto-detection.\n"
            "Examples: CLOUDY_PIXEL_PERCENTAGE (Sentinel), CLOUD_COVER (Landsat),\n"
            "CLOUD_COVERAGE (HLS)"
        )
        cloud_layout.addWidget(self.ts_cloud_property_input)
        filters_layout.addRow("Max Cloud Cover:", cloud_layout)

        self.ts_use_cloud_filter = QCheckBox("Apply cloud filter")
        self.ts_use_cloud_filter.setChecked(False)
        filters_layout.addRow("", self.ts_use_cloud_filter)

        # Spatial filter options
        spatial_group = QGroupBox("Spatial Filter")
        spatial_layout = QVBoxLayout(spatial_group)

        self.ts_spatial_none = QRadioButton("No spatial filter")
        self.ts_spatial_none.setChecked(True)
        spatial_layout.addWidget(self.ts_spatial_none)

        self.ts_spatial_extent = QRadioButton("Use current map extent")
        spatial_layout.addWidget(self.ts_spatial_extent)

        draw_bbox_layout = QHBoxLayout()
        self.ts_spatial_draw = QRadioButton("Draw bounding box")
        draw_bbox_layout.addWidget(self.ts_spatial_draw)
        self.ts_draw_bbox_btn = QPushButton("□ Draw")
        self.ts_draw_bbox_btn.setMaximumWidth(70)
        self.ts_draw_bbox_btn.setEnabled(False)
        self.ts_draw_bbox_btn.clicked.connect(self._start_draw_bbox_ts)
        draw_bbox_layout.addWidget(self.ts_draw_bbox_btn)
        self.ts_clear_bbox_btn = QPushButton("Clear")
        self.ts_clear_bbox_btn.setMaximumWidth(50)
        self.ts_clear_bbox_btn.setEnabled(False)
        self.ts_clear_bbox_btn.clicked.connect(self._clear_drawn_bbox_ts)
        draw_bbox_layout.addWidget(self.ts_clear_bbox_btn)
        spatial_layout.addLayout(draw_bbox_layout)

        self.ts_bbox_label = QLabel("")
        self.ts_bbox_label.setStyleSheet("color: #aaaaaa; font-size: 9px;")
        self.ts_bbox_label.setWordWrap(True)
        spatial_layout.addWidget(self.ts_bbox_label)

        # Connect radio buttons to enable/disable draw button
        self.ts_spatial_draw.toggled.connect(
            lambda checked: self.ts_draw_bbox_btn.setEnabled(checked)
        )

        filters_layout.addRow(spatial_group)

        layout.addWidget(filters_group)

        # Property filters group
        prop_filter_group = QGroupBox("Property Filters (Optional)")
        prop_filter_layout = QVBoxLayout(prop_filter_group)

        prop_filter_help = QLabel(
            "Add custom property filters. One per line in format:\n"
            "property_name operator value (e.g., SUN_ELEVATION > 30)"
        )
        prop_filter_help.setStyleSheet("color: gray; font-size: 10px;")
        prop_filter_help.setWordWrap(True)
        prop_filter_layout.addWidget(prop_filter_help)

        self.ts_property_filters = QPlainTextEdit()
        self.ts_property_filters.setPlaceholderText(
            "SUN_ELEVATION > 30\nSUN_AZIMUTH < 180\nMGRS_TILE == 10SGD"
        )
        self.ts_property_filters.setMaximumHeight(80)
        prop_filter_layout.addWidget(self.ts_property_filters)

        # Operator reference
        operator_label = QLabel(
            "Operators: == (equals), != (not equals), < > <= >= (comparison)"
        )
        operator_label.setStyleSheet("color: gray; font-size: 9px;")
        prop_filter_layout.addWidget(operator_label)

        layout.addWidget(prop_filter_group)

        # Time series options group
        ts_options_group = QGroupBox("Time Series Options")
        ts_options_layout = QFormLayout(ts_options_group)

        # Temporal frequency
        self.ts_frequency_combo = QComboBox()
        self.ts_frequency_combo.addItems(["day", "week", "month", "quarter", "year"])
        self.ts_frequency_combo.setCurrentText("month")
        ts_options_layout.addRow("Frequency:", self.ts_frequency_combo)

        # Reducer method
        self.ts_reducer_combo = QComboBox()
        self.ts_reducer_combo.addItems(["median", "mean", "min", "max", "first", "sum"])
        self.ts_reducer_combo.setCurrentText("median")
        ts_options_layout.addRow("Reducer:", self.ts_reducer_combo)

        layout.addWidget(ts_options_group)

        # Visualization params group
        vis_group = QGroupBox("Visualization Parameters")
        vis_layout = QFormLayout(vis_group)

        self.ts_bands_input = QLineEdit()
        self.ts_bands_input.setPlaceholderText("e.g., B4,B3,B2 for RGB")
        vis_layout.addRow("Bands:", self.ts_bands_input)

        self.ts_vis_min_input = QLineEdit()
        self.ts_vis_min_input.setPlaceholderText("e.g., 0")
        vis_layout.addRow("Min:", self.ts_vis_min_input)

        self.ts_vis_max_input = QLineEdit()
        self.ts_vis_max_input.setPlaceholderText("e.g., 3000")
        vis_layout.addRow("Max:", self.ts_vis_max_input)

        self.ts_palette_input = QLineEdit()
        self.ts_palette_input.setPlaceholderText("e.g., blue,green,red or viridis")
        vis_layout.addRow("Palette:", self.ts_palette_input)

        layout.addWidget(vis_group)

        # Create time series button
        create_btn_layout = QHBoxLayout()
        self.ts_create_btn = QPushButton("▶ Create Time Series")
        self.ts_create_btn.clicked.connect(self._create_timeseries)
        create_btn_layout.addWidget(self.ts_create_btn)

        self.ts_preview_btn = QPushButton("Preview Info")
        self.ts_preview_btn.clicked.connect(self._preview_timeseries)
        create_btn_layout.addWidget(self.ts_preview_btn)

        layout.addLayout(create_btn_layout)

        # Time slider group
        slider_group = QGroupBox("Time Slider")
        slider_layout = QVBoxLayout(slider_group)

        # Current time label
        self.ts_current_label = QLabel("No time series loaded")
        self.ts_current_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.ts_current_label.setAlignment(Qt.AlignCenter)
        slider_layout.addWidget(self.ts_current_label)

        # Time slider
        self.ts_time_slider = QSlider(Qt.Horizontal)
        self.ts_time_slider.setMinimum(0)
        self.ts_time_slider.setMaximum(0)
        self.ts_time_slider.setValue(0)
        self.ts_time_slider.setEnabled(False)
        self.ts_time_slider.valueChanged.connect(self._on_timeslider_changed)
        slider_layout.addWidget(self.ts_time_slider)

        # Slider control buttons
        slider_btn_layout = QHBoxLayout()

        self.ts_prev_btn = QPushButton("◀ Prev")
        self.ts_prev_btn.setEnabled(False)
        self.ts_prev_btn.clicked.connect(self._timeseries_prev)
        slider_btn_layout.addWidget(self.ts_prev_btn)

        self.ts_play_btn = QPushButton("▶ Play")
        self.ts_play_btn.setEnabled(False)
        self.ts_play_btn.clicked.connect(self._timeseries_toggle_play)
        slider_btn_layout.addWidget(self.ts_play_btn)

        self.ts_next_btn = QPushButton("Next ▶")
        self.ts_next_btn.setEnabled(False)
        self.ts_next_btn.clicked.connect(self._timeseries_next)
        slider_btn_layout.addWidget(self.ts_next_btn)

        slider_layout.addLayout(slider_btn_layout)

        # Animation speed control
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("Speed:"))
        self.ts_speed_spin = QSpinBox()
        self.ts_speed_spin.setRange(500, 5000)
        self.ts_speed_spin.setValue(1000)
        self.ts_speed_spin.setSuffix(" ms")
        self.ts_speed_spin.setSingleStep(100)
        self.ts_speed_spin.valueChanged.connect(self._update_timeseries_timer_interval)
        speed_layout.addWidget(self.ts_speed_spin)

        self.ts_loop_check = QCheckBox("Loop")
        self.ts_loop_check.setChecked(True)
        speed_layout.addWidget(self.ts_loop_check)

        slider_layout.addLayout(speed_layout)

        layout.addWidget(slider_group)

        # Status/info area
        self.ts_info_label = QLabel("")
        self.ts_info_label.setWordWrap(True)
        self.ts_info_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.ts_info_label)

        # Copy code button
        copy_btn_layout = QHBoxLayout()
        self.ts_copy_code_btn = QPushButton("📋 Copy Code Snippet")
        self.ts_copy_code_btn.clicked.connect(self._copy_timeseries_code)
        self.ts_copy_code_btn.setToolTip(
            "Copy Python code for creating this time series"
        )
        copy_btn_layout.addWidget(self.ts_copy_code_btn)
        layout.addLayout(copy_btn_layout)

        layout.addStretch()

        scroll.setWidget(scroll_widget)

        # Return scroll area wrapped in widget
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(scroll)
        return container

    def _create_load_tab(self):
        """Create the load/filter tab."""
        widget = QWidget()

        # Scroll area for many options
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)

        # Dataset ID input
        id_group = QGroupBox("Dataset")
        id_layout = QFormLayout(id_group)

        self.dataset_id_input = QLineEdit()
        self.dataset_id_input.setPlaceholderText("e.g., LANDSAT/LC09/C02/T1_L2")
        id_layout.addRow("Asset ID:", self.dataset_id_input)

        self.layer_name_input = QLineEdit()
        self.layer_name_input.setPlaceholderText("Layer name (optional)")
        id_layout.addRow("Layer Name:", self.layer_name_input)

        layout.addWidget(id_group)

        # Filters group
        filters_group = QGroupBox("Filters (for ImageCollections)")
        filters_layout = QFormLayout(filters_group)

        # Date range
        today = datetime.now()
        one_year_ago = today - timedelta(days=365)

        self.start_date = QDateEdit()
        self.start_date.setDate(one_year_ago)
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        filters_layout.addRow("Start Date:", self.start_date)

        self.end_date = QDateEdit()
        self.end_date.setDate(today)
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        filters_layout.addRow("End Date:", self.end_date)

        self.use_date_filter = QCheckBox("Apply date filter")
        self.use_date_filter.setChecked(False)
        filters_layout.addRow("", self.use_date_filter)

        # Cloud cover with property name input
        cloud_layout = QHBoxLayout()
        self.cloud_cover_spin = QSpinBox()
        self.cloud_cover_spin.setRange(0, 100)
        self.cloud_cover_spin.setValue(20)
        self.cloud_cover_spin.setSuffix("%")
        cloud_layout.addWidget(self.cloud_cover_spin)

        self.cloud_property_input = QLineEdit()
        self.cloud_property_input.setPlaceholderText("Property name (auto-detect)")
        self.cloud_property_input.setToolTip(
            "Cloud cover property name. Leave empty for auto-detection.\n"
            "Examples: CLOUDY_PIXEL_PERCENTAGE (Sentinel), CLOUD_COVER (Landsat),\n"
            "CLOUD_COVERAGE (HLS)"
        )
        cloud_layout.addWidget(self.cloud_property_input)
        filters_layout.addRow("Max Cloud Cover:", cloud_layout)

        self.use_cloud_filter = QCheckBox("Apply cloud filter")
        self.use_cloud_filter.setChecked(False)
        filters_layout.addRow("", self.use_cloud_filter)

        # Spatial filter options
        spatial_group = QGroupBox("Spatial Filter")
        spatial_layout = QVBoxLayout(spatial_group)

        self.load_spatial_none = QRadioButton("No spatial filter")
        self.load_spatial_none.setChecked(True)
        spatial_layout.addWidget(self.load_spatial_none)

        self.load_spatial_extent = QRadioButton("Use current map extent")
        spatial_layout.addWidget(self.load_spatial_extent)

        draw_bbox_layout = QHBoxLayout()
        self.load_spatial_draw = QRadioButton("Draw bounding box")
        draw_bbox_layout.addWidget(self.load_spatial_draw)
        self.load_draw_bbox_btn = QPushButton("□ Draw")
        self.load_draw_bbox_btn.setMaximumWidth(70)
        self.load_draw_bbox_btn.setEnabled(False)
        self.load_draw_bbox_btn.clicked.connect(self._start_draw_bbox_load)
        draw_bbox_layout.addWidget(self.load_draw_bbox_btn)
        self.load_clear_bbox_btn = QPushButton("Clear")
        self.load_clear_bbox_btn.setMaximumWidth(50)
        self.load_clear_bbox_btn.setEnabled(False)
        self.load_clear_bbox_btn.clicked.connect(self._clear_drawn_bbox_load)
        draw_bbox_layout.addWidget(self.load_clear_bbox_btn)
        spatial_layout.addLayout(draw_bbox_layout)

        self.load_bbox_label = QLabel("")
        self.load_bbox_label.setStyleSheet("color: #aaaaaa; font-size: 9px;")
        self.load_bbox_label.setWordWrap(True)
        spatial_layout.addWidget(self.load_bbox_label)

        # Connect radio buttons to enable/disable draw button
        self.load_spatial_draw.toggled.connect(
            lambda checked: self.load_draw_bbox_btn.setEnabled(checked)
        )

        filters_layout.addRow(spatial_group)

        layout.addWidget(filters_group)

        # Property filters group
        prop_filter_group = QGroupBox("Property Filters (Optional)")
        prop_filter_layout = QVBoxLayout(prop_filter_group)

        prop_filter_help = QLabel(
            "Add custom property filters. One per line in format:\n"
            "property_name operator value (e.g., SUN_ELEVATION > 30)"
        )
        prop_filter_help.setStyleSheet("color: gray; font-size: 10px;")
        prop_filter_help.setWordWrap(True)
        prop_filter_layout.addWidget(prop_filter_help)

        self.load_property_filters = QPlainTextEdit()
        self.load_property_filters.setPlaceholderText(
            "SUN_ELEVATION > 30\nSUN_AZIMUTH < 180"
        )
        self.load_property_filters.setMaximumHeight(80)
        prop_filter_layout.addWidget(self.load_property_filters)

        # Operator reference
        operator_label = QLabel(
            "Operators: == (equals), != (not equals), < > <= >= (comparison)"
        )
        operator_label.setStyleSheet("color: gray; font-size: 9px;")
        prop_filter_layout.addWidget(operator_label)

        layout.addWidget(prop_filter_group)

        # Image selection group (for ImageCollections)
        image_group = QGroupBox("Image Selection (for ImageCollections)")
        image_layout = QVBoxLayout(image_group)

        # Radio buttons for selection mode
        self.load_mode_group = QButtonGroup()

        self.load_mosaic_radio = QRadioButton("Load as composite (mosaic/median/mean)")
        self.load_mosaic_radio.setChecked(True)
        self.load_mode_group.addButton(self.load_mosaic_radio, 0)
        image_layout.addWidget(self.load_mosaic_radio)

        self.load_individual_radio = QRadioButton("Select individual image(s)")
        self.load_mode_group.addButton(self.load_individual_radio, 1)
        image_layout.addWidget(self.load_individual_radio)

        # Aggregation method (for mosaic mode)
        agg_layout = QHBoxLayout()
        agg_layout.addWidget(QLabel("Composite Method:"))
        self.agg_method = QComboBox()
        self.agg_method.addItems(["mosaic", "median", "mean", "min", "max", "first"])
        agg_layout.addWidget(self.agg_method)
        image_layout.addLayout(agg_layout)

        # Image list (for individual mode)
        self.image_list_widget = QListWidget()
        self.image_list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        self.image_list_widget.setMaximumHeight(150)
        self.image_list_widget.setVisible(False)
        image_layout.addWidget(self.image_list_widget)

        # Fetch images button
        fetch_layout = QHBoxLayout()
        self.fetch_images_btn = QPushButton("Fetch Available Images")
        self.fetch_images_btn.clicked.connect(self._fetch_images)
        self.fetch_images_btn.setVisible(False)
        fetch_layout.addWidget(self.fetch_images_btn)

        self.image_limit_spin = QSpinBox()
        self.image_limit_spin.setRange(10, 500)
        self.image_limit_spin.setValue(100)
        self.image_limit_spin.setPrefix("Limit: ")
        self.image_limit_spin.setVisible(False)
        fetch_layout.addWidget(self.image_limit_spin)
        image_layout.addLayout(fetch_layout)

        # Connect radio buttons to toggle visibility
        self.load_individual_radio.toggled.connect(self._toggle_image_selection)

        layout.addWidget(image_group)

        # Visualization params group
        vis_group = QGroupBox("Visualization Parameters")
        vis_layout = QFormLayout(vis_group)

        self.bands_input = QLineEdit()
        self.bands_input.setPlaceholderText("e.g., B4,B3,B2 for RGB")
        vis_layout.addRow("Bands:", self.bands_input)

        self.vis_min_input = QLineEdit()
        self.vis_min_input.setPlaceholderText("e.g., 0")
        vis_layout.addRow("Min:", self.vis_min_input)

        self.vis_max_input = QLineEdit()
        self.vis_max_input.setPlaceholderText("e.g., 3000")
        vis_layout.addRow("Max:", self.vis_max_input)

        self.palette_input = QLineEdit()
        self.palette_input.setPlaceholderText("e.g., blue,green,red or viridis")
        vis_layout.addRow("Palette:", self.palette_input)

        layout.addWidget(vis_group)

        # Load buttons
        btn_layout = QHBoxLayout()

        self.load_btn = QPushButton("Load Dataset")
        self.load_btn.clicked.connect(self._load_dataset)
        btn_layout.addWidget(self.load_btn)

        self.preview_btn = QPushButton("Preview Info")
        self.preview_btn.clicked.connect(self._preview_dataset)
        btn_layout.addWidget(self.preview_btn)

        layout.addLayout(btn_layout)

        # Copy code button
        btn_layout2 = QHBoxLayout()
        self.copy_code_btn = QPushButton("📋 Copy Code Snippet")
        self.copy_code_btn.clicked.connect(self._copy_code_snippet)
        self.copy_code_btn.setToolTip(
            "Copy the Python code for loading this dataset to clipboard"
        )
        btn_layout2.addWidget(self.copy_code_btn)
        layout.addLayout(btn_layout2)

        layout.addStretch()

        scroll.setWidget(scroll_widget)

        # Return scroll area wrapped in widget
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(scroll)
        return container

    def _create_code_tab(self):
        """Create the code console tab for geemap code."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Instructions
        instructions = QLabel(
            "Write Python/geemap code to load Earth Engine layers.\n"
            "Use standard geemap syntax: import geemap; m = geemap.Map(); m.add_layer(...)"
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(instructions)

        # Create splitter for code input and output
        code_splitter = QSplitter(Qt.Vertical)

        # Code input
        self.code_input = QPlainTextEdit()
        self.code_input.setPlaceholderText(
            "# Example code using geemap API:\n"
            "import ee\n"
            "import geemap\n"
            "\n"
            "m = geemap.Map()\n"
            "\n"
            "# Load a DEM\n"
            "dem = ee.Image('USGS/SRTMGL1_003')\n"
            "vis = {'min': 0, 'max': 4000, 'palette': ['green', 'yellow', 'brown', 'white']}\n"
            "m.add_layer(dem, vis, 'SRTM DEM')\n"
            "\n"
            "# Load Sentinel-2 imagery\n"
            "s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')\\\n"
            "    .filterDate('2023-01-01', '2023-06-01')\\\n"
            "    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))\\\n"
            "    .median()\n"
            "m.add_layer(s2, {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 3000}, 'Sentinel-2')\n"
            "\n"
            "# Load a FeatureCollection\n"
            "countries = ee.FeatureCollection('FAO/GAUL/2015/level0')\n"
            "m.add_layer(countries, {'color': 'blue'}, 'Countries')"
        )
        self.code_input.setFont(QFont("Monospace", 10))
        code_splitter.addWidget(self.code_input)

        # Output
        self.code_output = QTextEdit()
        self.code_output.setReadOnly(True)
        self.code_output.setPlaceholderText("Output will appear here...")
        self.code_output.setFont(QFont("Monospace", 9))
        code_splitter.addWidget(self.code_output)

        # Set initial sizes (code input gets 70%, output gets 30%)
        code_splitter.setSizes([400, 150])

        layout.addWidget(code_splitter)

        # Buttons
        btn_layout = QHBoxLayout()

        run_btn = QPushButton("▶ Run Code")
        run_btn.clicked.connect(self._run_code)
        btn_layout.addWidget(run_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(lambda: self.code_input.clear())
        btn_layout.addWidget(clear_btn)

        # Example dropdown
        example_combo = QComboBox()
        example_combo.addItem("Load Example...")
        example_combo.addItem("DEM with palette")
        example_combo.addItem("Landsat 9 RGB")
        example_combo.addItem("Sentinel-2 with filters")
        example_combo.addItem("NDVI calculation")
        example_combo.addItem("FeatureCollection styling")
        example_combo.addItem("Dynamic World")
        example_combo.currentIndexChanged.connect(self._load_code_example)
        btn_layout.addWidget(example_combo)

        layout.addLayout(btn_layout)

        return widget

    def _create_conversion_tab(self):
        """Create the conversion tab for converting JavaScript to Python."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Instructions
        instructions = QLabel(
            "Convert Earth Engine JavaScript code to Python.\n"
            "Paste JavaScript code, click Convert, then Run Code to execute."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(instructions)

        # Code input/output area
        self.conversion_input = QPlainTextEdit()
        self.conversion_input.setPlaceholderText(
            "// Paste Earth Engine JavaScript code here\n"
            "// Example:\n"
            "var dem = ee.Image('USGS/SRTMGL1_003');\n"
            "var vis = {min: 0, max: 4000, palette: ['green', 'yellow', 'brown']};\n"
            "Map.addLayer(dem, vis, 'DEM');"
        )
        self.conversion_input.setFont(QFont("Monospace", 10))
        layout.addWidget(self.conversion_input)

        # Buttons
        btn_layout = QHBoxLayout()

        convert_btn = QPushButton("Convert to Python")
        convert_btn.clicked.connect(self._convert_js_to_py)
        btn_layout.addWidget(convert_btn)

        run_btn = QPushButton("▶ Run Code")
        run_btn.clicked.connect(self._run_conversion_code)
        btn_layout.addWidget(run_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(lambda: self.conversion_input.clear())
        btn_layout.addWidget(clear_btn)

        layout.addLayout(btn_layout)

        return widget

    def _convert_js_to_py(self):
        """Convert JavaScript code to Python using geemap's conversion function."""
        js_code = self.conversion_input.toPlainText().strip()
        if not js_code:
            QMessageBox.warning(
                self, "Warning", "Please enter JavaScript code to convert."
            )
            return

        try:
            from geemap.conversion import js_snippet_to_py

            # Convert JavaScript to Python
            py_lines = js_snippet_to_py(
                js_code,
                add_new_cell=False,
                import_ee=True,
                import_geemap=True,
                show_map=False,
                Map="m",
            )

            if py_lines:
                py_code = "".join(py_lines)
                # Convert camelCase methods to snake_case
                py_code = self._camel_to_snake_methods(py_code)
                self.conversion_input.setPlainText(py_code)
                self._show_success("JavaScript converted to Python!")
            else:
                QMessageBox.warning(
                    self, "Warning", "Conversion returned empty result."
                )
        except ImportError:
            QMessageBox.critical(
                self,
                "Error",
                "geemap is not installed or conversion module not available.\n"
                "Please install geemap: pip install geemap",
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Conversion Error", f"Failed to convert: {str(e)}"
            )

    def _camel_to_snake_methods(self, code: str) -> str:
        """Convert common geemap camelCase methods to snake_case.

        Args:
            code: Python code with camelCase method names.

        Returns:
            Code with snake_case method names.
        """
        # Map of camelCase to snake_case for common geemap/Map methods
        method_replacements = {
            ".addLayer(": ".add_layer(",
            ".setCenter(": ".set_center(",
            ".centerObject(": ".center_object(",
            ".addBasemap(": ".add_basemap(",
            ".setOptions(": ".set_options(",
            ".zoomToObject(": ".zoom_to_object(",
            ".setBounds(": ".set_bounds(",
            ".getCenter(": ".get_center(",
            ".getBounds(": ".get_bounds(",
            ".getZoom(": ".get_zoom(",
            ".setZoom(": ".set_zoom(",
        }

        for camel, snake in method_replacements.items():
            code = code.replace(camel, snake)

        return code

    def _load_js_code_cache(self):
        """Load and cache the f.json file containing JavaScript code snippets.

        Returns:
            dict: Mapping of asset IDs to JavaScript code, or None if failed.
        """
        if self._js_code_cache is not None:
            return self._js_code_cache

        import json
        import os
        import os
        import tempfile
        import uuid
        import time
        from urllib.request import urlopen, Request
        from urllib.error import URLError

        # Cache file path
        cache_dir = os.path.join(tempfile.gettempdir(), "gee_data_catalogs")
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, "f.json")

        # Try to load from cache file first (if less than 24 hours old)
        try:
            if os.path.exists(cache_file):
                file_age = time.time() - os.path.getmtime(cache_file)
                if file_age < 86400 * 7:  # 7 days
                    with open(cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._js_code_cache = self._parse_js_code_data(data)
                        return self._js_code_cache
        except Exception:
            pass

        # Download from GitHub
        url = "https://github.com/opengeos/datasets/releases/download/gee/f.json"
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))

                # Save to cache file
                try:
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(data, f)
                except Exception:
                    pass

                self._js_code_cache = self._parse_js_code_data(data)
                return self._js_code_cache
        except (URLError, Exception) as e:
            QgsMessageLog.logMessage(
                f"Failed to load JavaScript code cache: {e}",
                "GEE Data Catalogs",
                Qgis.Warning,
            )
            self._js_code_cache = {}
            return self._js_code_cache

    def _parse_js_code_data(self, data):
        """Parse the f.json data into an asset ID to code mapping.

        Args:
            data: The parsed JSON data from f.json.

        Returns:
            dict: Mapping of asset IDs to JavaScript code.
        """
        import re

        code_map = {}

        for category in data.get("examples", []):
            if category.get("name") == "Datasets":
                for provider in category.get("contents", []):
                    for item in provider.get("contents", []):
                        code = item.get("code", "")
                        if not code:
                            continue

                        # Extract asset IDs from the code
                        matches = re.findall(
                            r"ee\.(Image|ImageCollection|FeatureCollection)\(['\"]([^'\"]+)['\"]\)",
                            code,
                        )
                        for _, asset_id in matches:
                            if asset_id not in code_map:
                                code_map[asset_id] = code

        return code_map

    def _get_js_code_for_asset(self, asset_id):
        """Get JavaScript code for a given asset ID.

        Args:
            asset_id: The Earth Engine asset ID.

        Returns:
            str: JavaScript code if found, None otherwise.
        """
        cache = self._load_js_code_cache()
        return cache.get(asset_id)

    def _run_js_code_for_asset(self, asset_id):
        """Run JavaScript code for an asset by converting to Python.

        Args:
            asset_id: The Earth Engine asset ID.

        Returns:
            bool: True if code was found and executed, False otherwise.
        """
        js_code = self._get_js_code_for_asset(asset_id)
        if not js_code:
            return False

        try:
            from geemap.conversion import js_snippet_to_py

            # Convert JavaScript to Python
            py_lines = js_snippet_to_py(
                js_code,
                add_new_cell=False,
                import_ee=True,
                import_geemap=True,
                show_map=False,
                Map="m",
            )

            if not py_lines:
                return False

            py_code = "".join(py_lines)
            # Convert camelCase methods to snake_case
            py_code = self._camel_to_snake_methods(py_code)

            # Copy the converted code to clipboard
            clipboard = QApplication.clipboard()
            clipboard.setText(py_code)

            # Execute the code
            self._execute_code_internal(py_code)
            return True

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Failed to run JavaScript code for {asset_id}: {e}",
                "GEE Data Catalogs",
                Qgis.Warning,
            )
            return False

    def _execute_code_internal(self, code):
        """Execute Python code internally (shared by multiple methods).

        Args:
            code: Python code to execute.
        """
        import sys
        import types

        # Create a QGIS-compatible Map class
        QGISMap = self._create_qgis_map_class()

        # Create namespace for execution
        namespace = {
            "iface": self.iface,
        }

        # Import ee
        try:
            import ee

            namespace["ee"] = ee
        except ImportError:
            pass

        # Create a patched geemap module that uses our QGISMap
        patched_geemap = types.ModuleType("geemap")
        patched_geemap.Map = QGISMap

        # Try to copy commonly used attributes from real geemap
        try:
            import geemap as real_geemap

            for attr in [
                "ee_initialize",
                "basemaps",
                "coreutils",
                "__version__",
                "create_timeseries",
            ]:
                if hasattr(real_geemap, attr):
                    setattr(patched_geemap, attr, getattr(real_geemap, attr))
        except ImportError:
            pass

        # Patch sys.modules to ensure our geemap is used for imports
        original_geemap = sys.modules.get("geemap")
        sys.modules["geemap"] = patched_geemap

        original_qgis_geemap = sys.modules.get("qgis_geemap.core.qgis_map")

        # Add geemap to namespace
        namespace["geemap"] = patched_geemap

        # Pre-create a Map instance as 'm' for convenience
        namespace["m"] = QGISMap()
        namespace["Map"] = QGISMap

        try:
            exec(code, namespace)
        finally:
            # Restore original modules
            if original_geemap is not None:
                sys.modules["geemap"] = original_geemap
            else:
                sys.modules.pop("geemap", None)

            if original_qgis_geemap is not None:
                sys.modules["qgis_geemap.core.qgis_map"] = original_qgis_geemap

    def _run_conversion_code(self):
        """Execute the Python code from the conversion tab."""
        code = self.conversion_input.toPlainText()
        if not code.strip():
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        try:
            import sys
            import types

            # Create a QGIS-compatible Map class
            QGISMap = self._create_qgis_map_class()

            # Create namespace for execution
            namespace = {
                "iface": self.iface,
            }

            # Import ee
            try:
                import ee

                namespace["ee"] = ee
            except ImportError:
                pass

            # Create a patched geemap module that uses our QGISMap
            patched_geemap = types.ModuleType("geemap")
            patched_geemap.Map = QGISMap

            # Try to copy commonly used attributes from real geemap
            try:
                import geemap as real_geemap

                for attr in [
                    "ee_initialize",
                    "basemaps",
                    "coreutils",
                    "__version__",
                    "create_timeseries",
                ]:
                    if hasattr(real_geemap, attr):
                        setattr(patched_geemap, attr, getattr(real_geemap, attr))
            except ImportError:
                pass

            # Patch sys.modules to ensure our geemap is used for imports
            original_geemap = sys.modules.get("geemap")
            sys.modules["geemap"] = patched_geemap

            # Also patch qgis_geemap if it exists
            original_qgis_geemap = sys.modules.get("qgis_geemap.core.qgis_map")

            # Add geemap to namespace
            namespace["geemap"] = patched_geemap

            # Pre-create a Map instance as 'm' for convenience
            namespace["m"] = QGISMap()
            namespace["Map"] = QGISMap

            try:
                # Execute the code
                exec(code, namespace)
                self._show_success("Code executed successfully!")
            finally:
                # Restore original modules
                if original_geemap is not None:
                    sys.modules["geemap"] = original_geemap
                else:
                    sys.modules.pop("geemap", None)

                if original_qgis_geemap is not None:
                    sys.modules["qgis_geemap.core.qgis_map"] = original_qgis_geemap

        except Exception as e:
            import traceback

            error_msg = str(e)
            tb = traceback.format_exc()
            QMessageBox.critical(
                self, "Execution Error", f"Error: {error_msg}\n\nDetails:\n{tb}"
            )
        finally:
            QApplication.restoreOverrideCursor()

    def _create_inspector_tab(self):
        """Create the Inspector tab for examining Earth Engine data at clicked locations."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Instructions
        instructions = QLabel(
            "Click 'Start Inspector' button below, then click on the map to inspect Earth Engine layer values at that location."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(instructions)

        # Layer count info
        self.inspector_layer_count_label = QLabel("Registered layers: 0")
        self.inspector_layer_count_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.inspector_layer_count_label)

        # Inspector toggle button
        btn_layout = QHBoxLayout()
        self.inspector_toggle_btn = QPushButton("▶ Start Inspector")
        self.inspector_toggle_btn.setCheckable(True)
        self.inspector_toggle_btn.clicked.connect(self._toggle_inspector)
        btn_layout.addWidget(self.inspector_toggle_btn)

        self.inspector_clear_btn = QPushButton("Clear")
        self.inspector_clear_btn.clicked.connect(self._clear_inspector)
        btn_layout.addWidget(self.inspector_clear_btn)

        self.inspector_refresh_btn = QPushButton("↻ Refresh Layers")
        self.inspector_refresh_btn.setToolTip(
            "Refresh the list of registered Earth Engine layers"
        )
        self.inspector_refresh_btn.clicked.connect(self._refresh_inspector_layers)
        btn_layout.addWidget(self.inspector_refresh_btn)

        layout.addLayout(btn_layout)

        # Location group
        location_group = QGroupBox("Location")
        location_layout = QFormLayout(location_group)

        self.inspector_lon_label = QLabel("--")
        self.inspector_lat_label = QLabel("--")
        location_layout.addRow("Longitude:", self.inspector_lon_label)
        location_layout.addRow("Latitude:", self.inspector_lat_label)

        layout.addWidget(location_group)

        # Results tree
        results_label = QLabel("Layer Results:")
        results_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(results_label)

        self.inspector_tree = QTreeWidget()
        self.inspector_tree.setHeaderLabels(["Property", "Value"])
        self.inspector_tree.setAlternatingRowColors(True)
        self.inspector_tree.setColumnWidth(0, 200)
        self.inspector_tree.header().setStretchLastSection(True)
        layout.addWidget(self.inspector_tree)

        # Progress bar
        self.inspector_progress_bar = QProgressBar()
        self.inspector_progress_bar.setVisible(False)
        self.inspector_progress_bar.setTextVisible(False)
        layout.addWidget(self.inspector_progress_bar)

        # Inspector status
        self.inspector_status_label = QLabel(
            "Ready to inspect. Click 'Start Inspector' and then click on the map."
        )
        self.inspector_status_label.setWordWrap(True)
        self.inspector_status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.inspector_status_label)

        return widget

    def _create_export_tab(self):
        """Create the Export tab for exporting Earth Engine data."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Instructions
        instructions = QLabel(
            "Export Earth Engine layers to local files.\n"
            "• Images: Export as Cloud Optimized GeoTIFF (COG) using xee\n"
            "• FeatureCollections: Export as GeoJSON, Shapefile, or GeoPackage"
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(instructions)

        # Layer selection group
        layer_group = QGroupBox("Select Layer")
        layer_layout = QVBoxLayout(layer_group)

        # Layer dropdown
        layer_combo_layout = QHBoxLayout()
        layer_combo_layout.addWidget(QLabel("EE Layer:"))
        self.export_layer_combo = QComboBox()
        self.export_layer_combo.setMinimumWidth(200)
        self.export_layer_combo.currentIndexChanged.connect(
            self._on_export_layer_changed
        )
        layer_combo_layout.addWidget(self.export_layer_combo, 1)

        refresh_layers_btn = QPushButton("↻")
        refresh_layers_btn.setToolTip("Refresh layer list")
        refresh_layers_btn.setMaximumWidth(30)
        refresh_layers_btn.clicked.connect(self._refresh_export_layers)
        layer_combo_layout.addWidget(refresh_layers_btn)

        layer_layout.addLayout(layer_combo_layout)

        # Layer type indicator
        self.export_layer_type_label = QLabel("Layer type: --")
        self.export_layer_type_label.setStyleSheet("color: gray; font-size: 10px;")
        layer_layout.addWidget(self.export_layer_type_label)

        layout.addWidget(layer_group)

        # Region selection group
        region_group = QGroupBox("Export Region")
        region_layout = QVBoxLayout(region_group)

        self.export_region_btn_group = QButtonGroup(self)

        # Map extent option
        self.export_map_extent_radio = QRadioButton("Use current map extent")
        self.export_map_extent_radio.setChecked(True)
        self.export_region_btn_group.addButton(self.export_map_extent_radio, 0)
        region_layout.addWidget(self.export_map_extent_radio)

        # Vector layer option
        vector_layout = QHBoxLayout()
        self.export_vector_radio = QRadioButton("Use vector layer bounds:")
        self.export_region_btn_group.addButton(self.export_vector_radio, 1)
        vector_layout.addWidget(self.export_vector_radio)

        self.export_vector_combo = QComboBox()
        self.export_vector_combo.setEnabled(False)
        vector_layout.addWidget(self.export_vector_combo, 1)
        region_layout.addLayout(vector_layout)

        # Connect radio button to enable/disable vector combo
        self.export_vector_radio.toggled.connect(
            lambda checked: self.export_vector_combo.setEnabled(checked)
        )

        # Draw bounding box option
        draw_layout = QHBoxLayout()
        self.export_draw_radio = QRadioButton("Draw bounding box on map")
        self.export_region_btn_group.addButton(self.export_draw_radio, 2)
        draw_layout.addWidget(self.export_draw_radio)

        self.export_draw_btn = QPushButton("Draw")
        self.export_draw_btn.setEnabled(False)
        self.export_draw_btn.setMaximumWidth(60)
        self.export_draw_btn.clicked.connect(self._start_draw_export_bbox)
        draw_layout.addWidget(self.export_draw_btn)

        self.export_drawn_bounds_label = QLabel("")
        self.export_drawn_bounds_label.setStyleSheet("color: gray; font-size: 9px;")
        draw_layout.addWidget(self.export_drawn_bounds_label, 1)
        region_layout.addLayout(draw_layout)

        self.export_draw_radio.toggled.connect(
            lambda checked: self.export_draw_btn.setEnabled(checked)
        )

        # Store drawn bounds
        self._export_drawn_bounds = None

        # Custom bounds option
        custom_layout = QHBoxLayout()
        self.export_custom_radio = QRadioButton("Custom bounds (W,S,E,N):")
        self.export_region_btn_group.addButton(self.export_custom_radio, 3)
        custom_layout.addWidget(self.export_custom_radio)

        self.export_bounds_edit = QLineEdit()
        self.export_bounds_edit.setPlaceholderText("-180,-90,180,90")
        self.export_bounds_edit.setEnabled(False)
        custom_layout.addWidget(self.export_bounds_edit, 1)
        region_layout.addLayout(custom_layout)

        self.export_custom_radio.toggled.connect(
            lambda checked: self.export_bounds_edit.setEnabled(checked)
        )

        layout.addWidget(region_group)

        # Export options group
        options_group = QGroupBox("Export Options")
        options_layout = QFormLayout(options_group)

        # Scale (for images)
        self.export_scale_spin = QSpinBox()
        self.export_scale_spin.setRange(1, 10000)
        self.export_scale_spin.setValue(30)
        self.export_scale_spin.setSuffix(" m")
        options_layout.addRow("Scale:", self.export_scale_spin)

        # CRS
        self.export_crs_edit = QLineEdit("EPSG:3857")
        options_layout.addRow("CRS:", self.export_crs_edit)

        # Output format (for FeatureCollections)
        self.export_format_combo = QComboBox()
        # Common vector formats supported by GeoPandas/pyogrio
        self.export_format_combo.addItems(
            [
                "GeoJSON",
                "GPKG (GeoPackage)",
                "ESRI Shapefile",
                "FlatGeobuf",
                "Parquet (GeoParquet)",
                "GeoJSONSeq",
                "CSV",
                "KML",
                "GML",
            ]
        )
        options_layout.addRow("Vector Format:", self.export_format_combo)

        layout.addWidget(options_group)

        # Output file selection
        output_group = QGroupBox("Output File")
        output_layout = QHBoxLayout(output_group)

        self.export_output_edit = QLineEdit()
        self.export_output_edit.setPlaceholderText("Select output file...")
        output_layout.addWidget(self.export_output_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_export_output)
        output_layout.addWidget(browse_btn)

        layout.addWidget(output_group)

        # Export button
        btn_layout = QHBoxLayout()
        self.export_btn = QPushButton("Export")
        self.export_btn.clicked.connect(self._do_export)
        self.export_btn.setStyleSheet("font-weight: bold;")
        btn_layout.addWidget(self.export_btn)

        layout.addLayout(btn_layout)

        # Progress bar
        self.export_progress_bar = QProgressBar()
        self.export_progress_bar.setVisible(False)
        layout.addWidget(self.export_progress_bar)

        # Status label
        self.export_status_label = QLabel("Select a layer to export.")
        self.export_status_label.setWordWrap(True)
        self.export_status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.export_status_label)

        # Add stretch to push everything up
        layout.addStretch()

        # Initialize layer lists
        self._refresh_export_layers()
        self._refresh_vector_layers()

        return widget

    def _refresh_export_layers(self):
        """Refresh the list of EE layers available for export."""
        from ..core.ee_utils import get_ee_layers

        self.export_layer_combo.clear()
        ee_layers = get_ee_layers()

        if not ee_layers:
            self.export_layer_combo.addItem("-- No EE layers loaded --")
            self.export_layer_type_label.setText("Layer type: --")
            return

        for name in ee_layers.keys():
            self.export_layer_combo.addItem(name)

        self._on_export_layer_changed(0)

    def _refresh_vector_layers(self):
        """Refresh the list of vector layers for bounds selection."""
        self.export_vector_combo.clear()

        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == layer.VectorLayer:
                self.export_vector_combo.addItem(layer.name(), layer.id())

    def _on_export_layer_changed(self, index):
        """Handle export layer selection change."""
        from ..core.ee_utils import get_ee_layers

        layer_name = self.export_layer_combo.currentText()
        if layer_name.startswith("--"):
            self.export_layer_type_label.setText("Layer type: --")
            return

        # Reset output file path when layer changes
        self.export_output_edit.clear()

        ee_layers = get_ee_layers()
        if layer_name in ee_layers:
            ee_object, vis_params = ee_layers[layer_name]

            # Check type using class name as fallback for lazy ee objects
            type_name = type(ee_object).__name__
            is_image = isinstance(ee_object, ee.Image) or type_name == "Image"
            is_image_collection = (
                isinstance(ee_object, ee.ImageCollection)
                or type_name == "ImageCollection"
            )
            is_feature_collection = (
                isinstance(ee_object, ee.FeatureCollection)
                or type_name == "FeatureCollection"
            )
            is_feature = isinstance(ee_object, ee.Feature) or type_name == "Feature"

            if is_image:
                self.export_layer_type_label.setText("Layer type: ee.Image")
                self.export_format_combo.setEnabled(False)
                self.export_scale_spin.setEnabled(True)
            elif is_image_collection:
                self.export_layer_type_label.setText(
                    "Layer type: ee.ImageCollection (will mosaic)"
                )
                self.export_format_combo.setEnabled(False)
                self.export_scale_spin.setEnabled(True)
            elif is_feature_collection:
                self.export_layer_type_label.setText("Layer type: ee.FeatureCollection")
                self.export_format_combo.setEnabled(True)
                self.export_scale_spin.setEnabled(False)
            elif is_feature:
                self.export_layer_type_label.setText("Layer type: ee.Feature")
                self.export_format_combo.setEnabled(True)
                self.export_scale_spin.setEnabled(False)
            else:
                # Default: enable both options for unknown types
                self.export_layer_type_label.setText(f"Layer type: {type_name}")
                self.export_format_combo.setEnabled(True)
                self.export_scale_spin.setEnabled(True)

    def _browse_export_output(self):
        """Open file dialog to select output file."""
        from ..core.ee_utils import get_ee_layers

        layer_name = self.export_layer_combo.currentText()
        ee_layers = get_ee_layers()

        # Format to file filter and extension mapping
        format_info = {
            "GeoJSON": ("GeoJSON (*.geojson);;All Files (*)", ".geojson"),
            "GPKG (GeoPackage)": ("GeoPackage (*.gpkg);;All Files (*)", ".gpkg"),
            "ESRI Shapefile": ("Shapefile (*.shp);;All Files (*)", ".shp"),
            "FlatGeobuf": ("FlatGeobuf (*.fgb);;All Files (*)", ".fgb"),
            "Parquet (GeoParquet)": (
                "GeoParquet (*.parquet);;All Files (*)",
                ".parquet",
            ),
            "GeoJSONSeq": ("GeoJSON Sequence (*.geojsonl);;All Files (*)", ".geojsonl"),
            "CSV": ("CSV (*.csv);;All Files (*)", ".csv"),
            "KML": ("KML (*.kml);;All Files (*)", ".kml"),
            "GML": ("GML (*.gml);;All Files (*)", ".gml"),
        }

        file_path = ""
        expected_ext = ""

        if layer_name in ee_layers:
            ee_object, _ = ee_layers[layer_name]
            type_name = type(ee_object).__name__
            is_image = isinstance(
                ee_object, (ee.Image, ee.ImageCollection)
            ) or type_name in ("Image", "ImageCollection")

            if is_image:
                file_path, _ = QFileDialog.getSaveFileName(
                    self,
                    "Save Image As",
                    "",
                    "Cloud Optimized GeoTIFF (*.tif);;All Files (*)",
                )
                expected_ext = ".tif"
            else:
                fmt = self.export_format_combo.currentText()
                filter_str, expected_ext = format_info.get(fmt, ("All Files (*)", ""))
                file_path, _ = QFileDialog.getSaveFileName(
                    self, "Save As", "", filter_str
                )
        else:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save As", "", "All Files (*)"
            )

        if file_path:
            # Auto-add extension if not present
            if expected_ext and not file_path.lower().endswith(expected_ext):
                file_path += expected_ext
            self.export_output_edit.setText(file_path)

    def _get_export_region(self):
        """Get the export region as an ee.Geometry.

        Returns:
            ee.Geometry.Rectangle or None if error.
        """
        region_type = self.export_region_btn_group.checkedId()

        if region_type == 0:  # Map extent
            bounds = self._get_map_extent_wgs84()
            if bounds:
                return ee.Geometry.Rectangle(bounds)
            else:
                QMessageBox.warning(self, "Error", "Could not get map extent.")
                return None

        elif region_type == 1:  # Vector layer
            layer_id = self.export_vector_combo.currentData()
            if not layer_id:
                QMessageBox.warning(self, "Error", "No vector layer selected.")
                return None

            layer = QgsProject.instance().mapLayer(layer_id)
            if not layer:
                QMessageBox.warning(self, "Error", "Vector layer not found.")
                return None

            from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform

            extent = layer.extent()
            layer_crs = layer.crs()
            wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")

            if layer_crs.authid() != "EPSG:4326":
                transform = QgsCoordinateTransform(
                    layer_crs, wgs84, QgsProject.instance()
                )
                extent = transform.transformBoundingBox(extent)

            bounds = [
                extent.xMinimum(),
                extent.yMinimum(),
                extent.xMaximum(),
                extent.yMaximum(),
            ]
            return ee.Geometry.Rectangle(bounds)

        elif region_type == 2:  # Draw bounding box
            if self._export_drawn_bounds is None:
                QMessageBox.warning(
                    self, "Error", "Please draw a bounding box on the map first."
                )
                return None
            return ee.Geometry.Rectangle(self._export_drawn_bounds)

        elif region_type == 3:  # Custom bounds
            bounds_text = self.export_bounds_edit.text().strip()
            try:
                parts = [float(x.strip()) for x in bounds_text.split(",")]
                if len(parts) != 4:
                    raise ValueError("Need exactly 4 values")
                return ee.Geometry.Rectangle(parts)
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Error",
                    f"Invalid bounds format: {e}\nUse: West,South,East,North",
                )
                return None

        return None

    def _start_draw_export_bbox(self):
        """Start the bounding box drawing tool."""
        from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand
        from qgis.core import (
            QgsWkbTypes,
            QgsCoordinateReferenceSystem,
            QgsCoordinateTransform,
        )

        canvas = self.iface.mapCanvas()

        # Create a rubber band for visual feedback
        self._export_rubber_band = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
        self._export_rubber_band.setColor(Qt.red)
        self._export_rubber_band.setWidth(2)
        self._export_rubber_band.setFillColor(Qt.transparent)

        # Store start point
        self._export_bbox_start = None

        class BBoxMapTool(QgsMapToolEmitPoint):
            def __init__(tool_self, canvas, dock):
                super().__init__(canvas)
                tool_self.dock = dock
                tool_self.start_point = None
                tool_self.end_point = None
                tool_self.is_drawing = False

            def canvasPressEvent(tool_self, event):
                tool_self.start_point = tool_self.toMapCoordinates(event.pos())
                tool_self.is_drawing = True
                tool_self.dock._export_rubber_band.reset(QgsWkbTypes.PolygonGeometry)

            def canvasMoveEvent(tool_self, event):
                if not tool_self.is_drawing:
                    return
                tool_self.end_point = tool_self.toMapCoordinates(event.pos())
                tool_self.dock._update_export_rubber_band(
                    tool_self.start_point, tool_self.end_point
                )

            def canvasReleaseEvent(tool_self, event):
                if not tool_self.is_drawing:
                    return
                tool_self.is_drawing = False
                tool_self.end_point = tool_self.toMapCoordinates(event.pos())

                # Convert to WGS84
                map_crs = canvas.mapSettings().destinationCrs()
                wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")

                if map_crs.authid() != "EPSG:4326":
                    transform = QgsCoordinateTransform(
                        map_crs, wgs84, QgsProject.instance()
                    )
                    start_wgs84 = transform.transform(tool_self.start_point)
                    end_wgs84 = transform.transform(tool_self.end_point)
                else:
                    start_wgs84 = tool_self.start_point
                    end_wgs84 = tool_self.end_point

                # Store bounds as [west, south, east, north]
                west = min(start_wgs84.x(), end_wgs84.x())
                east = max(start_wgs84.x(), end_wgs84.x())
                south = min(start_wgs84.y(), end_wgs84.y())
                north = max(start_wgs84.y(), end_wgs84.y())

                tool_self.dock._export_drawn_bounds = [west, south, east, north]
                tool_self.dock.export_drawn_bounds_label.setText(
                    f"({west:.4f}, {south:.4f}, {east:.4f}, {north:.4f})"
                )

                # Clean up
                tool_self.dock._export_rubber_band.reset()
                canvas.unsetMapTool(tool_self)
                tool_self.dock._show_success("Bounding box drawn")

        self._export_bbox_tool = BBoxMapTool(canvas, self)
        canvas.setMapTool(self._export_bbox_tool)
        self.export_status_label.setText(
            "Click and drag on the map to draw a bounding box..."
        )

    def _update_export_rubber_band(self, start_point, end_point):
        """Update the rubber band rectangle during drawing."""
        from qgis.core import QgsPointXY, QgsGeometry

        # Create rectangle points
        points = [
            QgsPointXY(start_point.x(), start_point.y()),
            QgsPointXY(end_point.x(), start_point.y()),
            QgsPointXY(end_point.x(), end_point.y()),
            QgsPointXY(start_point.x(), end_point.y()),
            QgsPointXY(start_point.x(), start_point.y()),
        ]

        self._export_rubber_band.setToGeometry(
            QgsGeometry.fromPolygonXY([points]), None
        )

    def _do_export(self):
        """Perform the export operation using a background thread."""
        from ..core.ee_utils import get_ee_layers

        layer_name = self.export_layer_combo.currentText()
        if layer_name.startswith("--"):
            QMessageBox.warning(self, "Error", "Please select a valid EE layer.")
            return

        ee_layers = get_ee_layers()
        if layer_name not in ee_layers:
            QMessageBox.warning(self, "Error", "Layer not found in registry.")
            return

        ee_object, vis_params = ee_layers[layer_name]

        # Get region
        region = self._get_export_region()
        if region is None:
            return

        # Get options
        scale = self.export_scale_spin.value()
        crs = self.export_crs_edit.text().strip() or "EPSG:3857"
        vector_format = self.export_format_combo.currentText()

        # Determine export type
        type_name = type(ee_object).__name__
        is_image = isinstance(ee_object, ee.Image) or type_name == "Image"
        is_image_collection = (
            isinstance(ee_object, ee.ImageCollection) or type_name == "ImageCollection"
        )
        is_feature_collection = (
            isinstance(ee_object, ee.FeatureCollection)
            or type_name == "FeatureCollection"
        )
        is_feature = isinstance(ee_object, ee.Feature) or type_name == "Feature"

        if is_image or is_image_collection:
            export_type = "image"
        elif is_feature_collection or is_feature:
            export_type = "features"
        else:
            QMessageBox.warning(self, "Error", f"Unsupported object type: {type_name}")
            return

        output_path = self.export_output_edit.text().strip()
        if not output_path:
            output_path = self._generate_temp_export_path(
                export_type=export_type, vector_format=vector_format
            )
            self.export_output_edit.setText(output_path)

        # Show progress
        self._start_export_progress()
        self.export_status_label.setText("Starting export...")
        self.export_status_label.setStyleSheet("color: gray; font-size: 10px;")
        self.export_btn.setEnabled(False)

        # Create and start worker thread
        self._export_thread = ExportWorkerThread(
            export_type=export_type,
            ee_object=ee_object,
            region=region,
            output_path=output_path,
            scale=scale,
            crs=crs,
            vector_format=vector_format,
        )
        self._export_thread.finished.connect(self._on_export_finished)
        self._export_thread.error.connect(self._on_export_error)
        self._export_thread.progress.connect(self._on_export_progress)
        self._export_thread.start()

    def _on_export_progress(self, message):
        """Handle export progress updates."""
        self.export_status_label.setText(message)

    def _on_export_finished(self, output_path):
        """Handle successful export completion."""
        import os

        self._stop_export_progress()
        self.export_btn.setEnabled(True)
        self.export_status_label.setText(f"Exported to: {output_path}")
        self.export_status_label.setStyleSheet("color: green; font-size: 10px;")

        # Ask if user wants to add to map
        reply = QMessageBox.question(
            self,
            "Export Complete",
            f"Export successful!\n{output_path}\n\nAdd layer to map?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            layer_name = os.path.splitext(os.path.basename(output_path))[0]
            if output_path.lower().endswith(".tif"):
                from qgis.core import QgsRasterLayer

                layer = QgsRasterLayer(output_path, layer_name)
            else:
                from qgis.core import QgsVectorLayer

                layer = QgsVectorLayer(output_path, layer_name, "ogr")

            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)

    def _on_export_error(self, error_message):
        """Handle export error."""
        self._stop_export_progress()
        self.export_btn.setEnabled(True)
        self.export_status_label.setText("Export failed!")
        self.export_status_label.setStyleSheet("color: red; font-size: 10px;")
        QMessageBox.critical(self, "Export Error", f"Export failed:\n{error_message}")

    def _start_export_progress(self):
        """Start an indeterminate progress indicator for export."""
        self.export_progress_bar.setVisible(True)
        self.export_progress_bar.setRange(0, 0)

    def _stop_export_progress(self):
        """Stop the export progress animation."""
        self.export_progress_bar.setVisible(False)

    def _generate_temp_export_path(self, export_type: str, vector_format: str) -> str:
        """Generate a temporary output path when the user does not choose one."""
        import os
        import tempfile
        import uuid

        format_map = {
            "GeoJSON": ".geojson",
            "GPKG (GeoPackage)": ".gpkg",
            "ESRI Shapefile": ".shp",
            "FlatGeobuf": ".fgb",
            "Parquet (GeoParquet)": ".parquet",
            "GeoJSONSeq": ".geojsonl",
            "CSV": ".csv",
            "KML": ".kml",
            "GML": ".gml",
        }

        if export_type == "image":
            suffix = ".tif"
        else:
            suffix = format_map.get(vector_format, ".geojson")

        temp_dir = tempfile.gettempdir()
        filename = f"gee_export_{uuid.uuid4().hex}{suffix}"
        return os.path.join(temp_dir, filename)

    def _export_image(self, ee_object, region, scale, crs, output_path):
        """Export an ee.Image or ee.ImageCollection as COG using xee.

        Args:
            ee_object: ee.Image or ee.ImageCollection
            region: ee.Geometry for export bounds
            scale: Resolution in meters
            crs: Coordinate reference system string
            output_path: Output file path
        """
        import sys
        import os

        try:
            import xarray as xr
            import xee
        except ImportError as e:
            raise ImportError(
                f"Required packages not available: {e}\n"
                "Please install xarray and xee: pip install xarray xee"
            )

        self.export_status_label.setText("Opening dataset with xee...")
        QApplication.processEvents()

        # Convert ImageCollection to Image if needed
        if isinstance(ee_object, ee.ImageCollection):
            ee_object = ee_object.mosaic()

        # Clip to region
        ee_object = ee_object.clip(region)

        # Open with xee
        ds = xr.open_dataset(
            ee_object,
            engine=xee.EarthEngineBackendEntrypoint,
            crs=crs,
            scale=scale,
            geometry=region,
        )

        self.export_status_label.setText("Processing dataset...")
        QApplication.processEvents()

        # Ensure output has .tif extension
        if not output_path.lower().endswith(".tif"):
            output_path += ".tif"

        # Write as COG using rioxarray
        try:
            import rioxarray  # noqa: F401
        except ImportError:
            raise ImportError(
                "rioxarray is required for COG export.\n"
                "Please install it: pip install rioxarray"
            )

        # Handle xee dimension naming for rioxarray
        # xee may use 'X'/'Y', 'lon'/'lat', or 'x'/'y' depending on version
        rename_dims = {}
        for old_x in ["X", "lon", "longitude"]:
            if old_x in ds.dims:
                rename_dims[old_x] = "x"
                break
        for old_y in ["Y", "lat", "latitude"]:
            if old_y in ds.dims:
                rename_dims[old_y] = "y"
                break
        if rename_dims:
            ds = ds.rename(rename_dims)

        # Drop time dimension if present (take first time slice)
        if "time" in ds.dims:
            ds = ds.isel(time=0)

        # Verify spatial dims exist
        if "x" not in ds.dims or "y" not in ds.dims:
            raise ValueError(
                f"Could not find spatial dimensions. Available dims: {list(ds.dims)}"
            )

        # Set CRS
        ds = ds.rio.write_crs(crs)

        # Set spatial dims explicitly
        ds = ds.rio.set_spatial_dims(x_dim="x", y_dim="y")

        # Get data variables to export
        data_vars = list(ds.data_vars)
        if not data_vars:
            raise ValueError("No data variables found in the dataset")

        self.export_status_label.setText("Writing COG file...")
        QApplication.processEvents()

        # Export to COG
        if len(data_vars) > 1:
            # Stack multiple variables as bands
            import numpy as np

            # Get arrays and transpose each to (y, x) order
            arrays = []
            for var in data_vars:
                da = ds[var]
                if da.dims != ("y", "x"):
                    da = da.transpose("y", "x")
                arrays.append(da.values)

            stacked = np.stack(arrays, axis=0)

            # Create a new DataArray with band dimension
            da = xr.DataArray(
                stacked,
                dims=["band", "y", "x"],
                coords={
                    "band": list(range(1, len(data_vars) + 1)),
                    "y": ds.y,
                    "x": ds.x,
                },
            )
            da = da.rio.write_crs(crs)
            da = da.rio.set_spatial_dims(x_dim="x", y_dim="y")
            da.rio.to_raster(output_path, driver="COG")
        else:
            # Get the data array and transpose to (y, x) order for rioxarray
            da = ds[data_vars[0]]
            if da.dims != ("y", "x"):
                da = da.transpose("y", "x")
            da.rio.to_raster(output_path, driver="COG")

        self.export_status_label.setText(f"Exported to: {output_path}")
        self.export_status_label.setStyleSheet("color: green; font-size: 10px;")

        # Ask if user wants to add to map
        reply = QMessageBox.question(
            self,
            "Export Complete",
            f"Image exported successfully to:\n{output_path}\n\nAdd layer to map?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            from qgis.core import QgsRasterLayer

            layer_name = os.path.splitext(os.path.basename(output_path))[0]
            layer = QgsRasterLayer(output_path, layer_name)
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)

    def _export_features(self, ee_object, region, output_path):
        """Export an ee.FeatureCollection or ee.Feature using ee.data.computeFeatures.

        Args:
            ee_object: ee.FeatureCollection or ee.Feature
            region: ee.Geometry for filtering features
            output_path: Output file path
        """
        import os

        self.export_status_label.setText("Filtering features by region...")
        QApplication.processEvents()

        # Convert Feature to FeatureCollection if needed
        type_name = type(ee_object).__name__
        if isinstance(ee_object, ee.Feature) or type_name == "Feature":
            ee_object = ee.FeatureCollection([ee_object])

        # Filter by region
        ee_object = ee_object.filterBounds(region)

        self.export_status_label.setText("Fetching features from Earth Engine...")
        QApplication.processEvents()

        # Get the selected format
        fmt = self.export_format_combo.currentText()

        # Format mapping: display name -> (driver, extension)
        format_map = {
            "GeoJSON": ("GeoJSON", ".geojson"),
            "GPKG (GeoPackage)": ("GPKG", ".gpkg"),
            "ESRI Shapefile": ("ESRI Shapefile", ".shp"),
            "FlatGeobuf": ("FlatGeobuf", ".fgb"),
            "Parquet (GeoParquet)": ("Parquet", ".parquet"),
            "GeoJSONSeq": ("GeoJSONSeq", ".geojsonl"),
            "CSV": ("CSV", ".csv"),
            "KML": ("KML", ".kml"),
            "GML": ("GML", ".gml"),
        }

        driver, ext = format_map.get(fmt, ("GeoJSON", ".geojson"))

        # Ensure correct extension
        if not output_path.lower().endswith(ext):
            output_path += ext

        # Try to use ee.data.computeFeatures with GEOPANDAS_GEODATAFRAME first
        # Fall back to getInfo() if that fails
        try:
            import geopandas as gpd
        except ImportError:
            raise ImportError(
                "geopandas is required for vector export.\n"
                "Please install it: pip install geopandas"
            )

        try:
            # Try using computeFeatures with GeoDataFrame output (faster for large datasets)
            gdf = ee.data.computeFeatures(
                {
                    "expression": ee_object,
                    "fileFormat": "GEOPANDAS_GEODATAFRAME",
                }
            )
        except Exception:
            # Fall back to getInfo() method
            self.export_status_label.setText("Fetching features (fallback method)...")
            QApplication.processEvents()
            result = ee_object.getInfo()
            if "features" in result:
                gdf = gpd.GeoDataFrame.from_features(result["features"])
            else:
                raise RuntimeError("Failed to get features from Earth Engine")

        # Set CRS if not already set
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")

        self.export_status_label.setText("Writing output file...")
        QApplication.processEvents()

        # Export based on format
        if fmt == "GeoJSON":
            gdf.to_file(output_path, driver="GeoJSON")
        elif driver == "Parquet":
            gdf.to_parquet(output_path)
        else:
            gdf.to_file(output_path, driver=driver)

        self.export_status_label.setText(f"Exported to: {output_path}")
        self.export_status_label.setStyleSheet("color: green; font-size: 10px;")

        # Ask if user wants to add to map
        reply = QMessageBox.question(
            self,
            "Export Complete",
            f"Features exported successfully to:\n{output_path}\n\nAdd layer to map?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            from qgis.core import QgsVectorLayer

            layer = QgsVectorLayer(
                output_path, os.path.splitext(os.path.basename(output_path))[0], "ogr"
            )
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)

    def _on_tab_changed(self, index):
        """Handle tab changes."""
        # Refresh layer count when switching to Inspector tab (index 6 after adding Time Series tab)
        if index == 6:  # Inspector tab
            self._refresh_inspector_layers()
        elif index == 7:  # Export tab
            self._refresh_export_layers()
            self._refresh_vector_layers()

    def _toggle_image_selection(self, checked):
        """Toggle visibility of image selection widgets."""
        self.image_list_widget.setVisible(checked)
        self.fetch_images_btn.setVisible(checked)
        self.image_limit_spin.setVisible(checked)
        self.agg_method.setEnabled(not checked)

    def _start_catalog_load(self):
        """Start loading catalogs in background."""
        self.refresh_btn.setEnabled(False)
        self._show_progress("Loading catalogs from GitHub...")

        self._catalog_thread = CatalogLoaderThread(include_community=True)
        self._catalog_thread.finished.connect(self._on_catalog_loaded)
        self._catalog_thread.error.connect(self._on_catalog_error)
        self._catalog_thread.progress.connect(
            lambda msg: self.status_label.setText(msg)
        )
        self._catalog_thread.start()

    def _on_catalog_loaded(self, catalog):
        """Handle catalog loaded successfully."""
        self.refresh_btn.setEnabled(True)
        self._populate_catalog(catalog)
        self._show_success(
            f"Loaded catalogs with {sum(len(c.get('datasets', [])) for c in catalog.values())} datasets"
        )

    def _on_catalog_error(self, error):
        """Handle catalog load error."""
        self.refresh_btn.setEnabled(True)
        self._show_error(f"Failed to load catalogs: {error}")

    def _refresh_catalog(self):
        """Refresh the catalog from remote sources."""
        from ..core.catalog_data import clear_cache

        clear_cache()
        self._start_catalog_load()

    def _populate_catalog(self, catalog=None):
        """Populate the catalog tree with datasets."""
        try:
            if catalog is None:
                from ..core.catalog_data import get_catalog_data, get_categories

                catalog = get_catalog_data()

            from ..core.catalog_data import get_categories

            categories = get_categories()

            # Populate category filter
            self.category_filter.clear()
            self.category_filter.addItem("All Categories", None)
            for category in categories:
                self.category_filter.addItem(category, category)

            # Populate tree
            self.catalog_tree.clear()
            self._full_catalog = catalog  # Store for filtering

            for category in categories:
                cat_data = catalog.get(category, {})
                datasets = cat_data.get("datasets", [])
                if not datasets:
                    continue

                cat_item = QTreeWidgetItem([f"{category} ({len(datasets)})", "", ""])
                cat_item.setFont(0, QFont("", -1, QFont.Bold))

                for dataset in datasets:
                    source = dataset.get("source", "unknown")
                    source_display = (
                        "Official"
                        if source == "official"
                        else "Community" if source == "community" else source
                    )
                    ds_item = QTreeWidgetItem(
                        [
                            dataset.get("name", dataset.get("id", "Unknown"))[:55],
                            dataset.get("type", "Unknown"),
                            source_display,
                        ]
                    )
                    ds_item.setData(0, Qt.UserRole, dataset)
                    ds_item.setToolTip(0, dataset.get("id", ""))
                    cat_item.addChild(ds_item)

                self.catalog_tree.addTopLevelItem(cat_item)

            # Don't expand any nodes by default - keep tree collapsed

        except Exception as e:
            self._show_error(f"Failed to populate catalog: {str(e)}")

    def _filter_tree_by_source(self):
        """Filter tree by source (official/community) and update category counts."""
        source = self.source_filter.currentData()
        total_visible = 0

        for i in range(self.catalog_tree.topLevelItemCount()):
            cat_item = self.catalog_tree.topLevelItem(i)
            visible_count = 0

            for j in range(cat_item.childCount()):
                ds_item = cat_item.child(j)
                dataset = ds_item.data(0, Qt.UserRole)

                if source is None or dataset.get("source") == source:
                    ds_item.setHidden(False)
                    visible_count += 1
                else:
                    ds_item.setHidden(True)

            # Update category count in the label
            original_text = cat_item.text(0)
            # Extract category name (remove old count)
            if " (" in original_text:
                category_name = original_text.rsplit(" (", 1)[0]
            else:
                category_name = original_text

            # Update with new count
            cat_item.setText(0, f"{category_name} ({visible_count})")
            cat_item.setHidden(visible_count == 0)
            total_visible += visible_count

        # Update status label with total count
        source_name = self.source_filter.currentText()
        self._show_success(f"Showing {total_visible} datasets ({source_name})")

    def _on_dataset_selected(self, item, _column):
        """Handle dataset selection in tree."""
        dataset = item.data(0, Qt.UserRole)
        if dataset:
            self._selected_dataset = dataset
            self._show_dataset_info(dataset)
            self._reset_vis_params()
            self.add_map_btn.setEnabled(True)
            self.configure_btn.setEnabled(True)
            # Enable time series button only for ImageCollections
            is_image_collection = dataset.get("type", "").lower() == "imagecollection"
            self.timeseries_btn.setEnabled(is_image_collection)
        else:
            self._selected_dataset = None
            self.info_text.clear()
            self.add_map_btn.setEnabled(False)
            self.configure_btn.setEnabled(False)
            self.timeseries_btn.setEnabled(False)

    def _on_dataset_double_clicked(self, item, _column):
        """Handle double-click on dataset."""
        dataset = item.data(0, Qt.UserRole)
        if dataset:
            self._add_dataset_to_map(dataset)

    def _show_dataset_info(self, dataset):
        """Display dataset information."""
        # Stop any previous thumbnail loading
        if self._thumbnail_thread and self._thumbnail_thread.isRunning():
            self._thumbnail_thread.terminate()
            self._thumbnail_thread.wait()

        source_badge = f"<span style='background-color: {'#4285F4' if dataset.get('source') == 'official' else '#34A853'}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px;'>{dataset.get('source', 'unknown').upper()}</span>"

        info_lines = [
            f"{source_badge}",
            f"<b>Name:</b> {dataset.get('name', dataset.get('title', 'Unknown'))}",
            f"<b>ID:</b> <code>{dataset.get('id', 'Unknown')}</code>",
            f"<b>Type:</b> {dataset.get('type', 'Unknown')}",
            f"<b>Provider:</b> {dataset.get('provider', 'Unknown')}",
        ]

        # Placeholder for thumbnail (will be loaded asynchronously)
        thumbnail_url = dataset.get("thumbnail", "")
        thumbnail_placeholder = ""
        if thumbnail_url:
            thumbnail_placeholder = (
                f"<div id='thumbnail-placeholder'><i>Loading thumbnail...</i></div>"
            )
            info_lines.append(thumbnail_placeholder)

        info_lines.append("")
        info_lines.append(
            f"<b>Description:</b><br>{dataset.get('description', 'No description')[:300]}..."
        )

        if dataset.get("start_date"):
            info_lines.append(f"<b>Start Date:</b> {dataset['start_date']}")

        if dataset.get("end_date"):
            info_lines.append(f"<b>End Date:</b> {dataset['end_date']}")

        keywords = dataset.get("keywords", [])
        if keywords:
            if isinstance(keywords, list):
                info_lines.append(f"<b>Keywords:</b> {', '.join(keywords[:10])}")
            else:
                info_lines.append(f"<b>Keywords:</b> {keywords}")

        # For community datasets, prioritize docs link over sample_code
        if dataset.get("source") == "community":
            docs_url = dataset.get("docs", "")
            sample_code_url = dataset.get("sample_code", "")

            if docs_url:
                info_lines.append(f"<b>Docs:</b> <a href='{docs_url}'>{docs_url}</a>")
            if sample_code_url and sample_code_url != docs_url:
                info_lines.append(
                    f"<b>Sample Code:</b> <a href='{sample_code_url}'>{sample_code_url}</a>"
                )
        else:
            # For official datasets, show the URL and script
            if dataset.get("url"):
                url = dataset["url"]
                info_lines.append(f"<b>URL:</b> <a href='{url}'>{url}</a>")

            if dataset.get("script"):
                script = dataset["script"]
                info_lines.append(f"<b>Script:</b> <a href='{script}'>{script}</a>")

        # Store current HTML without thumbnail
        self._current_info_html = "<br>".join(info_lines)
        self.info_text.setHtml(self._current_info_html)

        # Load thumbnail asynchronously if available
        if thumbnail_url:
            self._thumbnail_thread = ThumbnailLoaderThread(thumbnail_url)
            self._thumbnail_thread.finished.connect(self._on_thumbnail_loaded)
            self._thumbnail_thread.error.connect(self._on_thumbnail_error)
            self._thumbnail_thread.start()

    def _on_thumbnail_loaded(self, img_data_url):
        """Handle thumbnail loaded successfully."""
        # Replace placeholder with actual image
        thumbnail_html = f"<br><img src='{img_data_url}' width='300' style='border: 1px solid #ccc; border-radius: 4px;'><br>"
        self._current_info_html = self._current_info_html.replace(
            "<div id='thumbnail-placeholder'><i>Loading thumbnail...</i></div>",
            thumbnail_html,
        )
        self.info_text.setHtml(self._current_info_html)

    def _on_thumbnail_error(self, _error):
        """Handle thumbnail load error."""
        # Remove placeholder on error (silently ignore the error)
        self._current_info_html = self._current_info_html.replace(
            "<div id='thumbnail-placeholder'><i>Loading thumbnail...</i></div>", ""
        )
        self.info_text.setHtml(self._current_info_html)

    def _show_search_dataset_info(self, dataset):
        """Display dataset information in the search tab.

        This is similar to _show_dataset_info but displays in the search info panel.
        """
        source_badge = f"<span style='background-color: {'#4285F4' if dataset.get('source') == 'official' else '#34A853'}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px;'>{dataset.get('source', 'unknown').upper()}</span>"

        info_lines = [
            f"{source_badge}",
            f"<b>Name:</b> {dataset.get('name', dataset.get('title', 'Unknown'))}",
            f"<b>ID:</b> <code>{dataset.get('id', 'Unknown')}</code>",
            f"<b>Type:</b> {dataset.get('type', 'Unknown')}",
            f"<b>Provider:</b> {dataset.get('provider', 'Unknown')}",
        ]

        # Add thumbnail preview if available
        thumbnail_url = dataset.get("thumbnail", "")
        if thumbnail_url:
            # For search results, we'll load thumbnails inline (simpler approach)
            try:
                import base64
                from urllib.request import urlopen, Request

                req = Request(thumbnail_url, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(req, timeout=5) as response:
                    img_data = response.read()
                    img_base64 = base64.b64encode(img_data).decode("utf-8")
                    img_format = "png" if thumbnail_url.endswith(".png") else "jpeg"
                    info_lines.append(
                        f"<br><img src='data:image/{img_format};base64,{img_base64}' width='300' style='border: 1px solid #ccc; border-radius: 4px;'><br>"
                    )
            except Exception:
                # If thumbnail loading fails, just skip it
                pass

        info_lines.append("")
        info_lines.append(
            f"<b>Description:</b><br>{dataset.get('description', 'No description')[:300]}..."
        )

        if dataset.get("start_date"):
            info_lines.append(f"<b>Start Date:</b> {dataset['start_date']}")

        if dataset.get("end_date"):
            info_lines.append(f"<b>End Date:</b> {dataset['end_date']}")

        keywords = dataset.get("keywords", [])
        if keywords:
            if isinstance(keywords, list):
                info_lines.append(f"<b>Keywords:</b> {', '.join(keywords[:10])}")
            else:
                info_lines.append(f"<b>Keywords:</b> {keywords}")

        # For community datasets, prioritize docs link over sample_code
        if dataset.get("source") == "community":
            docs_url = dataset.get("docs", "")
            sample_code_url = dataset.get("sample_code", "")

            if docs_url:
                info_lines.append(f"<b>Docs:</b> <a href='{docs_url}'>{docs_url}</a>")
            if sample_code_url and sample_code_url != docs_url:
                info_lines.append(
                    f"<b>Sample Code:</b> <a href='{sample_code_url}'>{sample_code_url}</a>"
                )
        else:
            # For official datasets, show the URL and script
            if dataset.get("url"):
                url = dataset["url"]
                info_lines.append(f"<b>URL:</b> <a href='{url}'>{url}</a>")

            if dataset.get("script"):
                script = dataset["script"]
                info_lines.append(f"<b>Script:</b> <a href='{script}'>{script}</a>")

        self.search_info_text.setHtml("<br>".join(info_lines))

    def _add_selected_to_map(self):
        """Add the selected dataset to the map."""
        if self._selected_dataset:
            self._add_dataset_to_map(self._selected_dataset)

    def _configure_and_add(self):
        """Configure and add the selected dataset."""
        if self._selected_dataset:
            # Populate the load tab with dataset info
            self.dataset_id_input.setText(self._selected_dataset.get("id", ""))
            self.layer_name_input.setText(self._selected_dataset.get("name", "")[:50])

            # Switch to Load tab (index 3 after Time Series tab)
            self.tab_widget.setCurrentIndex(3)

    def _configure_timeseries(self):
        """Configure time series from the selected dataset."""
        if self._selected_dataset:
            asset_id = self._selected_dataset.get("id", "")
            name = self._selected_dataset.get("name", asset_id.split("/")[-1])[:40]

            # Populate the time series tab with dataset info
            self.ts_dataset_id_input.setText(asset_id)
            self.ts_layer_name_input.setText(f"{name} Time Series")

            # Try to set reasonable date range from dataset metadata
            start_date = self._selected_dataset.get("start_date", "")
            end_date = self._selected_dataset.get("end_date", "")

            if start_date:
                try:
                    from datetime import datetime

                    # Parse date in various formats
                    for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"]:
                        try:
                            dt = datetime.strptime(start_date[:10], "%Y-%m-%d")
                            self.ts_start_date.setDate(dt)
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass

            if end_date:
                try:
                    from datetime import datetime

                    for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"]:
                        try:
                            dt = datetime.strptime(end_date[:10], "%Y-%m-%d")
                            self.ts_end_date.setDate(dt)
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass

            # Switch to Time Series tab (index 2)
            self.tab_widget.setCurrentIndex(2)

    def _add_dataset_to_map(self, dataset):
        """Add a dataset to the map with default visualization."""
        if ee is None:
            QMessageBox.warning(
                self,
                "Warning",
                "Earth Engine API not available. Please install earthengine-api.",
            )
            return

        asset_id = dataset.get("id")
        if not asset_id:
            self._show_error("Dataset has no ID")
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        try:
            self._show_progress(f"Loading {asset_id}...")
            QCoreApplication.processEvents()

            # Check if we have JavaScript code for this asset
            if self._run_js_code_for_asset(asset_id):
                name = dataset.get("name", asset_id.split("/")[-1])[:50]
                self._show_success(f"Added layer: {name} (from sample code)")
                return

            vis_params = dataset.get("vis_params", {})
            name = dataset.get("name", asset_id.split("/")[-1])[:50]

            # Auto-detect the asset type
            from ..core.ee_utils import detect_asset_type, add_ee_layer

            catalog_type = dataset.get("type", "").lower()

            # Try to load based on catalog type first, then fall back to detection
            ee_object = None
            actual_type = None

            try:
                if catalog_type == "image":
                    ee_object = ee.Image(asset_id)
                    ee_object.bandNames().getInfo()  # Verify it works
                    actual_type = "Image"
                elif catalog_type == "imagecollection":
                    collection = ee.ImageCollection(asset_id)
                    collection.size().getInfo()  # Verify it works
                    ee_object = collection.mosaic()
                    actual_type = "ImageCollection"
                elif catalog_type == "featurecollection" or catalog_type == "table":
                    ee_object = ee.FeatureCollection(asset_id)
                    ee_object.size().getInfo()  # Verify it works
                    actual_type = "FeatureCollection"
            except Exception:
                # Catalog type was wrong, auto-detect
                pass

            # If loading based on catalog type failed, auto-detect
            if ee_object is None:
                self._show_progress(f"Detecting asset type for {asset_id}...")
                QCoreApplication.processEvents()
                actual_type = detect_asset_type(asset_id)

                if actual_type == "Image":
                    ee_object = ee.Image(asset_id)
                elif actual_type == "ImageCollection":
                    ee_object = ee.ImageCollection(asset_id).mosaic()
                elif actual_type == "FeatureCollection":
                    ee_object = ee.FeatureCollection(asset_id)
                else:
                    raise ValueError(f"Could not determine asset type for: {asset_id}")

            # Add layer
            add_ee_layer(ee_object, vis_params, name)
            self._show_success(f"Added layer: {name} ({actual_type})")

        except Exception as e:
            self._show_error(f"Failed to load dataset: {str(e)}")
        finally:
            QApplication.restoreOverrideCursor()

    def _perform_search(self):
        """Perform dataset search."""
        try:
            from ..core.catalog_data import search_datasets

            query = self.search_input.text().strip()
            category = self.category_filter.currentData()
            data_type = self.type_filter.currentData()
            source = self.search_source_filter.currentData()

            results = search_datasets(
                query=query,
                category=category,
                data_type=data_type,
                source=source,
            )

            self.search_results.clear()
            self.search_info_text.clear()

            for dataset in results[:500]:  # Limit to 500 results
                item = QTreeWidgetItem(
                    [
                        dataset.get("name", dataset.get("id", "Unknown"))[:50],
                        dataset.get("type", "Unknown"),
                        dataset.get("source", "unknown"),
                    ]
                )
                item.setData(0, Qt.UserRole, dataset)
                item.setToolTip(0, dataset.get("id", ""))
                self.search_results.addTopLevelItem(item)

            self._show_success(
                f"Found {len(results)} datasets"
                + (f" (showing first 500)" if len(results) > 500 else "")
            )

        except Exception as e:
            self._show_error(f"Search failed: {str(e)}")

    def _on_search_result_selected(self, item, _column):
        """Handle search result selection."""
        dataset = item.data(0, Qt.UserRole)
        if dataset:
            self._selected_dataset = dataset
            self._show_search_dataset_info(dataset)
            self._reset_vis_params()
            # Enable time series button only for ImageCollections
            is_image_collection = dataset.get("type", "").lower() == "imagecollection"
            self.search_timeseries_btn.setEnabled(is_image_collection)
        else:
            self.search_timeseries_btn.setEnabled(False)

    def _on_search_result_double_clicked(self, item, _column):
        """Handle double-click on search result."""
        dataset = item.data(0, Qt.UserRole)
        if dataset:
            self._add_dataset_to_map(dataset)

    def _add_search_result_to_map(self):
        """Add selected search result to map."""
        items = self.search_results.selectedItems()
        if items:
            dataset = items[0].data(0, Qt.UserRole)
            if dataset:
                self._add_dataset_to_map(dataset)

    def _configure_search_result(self):
        """Configure and add selected search result."""
        items = self.search_results.selectedItems()
        if items:
            dataset = items[0].data(0, Qt.UserRole)
            if dataset:
                # Populate the load tab with dataset info
                self.dataset_id_input.setText(dataset.get("id", ""))
                self.layer_name_input.setText(dataset.get("name", "")[:50])
                # Switch to Load tab (index 3 after Time Series tab)
                self.tab_widget.setCurrentIndex(3)

    def _configure_search_timeseries(self):
        """Configure time series from selected search result."""
        items = self.search_results.selectedItems()
        if items:
            dataset = items[0].data(0, Qt.UserRole)
            if dataset:
                # Store as selected dataset and use common method
                self._selected_dataset = dataset
                self._configure_timeseries()

    def _fetch_images(self):
        """Fetch available images from the ImageCollection."""
        if ee is None:
            QMessageBox.warning(self, "Warning", "Earth Engine API not available.")
            return

        asset_id = self.dataset_id_input.text().strip()
        if not asset_id:
            QMessageBox.warning(self, "Warning", "Please enter an asset ID.")
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        self.fetch_images_btn.setEnabled(False)

        try:
            self._show_progress("Fetching images...")
            QCoreApplication.processEvents()

            # Build filtered collection
            collection = ee.ImageCollection(asset_id)

            # Apply date filter
            if self.use_date_filter.isChecked():
                start = self.start_date.date().toString("yyyy-MM-dd")
                end = self.end_date.date().toString("yyyy-MM-dd")
                collection = collection.filterDate(start, end)

            # Apply spatial filter
            bbox = self._get_spatial_filter_load()
            if bbox:
                geometry = ee.Geometry.Rectangle(bbox)
                collection = collection.filterBounds(geometry)

            # Apply cloud filter
            if self.use_cloud_filter.isChecked():
                cloud_cover = self.cloud_cover_spin.value()
                custom_cloud_prop = self.cloud_property_input.text().strip()
                cloud_prop = self._get_cloud_property(asset_id, custom_cloud_prop)
                collection = collection.filter(ee.Filter.lt(cloud_prop, cloud_cover))

            # Apply property filters
            property_filters = self._parse_property_filters(
                self.load_property_filters.toPlainText()
            )
            collection = self._apply_property_filters(collection, property_filters)

            self._filtered_collection = collection

            # Start background thread to fetch images
            limit = self.image_limit_spin.value()
            self._image_list_thread = ImageListLoaderThread(collection, limit)
            self._image_list_thread.finished.connect(self._on_images_fetched)
            self._image_list_thread.error.connect(self._on_images_error)
            self._image_list_thread.progress.connect(
                lambda msg: self.status_label.setText(msg)
            )
            self._image_list_thread.start()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.fetch_images_btn.setEnabled(True)
            self._show_error(f"Failed to fetch images: {str(e)}")

    def _on_images_fetched(self, images_info):
        """Handle images fetched successfully."""
        QApplication.restoreOverrideCursor()
        self.fetch_images_btn.setEnabled(True)

        self.image_list_widget.clear()
        for img in images_info:
            item = QListWidgetItem(f"{img['date']} - {img['id'].split('/')[-1]}")
            item.setData(Qt.UserRole, img)
            self.image_list_widget.addItem(item)

        self._show_success(f"Found {len(images_info)} images")

    def _on_images_error(self, error):
        """Handle images fetch error."""
        QApplication.restoreOverrideCursor()
        self.fetch_images_btn.setEnabled(True)
        self._show_error(f"Failed to fetch images: {error}")

    def _load_dataset(self):
        """Load dataset with custom filters and visualization."""
        if ee is None:
            QMessageBox.warning(
                self,
                "Warning",
                "Earth Engine API not available. Please install earthengine-api.",
            )
            return

        asset_id = self.dataset_id_input.text().strip()
        if not asset_id:
            QMessageBox.warning(self, "Warning", "Please enter an asset ID.")
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        try:
            self._show_progress(f"Loading {asset_id}...")
            QCoreApplication.processEvents()

            # Check if loading individual images
            if self.load_individual_radio.isChecked():
                selected_items = self.image_list_widget.selectedItems()
                if not selected_items:
                    QMessageBox.warning(
                        self, "Warning", "Please select images from the list."
                    )
                    return

                # Load each selected image
                vis_params = self._build_vis_params()
                for item in selected_items:
                    img_info = item.data(Qt.UserRole)
                    image_id = img_info["id"]
                    name = f"{self.layer_name_input.text().strip() or asset_id.split('/')[-1]} - {img_info['date']}"

                    ee_image = ee.Image(image_id)
                    from ..core.ee_utils import add_ee_layer

                    add_ee_layer(ee_image, vis_params, name[:50])

                self._show_success(f"Added {len(selected_items)} image layer(s)")
            else:
                # Load as composite - auto-detect asset type
                from ..core.ee_utils import detect_asset_type, add_ee_layer

                self._show_progress(f"Detecting asset type for {asset_id}...")
                QCoreApplication.processEvents()

                asset_type = detect_asset_type(asset_id)

                if asset_type == "ImageCollection":
                    ee_object = self._load_image_collection(asset_id)
                elif asset_type == "Image":
                    ee_object = ee.Image(asset_id)
                elif asset_type == "FeatureCollection":
                    ee_object = ee.FeatureCollection(asset_id)
                else:
                    # Try each type until one works
                    for loader_fn in [
                        ee.Image,
                        lambda x: ee.ImageCollection(x).mosaic(),
                        ee.FeatureCollection,
                    ]:
                        try:
                            ee_object = loader_fn(asset_id)
                            break
                        except Exception:
                            continue
                    else:
                        raise ValueError(f"Could not load asset: {asset_id}")

                # Build vis_params based on asset type
                is_feature_collection = asset_type == "FeatureCollection" or isinstance(
                    ee_object, ee.FeatureCollection
                )
                vis_params = self._build_vis_params(
                    for_feature_collection=is_feature_collection
                )
                name = self.layer_name_input.text().strip() or asset_id.split("/")[-1]

                add_ee_layer(ee_object, vis_params, name[:50])
                self._show_success(f"Added layer: {name} ({asset_type})")

        except Exception as e:
            self._show_error(f"Failed to load dataset: {str(e)}")
        finally:
            QApplication.restoreOverrideCursor()

    def _load_image_collection(self, asset_id):
        """Load and filter an ImageCollection."""
        from ..core.ee_utils import filter_image_collection

        collection = ee.ImageCollection(asset_id)

        start_date = None
        end_date = None
        if self.use_date_filter.isChecked():
            start_date = self.start_date.date().toString("yyyy-MM-dd")
            end_date = self.end_date.date().toString("yyyy-MM-dd")

        cloud_cover = None
        custom_cloud_prop = self.cloud_property_input.text().strip()
        cloud_property = self._get_cloud_property(asset_id, custom_cloud_prop)
        if self.use_cloud_filter.isChecked():
            cloud_cover = self.cloud_cover_spin.value()

        bbox = self._get_spatial_filter_load()

        collection = filter_image_collection(
            collection,
            start_date=start_date,
            end_date=end_date,
            bbox=bbox,
            cloud_cover=cloud_cover,
            cloud_property=cloud_property,
        )

        # Apply property filters
        property_filters = self._parse_property_filters(
            self.load_property_filters.toPlainText()
        )
        collection = self._apply_property_filters(collection, property_filters)

        method = self.agg_method.currentText()
        if method == "mosaic":
            return collection.mosaic()
        elif method == "median":
            return collection.median()
        elif method == "mean":
            return collection.mean()
        elif method == "min":
            return collection.min()
        elif method == "max":
            return collection.max()
        elif method == "first":
            return collection.first()
        else:
            return collection.mosaic()

    def _reset_vis_params(self):
        """Reset visualization parameters to default values."""
        self.bands_input.clear()
        self.vis_min_input.clear()
        self.vis_max_input.clear()
        self.palette_input.clear()

    def _build_vis_params(self, for_feature_collection: bool = False):
        """Build visualization parameters from UI inputs.

        Args:
            for_feature_collection: If True, exclude min/max params not supported by FeatureCollection.
        """
        vis_params = {}

        bands = self.bands_input.text().strip()
        if bands and not for_feature_collection:
            # Strip whitespace and quotes from each band name, filter out empty values
            vis_params["bands"] = [
                b.strip().strip("\"'")
                for b in bands.split(",")
                if b.strip().strip("\"'")
            ]

        # Parse min/max values if provided
        vis_min_text = self.vis_min_input.text().strip()
        vis_max_text = self.vis_max_input.text().strip()
        if not for_feature_collection:
            vis_min = None
            vis_max = None

            if vis_min_text:
                try:
                    vis_min = float(vis_min_text)
                    vis_params["min"] = vis_min
                except ValueError:
                    pass  # Skip if value is not a valid number

            if vis_max_text:
                try:
                    vis_max = float(vis_max_text)
                    vis_params["max"] = vis_max
                except ValueError:
                    pass  # Skip if value is not a valid number

            # If both values are provided, enforce that max > min as in original behavior.
            if vis_min is not None and vis_max is not None and vis_max <= vis_min:
                vis_params.pop("min", None)
                vis_params.pop("max", None)
        palette = self.palette_input.text().strip()
        if palette:
            # Check if it's a matplotlib colormap name
            palette_colors = self._get_colormap_colors(palette)
            if palette_colors:
                vis_params["palette"] = palette_colors
            else:
                # Strip whitespace and quotes from each color, filter out empty values
                vis_params["palette"] = [
                    p.strip().strip("\"'")
                    for p in palette.split(",")
                    if p.strip().strip("\"'")
                ]

        return vis_params

    def _get_colormap_colors(self, name: str, n_colors: int = 256) -> list:
        """Convert a matplotlib colormap name to a list of hex colors.

        Args:
            name: Colormap name (e.g., 'viridis', 'terrain', 'RdYlGn').
            n_colors: Number of colors to sample from the colormap.

        Returns:
            List of hex color strings, or empty list if not a valid colormap.
        """
        # Check if it looks like a color list rather than a colormap name
        if "," in name or name.startswith("#") or name.startswith("rgb"):
            return []

        try:
            import matplotlib.pyplot as plt
            import matplotlib.colors as mcolors

            # Try to get the colormap
            try:
                cmap = plt.get_cmap(name)
            except ValueError:
                return []

            # Sample colors from the colormap
            colors = []
            for i in range(n_colors):
                rgba = cmap(i / (n_colors - 1))
                hex_color = mcolors.to_hex(rgba)
                colors.append(hex_color)

            return colors
        except ImportError:
            # matplotlib not available, return empty list
            return []
        except Exception:
            return []

    def _preview_dataset(self):
        """Preview dataset information without loading (runs in background thread)."""
        if ee is None:
            QMessageBox.warning(self, "Warning", "Earth Engine API not available.")
            return

        asset_id = self.dataset_id_input.text().strip()
        if not asset_id:
            QMessageBox.warning(self, "Warning", "Please enter an asset ID.")
            return

        self.preview_btn.setEnabled(False)

        # Check for images in the list
        selected_images = None
        if self.image_list_widget.isVisible() and self.image_list_widget.count() > 0:
            selected_items = self.image_list_widget.selectedItems()
            if selected_items:
                # Preview only selected items
                selected_images = []
                for item in selected_items:
                    img_info = item.data(Qt.UserRole)
                    if img_info:
                        selected_images.append(img_info)
                self._show_progress(
                    f"Getting info for {len(selected_images)} selected image(s)..."
                )
            else:
                # No selection - preview all items in the list
                selected_images = []
                for i in range(self.image_list_widget.count()):
                    item = self.image_list_widget.item(i)
                    img_info = item.data(Qt.UserRole)
                    if img_info:
                        selected_images.append(img_info)
                self._show_progress(
                    f"Getting info for {len(selected_images)} image(s) in list..."
                )
        else:
            self._show_progress(f"Getting info for {asset_id}...")

        # Get filter params
        use_date_filter = self.use_date_filter.isChecked()
        start_date = (
            self.start_date.date().toString("yyyy-MM-dd") if use_date_filter else None
        )
        end_date = (
            self.end_date.date().toString("yyyy-MM-dd") if use_date_filter else None
        )

        # Start background thread
        self._preview_thread = PreviewInfoThread(
            asset_id, use_date_filter, start_date, end_date, selected_images
        )
        self._preview_thread.finished.connect(self._on_preview_finished)
        self._preview_thread.error.connect(self._on_preview_error)
        self._preview_thread.progress.connect(
            lambda msg: self.status_label.setText(msg)
        )
        self._preview_thread.start()

    def _on_preview_finished(self, info_text):
        """Handle preview info finished."""
        self.preview_btn.setEnabled(True)
        QMessageBox.information(self, "Dataset Info", info_text)
        self._show_success("Info retrieved")

    def _on_preview_error(self, error):
        """Handle preview info error."""
        self.preview_btn.setEnabled(True)
        self._show_error(f"Failed to get info: {error}")

    def _copy_code_snippet(self):
        """Generate and copy Python code snippet for loading the dataset."""
        asset_id = self.dataset_id_input.text().strip()
        if not asset_id:
            QMessageBox.warning(self, "Warning", "Please enter an asset ID.")
            return

        layer_name = self.layer_name_input.text().strip() or asset_id.split("/")[-1]

        # Build the code
        code_lines = [
            "import ee",
            "import geemap",
            "",
            "m = geemap.Map()",
            "",
        ]

        # Try to detect the actual asset type
        asset_type = None

        # First, try to use the type from selected dataset if available
        if self._selected_dataset and self._selected_dataset.get("type"):
            catalog_type = self._selected_dataset.get("type", "").lower()
            if catalog_type == "image":
                asset_type = "Image"
            elif catalog_type == "imagecollection":
                asset_type = "ImageCollection"
            elif catalog_type in ["featurecollection", "table"]:
                asset_type = "FeatureCollection"

        # If type still unknown, try to detect it (requires API call)
        if not asset_type and ee is not None:
            try:
                from ..core.ee_utils import detect_asset_type

                asset_type = detect_asset_type(asset_id)
            except Exception:
                # If detection fails, make a best guess based on UI state
                if (
                    self.use_date_filter.isChecked()
                    or self.use_cloud_filter.isChecked()
                    or self.load_individual_radio.isChecked()
                ):
                    asset_type = "ImageCollection"
                else:
                    asset_type = "Image"

        # Generate appropriate code based on asset type
        if asset_type == "ImageCollection":
            # ImageCollection code
            code_lines.append(f"# Load ImageCollection")
            code_lines.append(f"collection = ee.ImageCollection('{asset_id}')")

            # Add filters
            if self.use_date_filter.isChecked():
                start = self.start_date.date().toString("yyyy-MM-dd")
                end = self.end_date.date().toString("yyyy-MM-dd")
                code_lines.append(
                    f"collection = collection.filterDate('{start}', '{end}')"
                )

            if self.use_cloud_filter.isChecked():
                cloud_cover = self.cloud_cover_spin.value()
                cloud_prop = self._get_cloud_property(asset_id)
                code_lines.append(
                    f"collection = collection.filter(ee.Filter.lt('{cloud_prop}', {cloud_cover}))"
                )

            # Spatial filter
            bbox = self._get_spatial_filter_load()
            if bbox:
                west, south, east, north = bbox
                code_lines.append(f"# Spatial filter (EPSG:4326)")
                code_lines.append(
                    f"geometry = ee.Geometry.Rectangle([{west}, {south}, {east}, {north}])"
                )
                code_lines.append(f"collection = collection.filterBounds(geometry)")

            # Add composite method
            method = self.agg_method.currentText()
            code_lines.append(f"")
            code_lines.append(f"# Create composite")
            code_lines.append(f"image = collection.{method}()")

            # Add visualization parameters
            code_lines.append("")
            code_lines.append("# Visualization parameters")

            vis_parts = []
            bands = self.bands_input.text().strip()
            if bands:
                band_list = [
                    b.strip().strip("\"'")
                    for b in bands.split(",")
                    if b.strip().strip("\"'")
                ]
                vis_parts.append(f"'bands': {band_list}")

            vis_min_text = self.vis_min_input.text().strip()
            vis_max_text = self.vis_max_input.text().strip()
            if vis_min_text and vis_max_text:
                try:
                    vis_min = float(vis_min_text)
                    vis_max = float(vis_max_text)
                    if vis_max >= vis_min:
                        vis_parts.append(f"'min': {vis_min}")
                        vis_parts.append(f"'max': {vis_max}")
                except ValueError:
                    # Ignore invalid numeric visualization parameters; omit min/max
                    pass

            palette = self.palette_input.text().strip()
            if palette:
                if "," in palette:
                    palette_list = [
                        p.strip().strip("\"'")
                        for p in palette.split(",")
                        if p.strip().strip("\"'")
                    ]
                    vis_parts.append(f"'palette': {palette_list}")
                else:
                    vis_parts.append(f"'palette': '{palette}'")

            if vis_parts:
                code_lines.append("vis_params = {" + ", ".join(vis_parts) + "}")
            else:
                code_lines.append("vis_params = {}")

            # Add to map
            code_lines.append("")
            code_lines.append(f"# Add to map")
            code_lines.append(f"m.add_layer(image, vis_params, '{layer_name}')")

        elif asset_type == "FeatureCollection":
            # FeatureCollection code
            code_lines.append(f"# Load FeatureCollection")
            code_lines.append(f"fc = ee.FeatureCollection('{asset_id}')")
            code_lines.append("")
            code_lines.append("# Visualization parameters")

            vis_parts = []
            palette = self.palette_input.text().strip()
            if palette:
                # For FeatureCollection, use color instead of palette
                if "," in palette:
                    colors = [p.strip() for p in palette.split(",")]
                    vis_parts.append(f"'color': '{colors[0]}'")
                else:
                    vis_parts.append(f"'color': '{palette}'")
            else:
                vis_parts.append("'color': 'blue'")

            if vis_parts:
                code_lines.append("vis_params = {" + ", ".join(vis_parts) + "}")
            else:
                code_lines.append("vis_params = {'color': 'blue'}")

            # Add to map
            code_lines.append("")
            code_lines.append(f"# Add to map")
            code_lines.append(f"m.add_layer(fc, vis_params, '{layer_name}')")

        else:  # Image
            # Single Image code
            code_lines.append(f"# Load Image")
            code_lines.append(f"image = ee.Image('{asset_id}')")
            code_lines.append("")
            code_lines.append("# Visualization parameters")

            vis_parts = []
            bands = self.bands_input.text().strip()
            if bands:
                band_list = [
                    b.strip().strip("\"'")
                    for b in bands.split(",")
                    if b.strip().strip("\"'")
                ]
                vis_parts.append(f"'bands': {band_list}")

            vis_min_text = self.vis_min_input.text().strip()
            vis_max_text = self.vis_max_input.text().strip()

            vis_min = None
            vis_max = None

            if vis_min_text:
                try:
                    vis_min = float(vis_min_text)
                except ValueError:
                    vis_min = None

            if vis_max_text:
                try:
                    vis_max = float(vis_max_text)
                except ValueError:
                    vis_max = None

            if vis_min is not None and vis_max is not None:
                if vis_max > vis_min:
                    vis_parts.append(f"'min': {vis_min}")
                    vis_parts.append(f"'max': {vis_max}")
            elif vis_min is not None:
                vis_parts.append(f"'min': {vis_min}")
            elif vis_max is not None:
                vis_parts.append(f"'max': {vis_max}")
            palette = self.palette_input.text().strip()
            if palette:
                if "," in palette:
                    palette_list = [
                        p.strip().strip("\"'")
                        for p in palette.split(",")
                        if p.strip().strip("\"'")
                    ]
                    vis_parts.append(f"'palette': {palette_list}")
                else:
                    vis_parts.append(f"'palette': '{palette}'")

            if vis_parts:
                code_lines.append("vis_params = {" + ", ".join(vis_parts) + "}")
            else:
                code_lines.append("vis_params = {}")

            # Add to map
            code_lines.append("")
            code_lines.append(f"# Add to map")
            code_lines.append(f"m.add_layer(image, vis_params, '{layer_name}')")

        code = "\n".join(code_lines)

        # Copy to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(code)

        self._show_success("Code snippet copied to clipboard!")

        # Paste code to Code tab and switch to it
        self.code_input.setPlainText(code)
        self.tab_widget.setCurrentIndex(
            4
        )  # Switch to Code tab (index 4 after Time Series tab)

    def _run_code(self):
        """Execute the code in the console."""
        code = self.code_input.toPlainText()
        if not code.strip():
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        try:
            import sys
            import types

            # Create a QGIS-compatible Map class
            QGISMap = self._create_qgis_map_class()

            # Create namespace for execution
            namespace = {
                "iface": self.iface,
            }

            # Import ee
            try:
                import ee

                namespace["ee"] = ee
            except ImportError:
                pass

            # Create a patched geemap module that uses our QGISMap
            patched_geemap = types.ModuleType("geemap")
            patched_geemap.Map = QGISMap

            # Try to copy commonly used attributes from real geemap
            try:
                import geemap as real_geemap

                for attr in [
                    "ee_initialize",
                    "basemaps",
                    "coreutils",
                    "__version__",
                    "create_timeseries",
                ]:
                    if hasattr(real_geemap, attr):
                        setattr(patched_geemap, attr, getattr(real_geemap, attr))
            except ImportError:
                pass

            # Patch sys.modules to ensure our geemap is used for imports
            original_geemap = sys.modules.get("geemap")
            sys.modules["geemap"] = patched_geemap

            # Also patch qgis_geemap if it exists, to prevent it from being used
            original_qgis_geemap = sys.modules.get("qgis_geemap.core.qgis_map")

            # Add geemap to namespace
            namespace["geemap"] = patched_geemap

            # Pre-create a Map instance as 'm' for convenience
            namespace["m"] = QGISMap()
            namespace["Map"] = QGISMap

            try:
                # Execute the code
                exec(code, namespace)

                self.code_output.setPlainText("✓ Code executed successfully!")
                self.code_output.setStyleSheet("color: green;")
                self._show_success("Code executed")
            finally:
                # Restore original modules
                if original_geemap is not None:
                    sys.modules["geemap"] = original_geemap
                else:
                    sys.modules.pop("geemap", None)

                if original_qgis_geemap is not None:
                    sys.modules["qgis_geemap.core.qgis_map"] = original_qgis_geemap

        except Exception as e:
            import traceback

            error_msg = str(e)
            tb = traceback.format_exc()
            self.code_output.setPlainText(f"✗ Error: {error_msg}\n\n{tb}")
            self.code_output.setStyleSheet("color: red;")
        finally:
            QApplication.restoreOverrideCursor()

    def _create_qgis_map_class(self):
        """Create a QGIS-compatible Map class that mimics geemap.Map."""
        iface = self.iface

        class QGISMap:
            """A Map class compatible with geemap API for QGIS."""

            def __init__(self, center=None, zoom=None, **kwargs):
                self._iface = iface
                self._layers = {}
                # Ignore center and zoom for QGIS

            def add_layer(
                self, ee_object, vis_params=None, name="Layer", shown=True, opacity=1.0
            ):
                """Add an Earth Engine layer to the map."""
                from ..core.ee_utils import add_ee_layer

                return add_ee_layer(ee_object, vis_params or {}, name, shown, opacity)

            def addLayer(
                self, ee_object, vis_params=None, name="Layer", shown=True, opacity=1.0
            ):
                """Alias for add_layer (geemap compatibility)."""
                return self.add_layer(ee_object, vis_params, name, shown, opacity)

            def add_ee_layer(
                self, ee_object, vis_params=None, name="Layer", shown=True, opacity=1.0
            ):
                """Alias for add_layer."""
                return self.add_layer(ee_object, vis_params, name, shown, opacity)

            def centerObject(self, ee_object, zoom=None):
                """Center the map on an Earth Engine object."""
                try:
                    import ee
                    from qgis.core import (
                        QgsRectangle,
                        QgsCoordinateReferenceSystem,
                        QgsCoordinateTransform,
                        QgsProject,
                    )

                    # Get the bounds of the EE object
                    bounds = None
                    if isinstance(
                        ee_object, (ee.Geometry, ee.Feature, ee.FeatureCollection)
                    ):
                        geometry = (
                            ee_object.geometry()
                            if hasattr(ee_object, "geometry")
                            else ee_object
                        )
                        bounds = geometry.bounds().getInfo()
                    elif isinstance(ee_object, (ee.Image, ee.ImageCollection)):
                        # For images, try to get geometry from properties
                        img = ee_object
                        if isinstance(ee_object, ee.ImageCollection):
                            img = ee_object.first()
                        geometry = img.geometry()
                        bounds = geometry.bounds().getInfo()

                    if bounds:
                        coords = bounds["coordinates"][0]
                        lons = [c[0] for c in coords]
                        lats = [c[1] for c in coords]
                        west, east = min(lons), max(lons)
                        south, north = min(lats), max(lats)

                        # Create extent in WGS84
                        wgs84_extent = QgsRectangle(west, south, east, north)

                        # Transform to map canvas CRS
                        canvas = self._iface.mapCanvas()
                        map_crs = canvas.mapSettings().destinationCrs()
                        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")

                        if map_crs.authid() != "EPSG:4326":
                            transform = QgsCoordinateTransform(
                                wgs84, map_crs, QgsProject.instance()
                            )
                            extent = transform.transformBoundingBox(wgs84_extent)
                        else:
                            extent = wgs84_extent

                        canvas.setExtent(extent)
                        canvas.refresh()
                except Exception:
                    # If centering fails, silently ignore
                    pass

            def center_object(self, ee_object, zoom=None):
                """Alias for centerObject."""
                return self.centerObject(ee_object, zoom)

            def setCenter(self, lon, lat, zoom=None):
                """Set map center to a specific lon/lat.

                Args:
                    lon: Longitude (x coordinate) in degrees, range [-180, 180]
                    lat: Latitude (y coordinate) in degrees, range [-90, 90]
                    zoom: Zoom level (currently ignored in QGIS implementation)
                """
                try:
                    from qgis.core import (
                        QgsRectangle,
                        QgsCoordinateReferenceSystem,
                        QgsCoordinateTransform,
                        QgsProject,
                    )

                    # Validate coordinates
                    if not (-180 <= lon <= 180):
                        raise ValueError(f"Longitude {lon} out of range [-180, 180]")
                    if not (-90 <= lat <= 90):
                        raise ValueError(f"Latitude {lat} out of range [-90, 90]")

                    canvas = self._iface.mapCanvas()

                    # Get current extent and CRS
                    current_extent = canvas.extent()
                    map_crs = canvas.mapSettings().destinationCrs()

                    # Calculate the width/height to maintain current scale
                    width = current_extent.width()
                    height = current_extent.height()

                    # Create new extent centered on lon/lat (in map CRS coordinates)
                    if map_crs.authid() == "EPSG:4326":
                        # Map is already in WGS84, use coordinates directly
                        new_extent = QgsRectangle(
                            lon - width / 2,
                            lat - height / 2,
                            lon + width / 2,
                            lat + height / 2,
                        )
                    else:
                        # Need to transform from WGS84 to map CRS
                        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
                        transform = QgsCoordinateTransform(
                            wgs84, map_crs, QgsProject.instance()
                        )

                        # Transform the center point
                        from qgis.core import QgsPointXY

                        center_wgs84 = QgsPointXY(lon, lat)
                        center_map = transform.transform(center_wgs84)

                        # Create extent in map CRS
                        new_extent = QgsRectangle(
                            center_map.x() - width / 2,
                            center_map.y() - height / 2,
                            center_map.x() + width / 2,
                            center_map.y() + height / 2,
                        )

                    canvas.setExtent(new_extent)
                    canvas.refresh()
                except Exception as e:
                    # If setting center fails, show error in console
                    import traceback

                    print(f"Error setting center: {e}")
                    traceback.print_exc()

            def set_center(self, lon, lat, zoom=None):
                """Alias for setCenter."""
                return self.setCenter(lon, lat, zoom)

            def add_basemap(self, basemap="ROADMAP"):
                """Add a basemap layer."""
                basemap_urls = {
                    "ROADMAP": "https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
                    "SATELLITE": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                    "TERRAIN": "https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}",
                    "HYBRID": "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
                    "OpenStreetMap": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                }
                url = basemap_urls.get(basemap, basemap_urls["ROADMAP"])
                from qgis.core import QgsRasterLayer, QgsProject

                uri = f"type=xyz&url={url}&zmax=19&zmin=0"
                layer = QgsRasterLayer(uri, basemap, "wms")
                if layer.isValid():
                    QgsProject.instance().addMapLayer(layer, True)

            def add_time_slider(
                self,
                ee_object,
                vis_params=None,
                region=None,
                layer_name="Time series",
                labels=None,
                time_interval=1,
                position="bottomright",
                slider_length="150px",
                date_format="YYYY-MM-dd",
                opacity=1.0,
                **kwargs,
            ):
                """Add a time series as individual layers.

                Note: QGIS doesn't support interactive sliders like Jupyter.
                Images are added as separate layers that can be toggled.
                """
                import ee
                from ..core.ee_utils import add_ee_layer

                if vis_params is None:
                    vis_params = {}

                # Convert to list if it's an ImageCollection
                if isinstance(ee_object, ee.ImageCollection):
                    # Get the list of images
                    img_list = ee_object.toList(ee_object.size())
                    count = ee_object.size().getInfo()

                    # Limit to reasonable number of layers
                    max_layers = min(count, 20)

                    # Get date labels if not provided
                    if labels is None:
                        try:
                            dates = ee_object.aggregate_array(
                                "system:time_start"
                            ).getInfo()
                            from datetime import datetime

                            labels = []
                            for ts in dates[:max_layers]:
                                if ts:
                                    dt = datetime.fromtimestamp(ts / 1000)
                                    labels.append(dt.strftime("%Y-%m-%d"))
                                else:
                                    labels.append(None)
                        except Exception:
                            labels = [None] * max_layers

                    # Add each image as a layer
                    for i in range(max_layers):
                        img = ee.Image(img_list.get(i))
                        label = labels[i] if i < len(labels) and labels[i] else f"{i+1}"
                        name = f"{layer_name} - {label}"
                        # Only show the last layer by default
                        shown = i == max_layers - 1
                        add_ee_layer(img, vis_params, name, shown, opacity)

                    print(
                        f"Added {max_layers} time series layers. Toggle visibility in the Layers panel."
                    )
                else:
                    # Single image, just add it
                    add_ee_layer(ee_object, vis_params, layer_name, True, opacity)

            def __repr__(self):
                return "QGISMap()"

        return QGISMap

    def _load_code_example(self, index):
        """Load a code example."""
        examples = {
            1: """# DEM with custom palette
import ee
import geemap

m = geemap.Map()
dem = ee.Image('USGS/SRTMGL1_003')
vis = {
    'min': 0,
    'max': 4000,
    'palette': ['006633', 'E5FFCC', '662A00', 'D8D8D8', 'F5F5F5']
}
m.add_layer(dem, vis, 'SRTM DEM')""",
            2: """# Landsat 9 True Color
import ee
import geemap

m = geemap.Map()
l9 = ee.ImageCollection('LANDSAT/LC09/C02/T1_L2')\\
    .filterDate('2023-01-01', '2023-12-31')\\
    .filter(ee.Filter.lt('CLOUD_COVER', 20))\\
    .median()

vis = {'bands': ['SR_B4', 'SR_B3', 'SR_B2'], 'min': 7000, 'max': 12000}
m.add_layer(l9, vis, 'Landsat 9 RGB')""",
            3: """# Sentinel-2 with filters
import ee
import geemap

m = geemap.Map()
s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')\\
    .filterDate('2023-06-01', '2023-09-01')\\
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))\\
    .median()

vis = {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 3000}
m.add_layer(s2, vis, 'Sentinel-2 Summer 2023')""",
            4: """# NDVI Calculation
import ee
import geemap

m = geemap.Map()
s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')\\
    .filterDate('2023-06-01', '2023-09-01')\\
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))\\
    .median()

ndvi = s2.normalizedDifference(['B8', 'B4']).rename('NDVI')
vis = {'min': -0.2, 'max': 0.8, 'palette': ['red', 'yellow', 'green']}
m.add_layer(ndvi, vis, 'NDVI')""",
            5: """# Styled FeatureCollection
import ee
import geemap

m = geemap.Map()
countries = ee.FeatureCollection('FAO/GAUL/2015/level0')

# Style as image
styled = countries.style(
    color='blue',
    fillColor='00000000',
    width=2
)
m.add_layer(styled, {}, 'Country Boundaries')""",
            6: """# Dynamic World Land Cover
import ee
import geemap

m = geemap.Map()
dw = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1')\\
    .filterDate('2023-01-01', '2023-12-31')\\
    .select('label')\\
    .mode()

vis = {
    'min': 0,
    'max': 8,
    'palette': ['#419BDF', '#397D49', '#88B053', '#7A87C6',
                '#E49635', '#DFC35A', '#C4281B', '#A59B8F', '#B39FE1']
}
m.add_layer(dw, vis, 'Dynamic World 2023')""",
        }

        if index in examples:
            self.code_input.setPlainText(examples[index])

    def _show_progress(self, message):
        """Show progress indicator."""
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: blue; font-size: 10px;")

    def _show_success(self, message):
        """Show success message."""
        self.progress_bar.setVisible(False)
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: green; font-size: 10px;")
        # self.iface.messageBar().pushSuccess("GEE Data Catalogs", message)

    def _show_error(self, message):
        """Show error message."""
        self.progress_bar.setVisible(False)
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: red; font-size: 10px;")
        QMessageBox.critical(self, "Error", message)

    def _refresh_inspector_layers(self):
        """Refresh the count of registered Earth Engine layers."""
        from ..core.ee_utils import get_ee_layers

        ee_layers = get_ee_layers()
        count = len(ee_layers)
        self.inspector_layer_count_label.setText(f"Registered layers: {count}")

        if count > 0:
            self.inspector_layer_count_label.setStyleSheet(
                "color: green; font-size: 10px; font-weight: bold;"
            )
            layer_names = list(ee_layers.keys())
            tooltip = "Registered layers:\n" + "\n".join(
                f"  • {name}" for name in layer_names
            )
            self.inspector_layer_count_label.setToolTip(tooltip)
        else:
            self.inspector_layer_count_label.setStyleSheet(
                "color: gray; font-size: 10px;"
            )
            self.inspector_layer_count_label.setToolTip(
                "No Earth Engine layers registered yet. Add layers using Browse/Search/Load/Code tabs."
            )

    def _toggle_inspector(self):
        """Toggle the Inspector map tool on/off."""
        # Update layer count when starting inspector
        self._refresh_inspector_layers()

        if self.inspector_toggle_btn.isChecked():
            # Start inspector
            if not self._inspector_map_tool:
                self._inspector_map_tool = InspectorMapTool(
                    self.iface, self._inspect_point
                )

            self._inspector_map_tool.activate()
            self._inspector_active = True
            self.inspector_toggle_btn.setText("■ Stop Inspector")
            self.inspector_status_label.setText(
                "Inspector active. Click on the map to inspect layers."
            )
            self.inspector_status_label.setStyleSheet("color: blue; font-size: 10px;")
        else:
            # Stop inspector
            if self._inspector_map_tool:
                self._inspector_map_tool.deactivate()

            self._inspector_active = False
            self.inspector_toggle_btn.setText("▶ Start Inspector")
            self.inspector_status_label.setText("Inspector stopped.")
            self.inspector_status_label.setStyleSheet("color: gray; font-size: 10px;")

    def _clear_inspector(self):
        """Clear inspector results."""
        self.inspector_tree.clear()
        self.inspector_lon_label.setText("--")
        self.inspector_lat_label.setText("--")
        self.inspector_progress_bar.setVisible(False)
        self.inspector_status_label.setText("Results cleared.")
        self.inspector_status_label.setStyleSheet("color: gray; font-size: 10px;")

    def _inspect_point(self, lon, lat):
        """Inspect Earth Engine layers at the clicked point."""
        # Update location labels
        self.inspector_lon_label.setText(f"{lon:.6f}")
        self.inspector_lat_label.setText(f"{lat:.6f}")

        # Clear previous results
        self.inspector_tree.clear()

        # Get EE layers
        from ..core.ee_utils import get_ee_layers

        ee_layers = get_ee_layers()

        if not ee_layers:
            self.inspector_status_label.setText("No Earth Engine layers to inspect.")
            self.inspector_status_label.setStyleSheet("color: orange; font-size: 10px;")
            return

        # Calculate scale based on map zoom
        canvas = self.iface.mapCanvas()
        scale = canvas.scale()
        # Convert map scale to Earth Engine scale (meters)
        ee_scale = max(10, min(1000, scale / 3000))

        # Show progress bar and update status
        self.inspector_progress_bar.setVisible(True)
        self.inspector_progress_bar.setRange(0, 0)  # Indeterminate mode
        self.inspector_status_label.setText(f"Inspecting {len(ee_layers)} layer(s)...")
        self.inspector_status_label.setStyleSheet("color: blue; font-size: 10px;")

        # Start inspector worker
        self._inspector_thread = InspectorWorker(ee_layers, (lon, lat), int(ee_scale))
        self._inspector_thread.finished.connect(self._on_inspection_finished)
        self._inspector_thread.error.connect(self._on_inspection_error)
        self._inspector_thread.progress.connect(
            lambda msg: self.inspector_status_label.setText(msg)
        )
        self._inspector_thread.start()

    def _on_inspection_finished(self, results):
        """Handle inspection results."""
        import json

        # Hide progress bar
        self.inspector_progress_bar.setVisible(False)

        if not results:
            self.inspector_status_label.setText("No data found at this location.")
            self.inspector_status_label.setStyleSheet("color: orange; font-size: 10px;")
            return

        # Display results in tree
        for layer_name, data in results.items():
            layer_item = QTreeWidgetItem([layer_name, ""])
            layer_item.setFont(0, QFont("", -1, QFont.Bold))

            if data.get("type") == "Error":
                error_item = QTreeWidgetItem(
                    ["Error", data.get("error", "Unknown error")]
                )
                error_item.setForeground(1, Qt.red)
                layer_item.addChild(error_item)

            elif data.get("type") in ["Image", "ImageCollection"]:
                type_item = QTreeWidgetItem(["Type", data.get("type")])
                layer_item.addChild(type_item)

                properties = data.get("properties", {})
                if properties:
                    for key, value in sorted(properties.items()):
                        # Format value
                        if isinstance(value, float):
                            value_str = f"{value:.6f}"
                        elif isinstance(value, (dict, list)):
                            value_str = json.dumps(value, indent=2)
                        else:
                            value_str = str(value)

                        prop_item = QTreeWidgetItem([key, value_str])
                        layer_item.addChild(prop_item)

            elif data.get("type") == "FeatureCollection":
                type_item = QTreeWidgetItem(["Type", "FeatureCollection"])
                layer_item.addChild(type_item)

                count_item = QTreeWidgetItem(
                    ["Feature Count", str(data.get("count", 0))]
                )
                layer_item.addChild(count_item)

                features = data.get("features", [])
                for i, feature in enumerate(features[:10]):  # Show up to 10 features
                    feature_item = QTreeWidgetItem([f"Feature {i+1}", ""])
                    properties = feature.get("properties", {})

                    for key, value in sorted(properties.items()):
                        if isinstance(value, float):
                            value_str = f"{value:.6f}"
                        elif isinstance(value, (dict, list)):
                            value_str = json.dumps(value, indent=2)
                        else:
                            value_str = str(value)

                        prop_item = QTreeWidgetItem([key, value_str])
                        feature_item.addChild(prop_item)

                    layer_item.addChild(feature_item)

            self.inspector_tree.addTopLevelItem(layer_item)
            # Expand this layer item to show all properties
            layer_item.setExpanded(True)
            # Also expand all child items (for FeatureCollections)
            for i in range(layer_item.childCount()):
                layer_item.child(i).setExpanded(True)

        self.inspector_status_label.setText(f"Inspected {len(results)} layer(s)")
        self.inspector_status_label.setStyleSheet("color: green; font-size: 10px;")

    def _on_inspection_error(self, error):
        """Handle inspection error."""
        # Hide progress bar
        self.inspector_progress_bar.setVisible(False)

        self.inspector_status_label.setText(f"Error: {error}")
        self.inspector_status_label.setStyleSheet("color: red; font-size: 10px;")

    # ==================== Time Series Methods ====================

    def _create_timeseries(self):
        """Create a time series from the specified ImageCollection."""
        if ee is None:
            QMessageBox.warning(
                self,
                "Warning",
                "Earth Engine API not available. Please install earthengine-api.",
            )
            return

        asset_id = self.ts_dataset_id_input.text().strip()
        if not asset_id:
            QMessageBox.warning(self, "Warning", "Please enter an asset ID.")
            return

        # Stop any existing playback
        self._stop_timeseries_playback()

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        self.ts_create_btn.setEnabled(False)

        try:
            start_date = self.ts_start_date.date().toString("yyyy-MM-dd")
            end_date = self.ts_end_date.date().toString("yyyy-MM-dd")
            frequency = self.ts_frequency_combo.currentText()
            reducer = self.ts_reducer_combo.currentText()

            # Get bands if specified
            bands = None
            bands_text = self.ts_bands_input.text().strip()
            if bands_text:
                bands = [
                    b.strip().strip("\"'") for b in bands_text.split(",") if b.strip()
                ]

            # Get spatial filter
            region = self._get_spatial_filter_ts()

            # Get cloud cover settings
            cloud_cover = None
            custom_cloud_property = self.ts_cloud_property_input.text().strip()
            cloud_property = self._get_cloud_property(asset_id, custom_cloud_property)
            if self.ts_use_cloud_filter.isChecked():
                cloud_cover = self.ts_cloud_cover_spin.value()

            # Get property filters
            property_filters = self._parse_property_filters(
                self.ts_property_filters.toPlainText()
            )

            self._show_progress(f"Creating time series for {asset_id}...")

            # Start background thread
            self._timeseries_thread = TimeSeriesLoaderThread(
                asset_id=asset_id,
                start_date=start_date,
                end_date=end_date,
                frequency=frequency,
                reducer=reducer,
                bands=bands,
                region=region,
                cloud_cover=cloud_cover,
                cloud_property=cloud_property,
                property_filters=property_filters,
            )
            self._timeseries_thread.finished.connect(self._on_timeseries_created)
            self._timeseries_thread.error.connect(self._on_timeseries_error)
            self._timeseries_thread.progress.connect(
                lambda msg: self.ts_info_label.setText(msg)
            )
            self._timeseries_thread.start()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.ts_create_btn.setEnabled(True)
            self._show_error(f"Failed to create time series: {str(e)}")

    def _on_timeseries_created(self, images_data, labels):
        """Handle time series created successfully."""
        QApplication.restoreOverrideCursor()
        self.ts_create_btn.setEnabled(True)

        if not images_data:
            self._show_error("No images found in the time series")
            return

        # Store time series data
        self._timeseries_images = images_data
        self._timeseries_labels = labels

        # Build the ImageCollection for visualization
        asset_id = self.ts_dataset_id_input.text().strip()
        start_date = self.ts_start_date.date().toString("yyyy-MM-dd")
        end_date = self.ts_end_date.date().toString("yyyy-MM-dd")
        frequency = self.ts_frequency_combo.currentText()
        reducer = self.ts_reducer_combo.currentText()

        # Get bands if specified
        bands = None
        bands_text = self.ts_bands_input.text().strip()
        if bands_text:
            bands = [b.strip().strip("\"'") for b in bands_text.split(",") if b.strip()]

        # Get spatial filter
        region = self._get_spatial_filter_ts()

        # Get cloud cover settings
        cloud_cover = None
        custom_cloud_property = self.ts_cloud_property_input.text().strip()
        cloud_property = self._get_cloud_property(asset_id, custom_cloud_property)
        if self.ts_use_cloud_filter.isChecked():
            cloud_cover = self.ts_cloud_cover_spin.value()

        # Get property filters
        property_filters = self._parse_property_filters(
            self.ts_property_filters.toPlainText()
        )

        try:
            # Create the time series collection using geemap's approach
            self._timeseries_collection = self._build_timeseries_collection(
                asset_id=asset_id,
                start_date=start_date,
                end_date=end_date,
                frequency=frequency,
                reducer=reducer,
                bands=bands,
                region=region,
                cloud_cover=cloud_cover,
                cloud_property=cloud_property,
                property_filters=property_filters,
            )

            # Build visualization parameters
            self._timeseries_vis_params = self._build_ts_vis_params()

            # Update slider
            self.ts_time_slider.setMaximum(len(labels) - 1)
            self.ts_time_slider.setValue(0)
            self.ts_time_slider.setEnabled(True)
            self.ts_prev_btn.setEnabled(True)
            self.ts_play_btn.setEnabled(True)
            self.ts_next_btn.setEnabled(True)

            # Update label
            self.ts_current_label.setText(labels[0] if labels else "No data")

            # Update info
            self.ts_info_label.setText(
                f"Time series created with {len(labels)} time steps. "
                f"Use the slider or Play button to animate."
            )

            # Display first image
            self._display_timeseries_image(0)

            self._show_success(f"Time series created with {len(labels)} images")

        except Exception as e:
            import traceback

            self._show_error(
                f"Failed to build time series: {str(e)}\n{traceback.format_exc()}"
            )

    def _on_timeseries_error(self, error):
        """Handle time series creation error."""
        QApplication.restoreOverrideCursor()
        self.ts_create_btn.setEnabled(True)
        self._show_error(f"Time series error: {error}")

    def _build_timeseries_collection(
        self,
        asset_id: str,
        start_date: str,
        end_date: str,
        frequency: str = "month",
        reducer: str = "median",
        bands: list = None,
        region: list = None,
        cloud_cover: int = None,
        cloud_property: str = "CLOUDY_PIXEL_PERCENTAGE",
        property_filters: list = None,
    ):
        """Build a time series ImageCollection.

        This is similar to geemap's create_timeseries function but returns
        a list of images for QGIS visualization.
        """
        from datetime import datetime
        from dateutil.relativedelta import relativedelta

        collection = ee.ImageCollection(asset_id)

        # Apply filters
        collection = collection.filterDate(start_date, end_date)

        region_geom = None
        if region:
            region_geom = ee.Geometry.Rectangle(region)
            collection = collection.filterBounds(region_geom)

        if cloud_cover is not None:
            collection = collection.filter(ee.Filter.lt(cloud_property, cloud_cover))

        # Apply property filters
        if property_filters:
            collection = self._apply_property_filters(collection, property_filters)

        if bands:
            collection = collection.select(bands)

        # Get frequency settings
        freq_dict = {
            "day": ("day", 1),
            "week": ("day", 7),
            "month": ("month", 1),
            "quarter": ("month", 3),
            "year": ("year", 1),
        }

        unit, step = freq_dict.get(frequency, ("month", 1))

        # Generate date sequence
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        dates = []
        current = start_dt
        while current < end_dt:
            dates.append(current.strftime("%Y-%m-%d"))
            if unit == "day":
                current += relativedelta(days=step)
            elif unit == "month":
                current += relativedelta(months=step)
            elif unit == "year":
                current += relativedelta(years=step)

        # Get reducer function
        reducer_func = getattr(ee.Reducer, reducer)()

        # Create image for each time step
        images = []
        for date_str in dates:
            start = ee.Date(date_str)
            if unit == "day":
                end = start.advance(step, "day")
            elif unit == "month":
                end = start.advance(step, "month")
            elif unit == "year":
                end = start.advance(step, "year")

            sub_col = collection.filterDate(start, end)
            if region_geom:
                sub_col = sub_col.filterBounds(region_geom)

            image = sub_col.reduce(reducer_func)

            # Set date property
            image = image.set(
                {
                    "system:time_start": start.millis(),
                    "system:date": start.format("YYYY-MM-dd"),
                }
            )

            # Clip to region if specified
            if region_geom:
                image = image.clip(region_geom)

            images.append(image)

        return images

    def _build_ts_vis_params(self):
        """Build visualization parameters for time series."""
        vis_params = {}

        bands = self.ts_bands_input.text().strip()
        if bands:
            vis_params["bands"] = [
                b.strip().strip("\"'")
                for b in bands.split(",")
                if b.strip().strip("\"'")
            ]

        vis_min_text = self.ts_vis_min_input.text().strip()
        vis_max_text = self.ts_vis_max_input.text().strip()

        if vis_min_text:
            try:
                vis_params["min"] = float(vis_min_text)
            except ValueError:
                # Invalid numeric input: leave 'min' unset so default visualization is used.
                pass

        if vis_max_text:
            try:
                vis_params["max"] = float(vis_max_text)
            except ValueError:
                # Invalid numeric input: leave 'max' unset so default visualization is used.
                # Ignore invalid numeric input; leave "max" unset so default behavior applies.
                pass

        palette = self.ts_palette_input.text().strip()
        if palette:
            palette_colors = self._get_colormap_colors(palette)
            if palette_colors:
                vis_params["palette"] = palette_colors
            else:
                vis_params["palette"] = [
                    p.strip().strip("\"'")
                    for p in palette.split(",")
                    if p.strip().strip("\"'")
                ]

        # If bands contain reducer suffixes, update them
        if "bands" in vis_params:
            reducer = self.ts_reducer_combo.currentText()
            # The reducer adds a suffix like '_median' to band names
            vis_params["bands"] = [f"{b}_{reducer}" for b in vis_params["bands"]]

        return vis_params

    def _display_timeseries_image(self, index):
        """Display the time series image at the given index."""
        if not self._timeseries_collection or index >= len(self._timeseries_collection):
            return

        try:
            from ..core.ee_utils import add_ee_layer

            image = self._timeseries_collection[index]
            layer_name = self.ts_layer_name_input.text().strip() or "Time Series"

            # Add the layer (will replace existing layer with same name)
            add_ee_layer(image, self._timeseries_vis_params, layer_name)

            # Update label
            if index < len(self._timeseries_labels):
                self.ts_current_label.setText(
                    f"{self._timeseries_labels[index]} ({index + 1}/{len(self._timeseries_labels)})"
                )

        except Exception as e:
            self.ts_info_label.setText(f"Error displaying image: {str(e)}")

    def _on_timeslider_changed(self, value):
        """Handle time slider value changed."""
        if not self._timeseries_collection:
            return

        self._timeseries_current_index = value
        self._display_timeseries_image(value)

    def _timeseries_prev(self):
        """Go to previous time step."""
        if not self._timeseries_collection:
            return

        current = self.ts_time_slider.value()
        if current > 0:
            self.ts_time_slider.setValue(current - 1)
        elif self.ts_loop_check.isChecked():
            self.ts_time_slider.setValue(self.ts_time_slider.maximum())

    def _timeseries_next(self):
        """Go to next time step."""
        if not self._timeseries_collection:
            return

        current = self.ts_time_slider.value()
        max_index = self.ts_time_slider.maximum()
        if current < max_index:
            self.ts_time_slider.setValue(current + 1)
        elif self.ts_loop_check.isChecked():
            self.ts_time_slider.setValue(0)

    def _timeseries_toggle_play(self):
        """Toggle time series playback."""
        if self._timeseries_playing:
            self._stop_timeseries_playback()
        else:
            self._start_timeseries_playback()

    def _start_timeseries_playback(self):
        """Start time series animation."""
        if not self._timeseries_collection:
            return

        self._timeseries_playing = True
        self.ts_play_btn.setText("⏸ Pause")

        # Create timer if it doesn't exist
        if not self._timeseries_timer:
            self._timeseries_timer = QTimer()
            self._timeseries_timer.timeout.connect(self._timeseries_timer_tick)

        # Set interval from speed control
        self._timeseries_timer.setInterval(self.ts_speed_spin.value())
        self._timeseries_timer.start()

    def _stop_timeseries_playback(self):
        """Stop time series animation."""
        self._timeseries_playing = False
        self.ts_play_btn.setText("▶ Play")

        if self._timeseries_timer:
            self._timeseries_timer.stop()

    def _timeseries_timer_tick(self):
        """Handle timer tick for animation."""
        if not self._timeseries_playing or not self._timeseries_collection:
            self._stop_timeseries_playback()
            return

        current = self.ts_time_slider.value()
        max_index = self.ts_time_slider.maximum()
        if current < max_index:
            self.ts_time_slider.setValue(current + 1)
        elif self.ts_loop_check.isChecked():
            self.ts_time_slider.setValue(0)
        else:
            self._stop_timeseries_playback()

    def _update_timeseries_timer_interval(self, value):
        """Update the timer interval when speed changes."""
        if self._timeseries_timer:
            self._timeseries_timer.setInterval(value)

    def _preview_timeseries(self):
        """Preview time series information."""
        if ee is None:
            QMessageBox.warning(self, "Warning", "Earth Engine API not available.")
            return

        asset_id = self.ts_dataset_id_input.text().strip()
        if not asset_id:
            QMessageBox.warning(self, "Warning", "Please enter an asset ID.")
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        try:
            start_date = self.ts_start_date.date().toString("yyyy-MM-dd")
            end_date = self.ts_end_date.date().toString("yyyy-MM-dd")

            collection = ee.ImageCollection(asset_id)
            collection = collection.filterDate(start_date, end_date)

            # Apply cloud filter if enabled
            if self.ts_use_cloud_filter.isChecked():
                cloud_cover = self.ts_cloud_cover_spin.value()
                cloud_property = self._get_cloud_property(
                    asset_id, self.ts_cloud_property_input.text().strip()
                )
                collection = collection.filter(
                    ee.Filter.lt(cloud_property, cloud_cover)
                )

            # Apply region filter if enabled
            region = self._get_spatial_filter_ts()
            if region:
                geometry = ee.Geometry.Rectangle(region)
                collection = collection.filterBounds(geometry)

            size = collection.size().getInfo()

            info_text = f"Asset: {asset_id}\n"
            info_text += f"Date Range: {start_date} to {end_date}\n"
            info_text += f"Matching Images: {size}\n\n"

            if size > 0:
                first = collection.first()
                bands = first.bandNames().getInfo()
                info_text += f"Bands: {len(bands)}\n"
                for band in bands[:10]:
                    info_text += f"  - {band}\n"
                if len(bands) > 10:
                    info_text += f"  ... and {len(bands) - 10} more\n"

            # Estimate time steps
            frequency = self.ts_frequency_combo.currentText()
            from datetime import datetime
            from dateutil.relativedelta import relativedelta

            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")

            freq_dict = {
                "day": relativedelta(days=1),
                "week": relativedelta(weeks=1),
                "month": relativedelta(months=1),
                "quarter": relativedelta(months=3),
                "year": relativedelta(years=1),
            }

            delta = freq_dict.get(frequency, relativedelta(months=1))
            steps = 0
            current = start_dt
            while current < end_dt:
                steps += 1
                current += delta

            info_text += f"\nEstimated Time Steps ({frequency}): {steps}"

            QMessageBox.information(self, "Time Series Info", info_text)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to get info: {str(e)}")
        finally:
            QApplication.restoreOverrideCursor()

    def _copy_timeseries_code(self):
        """Copy Python code for creating the time series."""
        asset_id = self.ts_dataset_id_input.text().strip()
        if not asset_id:
            QMessageBox.warning(self, "Warning", "Please enter an asset ID.")
            return

        start_date = self.ts_start_date.date().toString("yyyy-MM-dd")
        end_date = self.ts_end_date.date().toString("yyyy-MM-dd")
        frequency = self.ts_frequency_combo.currentText()
        reducer = self.ts_reducer_combo.currentText()
        layer_name = self.ts_layer_name_input.text().strip() or "Time Series"

        code_lines = [
            "import ee",
            "import geemap",
            "",
            "m = geemap.Map()",
            "",
            f"# Create time series from {asset_id}",
            f"collection = ee.ImageCollection('{asset_id}')",
            f"",
            f"# Date range",
            f"start_date = '{start_date}'",
            f"end_date = '{end_date}'",
            f"",
        ]

        # Add cloud filter
        if self.ts_use_cloud_filter.isChecked():
            cloud_cover = self.ts_cloud_cover_spin.value()
            custom_cloud_prop = self.ts_cloud_property_input.text().strip()
            cloud_property = self._get_cloud_property(asset_id, custom_cloud_prop)
            code_lines.append(f"# Cloud filter")
            code_lines.append(
                f"collection = collection.filter(ee.Filter.lt('{cloud_property}', {cloud_cover}))"
            )
            code_lines.append("")

        # Add spatial filter
        bbox = self._get_spatial_filter_ts()
        if bbox:
            west, south, east, north = bbox
            code_lines.append(f"# Spatial filter")
            code_lines.append(
                f"region = ee.Geometry.Rectangle([{west}, {south}, {east}, {north}])"
            )
            code_lines.append("")

        # Add property filters
        property_filters = self._parse_property_filters(
            self.ts_property_filters.toPlainText()
        )
        if property_filters:
            code_lines.append("# Property filters")
            for prop_name, op, value in property_filters:
                if op == "==":
                    code_lines.append(
                        f"collection = collection.filter(ee.Filter.eq('{prop_name}', {repr(value)}))"
                    )
                elif op == "!=":
                    code_lines.append(
                        f"collection = collection.filter(ee.Filter.neq('{prop_name}', {repr(value)}))"
                    )
                elif op == ">":
                    code_lines.append(
                        f"collection = collection.filter(ee.Filter.gt('{prop_name}', {value}))"
                    )
                elif op == ">=":
                    code_lines.append(
                        f"collection = collection.filter(ee.Filter.gte('{prop_name}', {value}))"
                    )
                elif op == "<":
                    code_lines.append(
                        f"collection = collection.filter(ee.Filter.lt('{prop_name}', {value}))"
                    )
                elif op == "<=":
                    code_lines.append(
                        f"collection = collection.filter(ee.Filter.lte('{prop_name}', {value}))"
                    )
            code_lines.append("")

        # Build visualization params
        vis_parts = []
        bands = self.ts_bands_input.text().strip()
        if bands:
            band_list = [b.strip().strip("\"'") for b in bands.split(",") if b.strip()]
            vis_parts.append(f"'bands': {band_list}")

        vis_min = self.ts_vis_min_input.text().strip()
        vis_max = self.ts_vis_max_input.text().strip()
        if vis_min and vis_max:
            try:
                vis_parts.append(f"'min': {float(vis_min)}")
                vis_parts.append(f"'max': {float(vis_max)}")
            except ValueError:
                # If min/max are not valid numbers, omit them from vis_params.
                pass

        palette = self.ts_palette_input.text().strip()
        if palette:
            if "," in palette:
                palette_list = [p.strip().strip("\"'") for p in palette.split(",")]
                vis_parts.append(f"'palette': {palette_list}")
            else:
                vis_parts.append(f"'palette': '{palette}'")

        code_lines.append("# Create time series using geemap")
        code_lines.append(f"timeseries = geemap.create_timeseries(")
        code_lines.append(f"    collection,")
        code_lines.append(f"    start_date=start_date,")
        code_lines.append(f"    end_date=end_date,")
        code_lines.append(f"    frequency='{frequency}',")
        code_lines.append(f"    reducer='{reducer}',")
        if bbox:
            code_lines.append(f"    region=region,")
        code_lines.append(f")")
        code_lines.append("")

        # Visualization params
        code_lines.append("# Visualization parameters")
        if vis_parts:
            code_lines.append("vis_params = {" + ", ".join(vis_parts) + "}")
        else:
            code_lines.append("vis_params = {}")
        code_lines.append("")

        # Add time slider
        code_lines.append("# Add time slider to map")
        code_lines.append(
            f"m.add_time_slider(timeseries, vis_params, layer_name='{layer_name}')"
        )
        code_lines.append("")
        code_lines.append("m")

        code = "\n".join(code_lines)

        # Copy to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(code)

        self._show_success("Time series code copied to clipboard!")

        # Paste code to Code tab and switch to it
        self.code_input.setPlainText(code)
        self.tab_widget.setCurrentIndex(4)  # Code tab

    def closeEvent(self, event):
        """Handle dock widget close event."""
        # Deactivate inspector if active
        if self._inspector_map_tool:
            self._inspector_map_tool.deactivate()

        # Stop time series playback and timer
        self._stop_timeseries_playback()
        if self._timeseries_timer:
            self._timeseries_timer.stop()
            self._timeseries_timer = None

        # Stop any running threads
        if self._catalog_thread and self._catalog_thread.isRunning():
            self._catalog_thread.terminate()
            self._catalog_thread.wait()
        if self._image_list_thread and self._image_list_thread.isRunning():
            self._image_list_thread.terminate()
            self._image_list_thread.wait()
        if self._preview_thread and self._preview_thread.isRunning():
            self._preview_thread.terminate()
            self._preview_thread.wait()
        if self._thumbnail_thread and self._thumbnail_thread.isRunning():
            self._thumbnail_thread.terminate()
            self._thumbnail_thread.wait()
        if self._inspector_thread and self._inspector_thread.isRunning():
            self._inspector_thread.terminate()
            self._inspector_thread.wait()
        if self._timeseries_thread and self._timeseries_thread.isRunning():
            self._timeseries_thread.terminate()
            self._timeseries_thread.wait()
        event.accept()
