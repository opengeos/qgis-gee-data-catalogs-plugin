"""
Catalog Dock Widget for GEE Data Catalogs

This module provides the main catalog browser panel for discovering
and loading Google Earth Engine datasets.
"""

from datetime import datetime, timedelta

from qgis.PyQt.QtCore import Qt, QCoreApplication, QThread, pyqtSignal
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

    def _get_cloud_property(self, asset_id: str) -> str:
        """Determine the correct cloud cover property based on the asset ID.

        Args:
            asset_id: The Earth Engine asset ID.

        Returns:
            The cloud cover property name for the dataset.
        """
        asset_upper = asset_id.upper()

        # Landsat collections use CLOUD_COVER
        if "LANDSAT" in asset_upper:
            return "CLOUD_COVER"

        # MODIS uses different properties but typically doesn't have per-scene cloud
        if "MODIS" in asset_upper:
            return "CLOUD_COVER"

        # Sentinel-2 uses CLOUDY_PIXEL_PERCENTAGE
        if "SENTINEL" in asset_upper or "COPERNICUS/S2" in asset_upper:
            return "CLOUDY_PIXEL_PERCENTAGE"

        # Default to CLOUDY_PIXEL_PERCENTAGE (most common for optical imagery)
        return "CLOUDY_PIXEL_PERCENTAGE"

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
        splitter.addWidget(search_info_group)

        splitter.setSizes([250, 250])

        return widget

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

        # Cloud cover
        self.cloud_cover_spin = QSpinBox()
        self.cloud_cover_spin.setRange(0, 100)
        self.cloud_cover_spin.setValue(20)
        self.cloud_cover_spin.setSuffix("%")
        filters_layout.addRow("Max Cloud Cover:", self.cloud_cover_spin)

        self.use_cloud_filter = QCheckBox("Apply cloud filter")
        self.use_cloud_filter.setChecked(False)
        filters_layout.addRow("", self.use_cloud_filter)

        # Bounding box
        self.use_bbox_filter = QCheckBox("Filter by current map extent")
        self.use_bbox_filter.setChecked(False)
        filters_layout.addRow("Spatial Filter:", self.use_bbox_filter)

        layout.addWidget(filters_group)

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

                for attr in ["ee_initialize", "basemaps", "coreutils", "__version__"]:
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

    def _on_tab_changed(self, index):
        """Handle tab changes."""
        # Refresh layer count when switching to Inspector tab (index 4)
        if index == 4:  # Inspector tab
            self._refresh_inspector_layers()

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
        else:
            self._selected_dataset = None
            self.info_text.clear()
            self.add_map_btn.setEnabled(False)
            self.configure_btn.setEnabled(False)

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

            # Switch to Load tab
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
                # Switch to Load tab
                self.tab_widget.setCurrentIndex(2)

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

            # Apply filters
            if self.use_date_filter.isChecked():
                start = self.start_date.date().toString("yyyy-MM-dd")
                end = self.end_date.date().toString("yyyy-MM-dd")
                collection = collection.filterDate(start, end)

            if self.use_bbox_filter.isChecked():
                bbox = self._get_map_extent_wgs84()
                if bbox:
                    geometry = ee.Geometry.Rectangle(bbox)
                    collection = collection.filterBounds(geometry)

            if self.use_cloud_filter.isChecked():
                cloud_cover = self.cloud_cover_spin.value()
                cloud_prop = self._get_cloud_property(asset_id)
                collection = collection.filter(ee.Filter.lt(cloud_prop, cloud_cover))

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
        if self.use_cloud_filter.isChecked():
            cloud_cover = self.cloud_cover_spin.value()

        bbox = None
        if self.use_bbox_filter.isChecked():
            bbox = self._get_map_extent_wgs84()

        collection = filter_image_collection(
            collection,
            start_date=start_date,
            end_date=end_date,
            bbox=bbox,
            cloud_cover=cloud_cover,
        )

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

            if self.use_bbox_filter.isChecked():
                # Get the current map extent in WGS84
                bbox = self._get_map_extent_wgs84()
                if bbox:
                    west, south, east, north = bbox
                    code_lines.append(f"# Filter by current map extent (EPSG:4326)")
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
        self.tab_widget.setCurrentIndex(3)  # Switch to Code tab

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

                for attr in ["ee_initialize", "basemaps", "coreutils", "__version__"]:
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

                    # Get the bounds of the EE object
                    if isinstance(
                        ee_object, (ee.Geometry, ee.Feature, ee.FeatureCollection)
                    ):
                        geometry = (
                            ee_object.geometry()
                            if hasattr(ee_object, "geometry")
                            else ee_object
                        )
                        bounds = geometry.bounds().getInfo()
                        coords = bounds["coordinates"][0]

                        # Extract min/max coordinates
                        lons = [c[0] for c in coords]
                        lats = [c[1] for c in coords]
                        west, east = min(lons), max(lons)
                        south, north = min(lats), max(lats)

                        # Set extent on QGIS map
                        from qgis.core import QgsRectangle

                        extent = QgsRectangle(west, south, east, north)
                        self._iface.mapCanvas().setExtent(extent)
                        self._iface.mapCanvas().refresh()
                    elif isinstance(ee_object, (ee.Image, ee.ImageCollection)):
                        # For images, try to get geometry from properties
                        img = ee_object
                        if isinstance(ee_object, ee.ImageCollection):
                            img = ee_object.first()

                        # Get the geometry/footprint
                        geometry = img.geometry()
                        bounds = geometry.bounds().getInfo()
                        coords = bounds["coordinates"][0]

                        lons = [c[0] for c in coords]
                        lats = [c[1] for c in coords]
                        west, east = min(lons), max(lons)
                        south, north = min(lats), max(lats)

                        from qgis.core import QgsRectangle

                        extent = QgsRectangle(west, south, east, north)
                        self._iface.mapCanvas().setExtent(extent)
                        self._iface.mapCanvas().refresh()
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

    def closeEvent(self, event):
        """Handle dock widget close event."""
        # Deactivate inspector if active
        if self._inspector_map_tool:
            self._inspector_map_tool.deactivate()

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
        event.accept()
