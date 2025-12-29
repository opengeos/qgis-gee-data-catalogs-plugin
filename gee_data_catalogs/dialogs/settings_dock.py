"""
Settings Dock Widget for GEE Data Catalogs

This module provides a settings panel for configuring plugin options.
"""

from qgis.PyQt.QtCore import Qt, QSettings
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QGroupBox,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QFormLayout,
    QMessageBox,
    QTabWidget,
)
from qgis.PyQt.QtGui import QFont


class SettingsDockWidget(QDockWidget):
    """A settings panel for configuring plugin options."""

    # Settings keys
    SETTINGS_PREFIX = "GeeDataCatalogs/"

    def __init__(self, iface, parent=None):
        """Initialize the settings dock widget.

        Args:
            iface: QGIS interface instance.
            parent: Parent widget.
        """
        super().__init__("GEE Data Catalogs Settings", parent)
        self.iface = iface
        self.settings = QSettings()

        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        """Set up the settings UI."""
        # Main widget
        main_widget = QWidget()
        self.setWidget(main_widget)

        # Main layout
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(10)

        # Header
        header_label = QLabel("Plugin Settings")
        header_font = QFont()
        header_font.setPointSize(12)
        header_font.setBold(True)
        header_label.setFont(header_font)
        header_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(header_label)

        # Tab widget for organized settings
        tab_widget = QTabWidget()
        layout.addWidget(tab_widget)

        # General settings tab
        general_tab = self._create_general_tab()
        tab_widget.addTab(general_tab, "General")

        # Earth Engine tab
        ee_tab = self._create_ee_tab()
        tab_widget.addTab(ee_tab, "Earth Engine")

        # Display tab
        display_tab = self._create_display_tab()
        tab_widget.addTab(display_tab, "Display")

        # Buttons
        button_layout = QHBoxLayout()

        self.save_btn = QPushButton("Save Settings")
        self.save_btn.clicked.connect(self._save_settings)
        button_layout.addWidget(self.save_btn)

        self.reset_btn = QPushButton("Reset Defaults")
        self.reset_btn.clicked.connect(self._reset_defaults)
        button_layout.addWidget(self.reset_btn)

        layout.addLayout(button_layout)

        # Stretch at the end
        layout.addStretch()

        # Status label
        self.status_label = QLabel("Settings loaded")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.status_label)

    def _create_general_tab(self):
        """Create the general settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # General options group
        general_group = QGroupBox("General Options")
        general_layout = QFormLayout(general_group)

        # Auto-initialize EE
        self.auto_init_check = QCheckBox()
        self.auto_init_check.setChecked(True)
        general_layout.addRow("Auto-initialize Earth Engine:", self.auto_init_check)

        # Show notifications
        self.notifications_check = QCheckBox()
        self.notifications_check.setChecked(True)
        general_layout.addRow("Show notifications:", self.notifications_check)

        # Default category
        self.default_category = QComboBox()
        self.default_category.addItems(
            [
                "Landsat",
                "Sentinel",
                "MODIS",
                "Elevation",
                "Land Cover",
                "Climate & Weather",
                "Boundaries",
                "Night Lights",
                "Population",
                "Water",
            ]
        )
        general_layout.addRow("Default category:", self.default_category)

        layout.addWidget(general_group)

        # Cache options
        cache_group = QGroupBox("Cache")
        cache_layout = QFormLayout(cache_group)

        self.cache_enabled = QCheckBox()
        self.cache_enabled.setChecked(True)
        cache_layout.addRow("Enable catalog cache:", self.cache_enabled)

        self.cache_duration = QSpinBox()
        self.cache_duration.setRange(1, 168)  # 1 hour to 1 week
        self.cache_duration.setValue(24)
        self.cache_duration.setSuffix(" hours")
        cache_layout.addRow("Cache duration:", self.cache_duration)

        layout.addWidget(cache_group)

        layout.addStretch()
        return widget

    def _create_ee_tab(self):
        """Create the Earth Engine settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Project settings
        project_group = QGroupBox("Earth Engine Project")
        project_layout = QFormLayout(project_group)

        self.ee_project_input = QLineEdit()
        self.ee_project_input.setPlaceholderText("Enter GCP project ID...")
        project_layout.addRow("Project ID:", self.ee_project_input)

        info_label = QLabel(
            "<small>Leave empty to use EE_PROJECT_ID environment variable.<br>"
            "Set the project ID if auto-initialization fails.</small>"
        )
        info_label.setWordWrap(True)
        project_layout.addRow("", info_label)

        layout.addWidget(project_group)

        # Default filters
        filters_group = QGroupBox("Default Filters")
        filters_layout = QFormLayout(filters_group)

        self.default_cloud_cover = QSpinBox()
        self.default_cloud_cover.setRange(0, 100)
        self.default_cloud_cover.setValue(20)
        self.default_cloud_cover.setSuffix("%")
        filters_layout.addRow("Default max cloud cover:", self.default_cloud_cover)

        self.default_date_range = QSpinBox()
        self.default_date_range.setRange(1, 365 * 10)
        self.default_date_range.setValue(365)
        self.default_date_range.setSuffix(" days")
        filters_layout.addRow("Default date range:", self.default_date_range)

        layout.addWidget(filters_group)

        # Performance
        perf_group = QGroupBox("Performance")
        perf_layout = QFormLayout(perf_group)

        self.max_features = QSpinBox()
        self.max_features.setRange(100, 50000)
        self.max_features.setValue(5000)
        perf_layout.addRow("Max features to load:", self.max_features)

        self.tile_size = QComboBox()
        self.tile_size.addItems(["256", "512", "1024"])
        self.tile_size.setCurrentText("256")
        perf_layout.addRow("Tile size:", self.tile_size)

        layout.addWidget(perf_group)

        layout.addStretch()
        return widget

    def _create_display_tab(self):
        """Create the display settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Layer options
        layer_group = QGroupBox("Layer Options")
        layer_layout = QFormLayout(layer_group)

        self.default_opacity = QDoubleSpinBox()
        self.default_opacity.setRange(0.0, 1.0)
        self.default_opacity.setValue(1.0)
        self.default_opacity.setSingleStep(0.1)
        layer_layout.addRow("Default layer opacity:", self.default_opacity)

        self.add_to_top = QCheckBox()
        self.add_to_top.setChecked(True)
        layer_layout.addRow("Add layers to top:", self.add_to_top)

        self.auto_zoom = QCheckBox()
        self.auto_zoom.setChecked(False)
        layer_layout.addRow("Auto-zoom to layer extent:", self.auto_zoom)

        layout.addWidget(layer_group)

        # Visualization defaults
        vis_group = QGroupBox("Visualization Defaults")
        vis_layout = QFormLayout(vis_group)

        self.default_palette = QComboBox()
        self.default_palette.addItems(
            [
                "viridis",
                "terrain",
                "inferno",
                "plasma",
                "magma",
                "cividis",
                "coolwarm",
                "spectral",
            ]
        )
        vis_layout.addRow("Default color palette:", self.default_palette)

        self.stretch_type = QComboBox()
        self.stretch_type.addItems(["Linear", "Histogram Equalization", "Min-Max"])
        vis_layout.addRow("Default stretch:", self.stretch_type)

        layout.addWidget(vis_group)

        layout.addStretch()
        return widget

    def _load_settings(self):
        """Load settings from QSettings."""
        # General
        self.auto_init_check.setChecked(
            self.settings.value(f"{self.SETTINGS_PREFIX}auto_init", True, type=bool)
        )
        self.notifications_check.setChecked(
            self.settings.value(f"{self.SETTINGS_PREFIX}notifications", True, type=bool)
        )
        self.default_category.setCurrentIndex(
            self.settings.value(f"{self.SETTINGS_PREFIX}default_category", 0, type=int)
        )
        self.cache_enabled.setChecked(
            self.settings.value(f"{self.SETTINGS_PREFIX}cache_enabled", True, type=bool)
        )
        self.cache_duration.setValue(
            self.settings.value(f"{self.SETTINGS_PREFIX}cache_duration", 24, type=int)
        )

        # Earth Engine
        self.ee_project_input.setText(
            self.settings.value(f"{self.SETTINGS_PREFIX}ee_project", "", type=str)
        )
        self.default_cloud_cover.setValue(
            self.settings.value(
                f"{self.SETTINGS_PREFIX}default_cloud_cover", 20, type=int
            )
        )
        self.default_date_range.setValue(
            self.settings.value(
                f"{self.SETTINGS_PREFIX}default_date_range", 365, type=int
            )
        )
        self.max_features.setValue(
            self.settings.value(f"{self.SETTINGS_PREFIX}max_features", 5000, type=int)
        )
        tile_size_index = self.tile_size.findText(
            self.settings.value(f"{self.SETTINGS_PREFIX}tile_size", "256", type=str)
        )
        if tile_size_index >= 0:
            self.tile_size.setCurrentIndex(tile_size_index)

        # Display
        self.default_opacity.setValue(
            self.settings.value(
                f"{self.SETTINGS_PREFIX}default_opacity", 1.0, type=float
            )
        )
        self.add_to_top.setChecked(
            self.settings.value(f"{self.SETTINGS_PREFIX}add_to_top", True, type=bool)
        )
        self.auto_zoom.setChecked(
            self.settings.value(f"{self.SETTINGS_PREFIX}auto_zoom", False, type=bool)
        )
        self.default_palette.setCurrentIndex(
            self.settings.value(f"{self.SETTINGS_PREFIX}default_palette", 0, type=int)
        )
        self.stretch_type.setCurrentIndex(
            self.settings.value(f"{self.SETTINGS_PREFIX}stretch_type", 0, type=int)
        )

        self.status_label.setText("Settings loaded")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")

    def _save_settings(self):
        """Save settings to QSettings."""
        # General
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}auto_init", self.auto_init_check.isChecked()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}notifications", self.notifications_check.isChecked()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}default_category",
            self.default_category.currentIndex(),
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}cache_enabled", self.cache_enabled.isChecked()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}cache_duration", self.cache_duration.value()
        )

        # Earth Engine
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}ee_project", self.ee_project_input.text()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}default_cloud_cover",
            self.default_cloud_cover.value(),
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}default_date_range", self.default_date_range.value()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}max_features", self.max_features.value()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}tile_size", self.tile_size.currentText()
        )

        # Display
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}default_opacity", self.default_opacity.value()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}add_to_top", self.add_to_top.isChecked()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}auto_zoom", self.auto_zoom.isChecked()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}default_palette",
            self.default_palette.currentIndex(),
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}stretch_type", self.stretch_type.currentIndex()
        )

        self.settings.sync()

        self.status_label.setText("Settings saved")
        self.status_label.setStyleSheet("color: green; font-size: 10px;")

        self.iface.messageBar().pushSuccess(
            "GEE Data Catalogs", "Settings saved successfully!"
        )

    def _reset_defaults(self):
        """Reset all settings to defaults."""
        reply = QMessageBox.question(
            self,
            "Reset Settings",
            "Are you sure you want to reset all settings to defaults?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        # General
        self.auto_init_check.setChecked(True)
        self.notifications_check.setChecked(True)
        self.default_category.setCurrentIndex(0)
        self.cache_enabled.setChecked(True)
        self.cache_duration.setValue(24)

        # Earth Engine
        self.ee_project_input.clear()
        self.default_cloud_cover.setValue(20)
        self.default_date_range.setValue(365)
        self.max_features.setValue(5000)
        self.tile_size.setCurrentText("256")

        # Display
        self.default_opacity.setValue(1.0)
        self.add_to_top.setChecked(True)
        self.auto_zoom.setChecked(False)
        self.default_palette.setCurrentIndex(0)
        self.stretch_type.setCurrentIndex(0)

        self.status_label.setText("Defaults restored (not saved)")
        self.status_label.setStyleSheet("color: orange; font-size: 10px;")
