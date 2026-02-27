"""
Dependency Installation Dock Widget for GEE Data Catalogs Plugin.

Provides a dockable panel for one-click installation of plugin dependencies
(earthengine-api) into an isolated virtual environment.
"""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class DependencyDockWidget(QDockWidget):
    """Dockable panel for managing plugin dependency installation."""

    install_succeeded = pyqtSignal()

    def __init__(self, iface, parent=None):
        """Initialize the dependency dock widget.

        Args:
            iface: QGIS interface instance.
            parent: Parent widget.
        """
        super().__init__("GEE Data Catalogs - Dependencies", parent)
        self.iface = iface
        self._deps_worker = None

        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._setup_ui()
        self._refresh_deps_status()

    def _setup_ui(self):
        """Set up the dock widget UI."""
        main_widget = QWidget()
        self.setWidget(main_widget)

        layout = QVBoxLayout(main_widget)
        layout.setSpacing(10)

        # Header
        header = QLabel("Install Dependencies")
        header_font = QFont()
        header_font.setPointSize(12)
        header_font.setBold(True)
        header.setFont(header_font)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Info label
        info = QLabel(
            "This plugin requires the <b>earthengine-api</b> Python package.<br><br>"
            "Click 'Install Dependencies' to install it in an<br>"
            "isolated virtual environment at:<br>"
            "<code>~/.qgis_gee_data_catalogs/</code><br><br>"
            "Your QGIS Python environment will not be modified."
        )
        info.setWordWrap(True)
        info.setTextFormat(Qt.RichText)
        layout.addWidget(info)

        # Package status group
        status_group = QGroupBox("Package Status")
        self._deps_status_layout = QFormLayout(status_group)

        self._deps_labels = {}
        from ..core.venv_manager import REQUIRED_PACKAGES

        for package_name, _version_spec in REQUIRED_PACKAGES:
            label = QLabel("Checking...")
            label.setStyleSheet("color: gray;")
            self._deps_labels[package_name] = label
            self._deps_status_layout.addRow(f"{package_name}:", label)

        layout.addWidget(status_group)

        # Install button
        self._install_btn = QPushButton("Install Dependencies")
        self._install_btn.setMinimumWidth(160)
        self._install_btn.clicked.connect(self._start_install)
        layout.addWidget(self._install_btn)

        # Progress bar (hidden initially)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        # Progress/status label
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)

        # Cancel button (hidden by default)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setStyleSheet("color: red;")
        self._cancel_btn.setVisible(False)
        self._cancel_btn.clicked.connect(self._cancel_install)
        layout.addWidget(self._cancel_btn)

        # Buttons row
        btn_layout = QHBoxLayout()

        self._refresh_btn = QPushButton("Refresh Status")
        self._refresh_btn.clicked.connect(self._refresh_deps_status)
        btn_layout.addWidget(self._refresh_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Stretch at the end
        layout.addStretch()

    def _refresh_deps_status(self):
        """Refresh the dependency status display."""
        from ..core.venv_manager import check_dependencies

        all_ok, missing, installed = check_dependencies()

        for package_name, version in installed:
            if package_name in self._deps_labels:
                self._deps_labels[package_name].setText(f"v{version} (installed)")
                self._deps_labels[package_name].setStyleSheet(
                    "color: green; font-weight: bold;"
                )

        for package_name, _version_spec in missing:
            if package_name in self._deps_labels:
                self._deps_labels[package_name].setText("Not installed")
                self._deps_labels[package_name].setStyleSheet("color: red;")

        self._install_btn.setEnabled(not all_ok)
        if all_ok:
            self._install_btn.setText("All Dependencies Installed")
        else:
            self._install_btn.setText(f"Install Dependencies ({len(missing)} missing)")

    def _start_install(self):
        """Start the dependency installation."""
        from .deps_manager import DepsInstallWorker

        # Guard against concurrent installs
        if self._deps_worker is not None and self._deps_worker.isRunning():
            return

        # Update UI for installation mode
        self._install_btn.setEnabled(False)
        self._refresh_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._status_label.setVisible(True)
        self._status_label.setText("Starting installation...")
        self._status_label.setStyleSheet("")
        self._cancel_btn.setVisible(True)
        self._cancel_btn.setEnabled(True)

        # Start worker
        self._deps_worker = DepsInstallWorker()
        self._deps_worker.progress.connect(self._on_progress)
        self._deps_worker.finished.connect(self._on_finished)
        self._deps_worker.start()

    def _on_progress(self, percent: int, message: str):
        """Handle progress updates from the worker.

        Args:
            percent: Progress percentage (0-100).
            message: Status message.
        """
        self._progress_bar.setValue(percent)
        self._status_label.setText(message)

    def _on_finished(self, success: bool, message: str):
        """Handle installation completion.

        Args:
            success: Whether the installation succeeded.
            message: Result message.
        """
        self._deps_worker = None

        # Reset UI
        self._progress_bar.setVisible(False)
        self._status_label.setText(message)
        self._cancel_btn.setVisible(False)
        self._refresh_btn.setEnabled(True)

        if success:
            self._status_label.setStyleSheet("color: green; font-weight: bold;")
            self.iface.messageBar().pushSuccess(
                "GEE Data Catalogs", "Dependencies installed successfully!"
            )
            self.install_succeeded.emit()
        else:
            self._status_label.setStyleSheet("color: red;")
            self._install_btn.setEnabled(True)

        # Refresh status display
        self._refresh_deps_status()

    def _cancel_install(self):
        """Cancel the ongoing dependency installation."""
        if self._deps_worker is not None and self._deps_worker.isRunning():
            self._deps_worker.cancel()
            self._cancel_btn.setEnabled(False)
            self._status_label.setText("Cancelling...")
