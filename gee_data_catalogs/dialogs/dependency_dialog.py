"""
Dependency Installation Dialog for GEE Data Catalogs

This dialog provides one-click installation of plugin dependencies
(earthengine-api) into an isolated virtual environment.
"""

import traceback

from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class DepsInstallWorker(QThread):
    """Worker thread for installing dependencies in the background."""

    progress = pyqtSignal(int, str)  # (percent, message)
    finished = pyqtSignal(bool, str)  # (success, message)

    def __init__(self, parent=None):
        """Initialize the worker thread.

        Args:
            parent: Parent QObject.
        """
        super().__init__(parent)
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the installation."""
        self._cancelled = True

    def run(self):
        """Run the installation in a background thread."""
        try:
            from ..core.venv_manager import create_venv_and_install

            success, message = create_venv_and_install(
                progress_callback=lambda pct, msg: self.progress.emit(pct, msg),
                cancel_check=lambda: self._cancelled,
            )
            self.finished.emit(success, message)
        except Exception as e:
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.finished.emit(False, error_msg)


class DependencyDialog(QDialog):
    """Dialog for installing plugin dependencies."""

    install_succeeded = pyqtSignal()

    def __init__(self, parent=None):
        """Initialize the dependency dialog.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self._worker = None
        self.setWindowTitle("GEE Data Catalogs - Install Dependencies")
        self.setMinimumWidth(500)
        self.setMinimumHeight(350)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QLabel("Install Dependencies")
        header_font = QFont()
        header_font.setPointSize(13)
        header_font.setBold(True)
        header.setFont(header_font)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Info text
        info = QLabel(
            "This plugin requires the <b>earthengine-api</b> Python package.<br><br>"
            "It will be installed into an isolated virtual environment at:<br>"
            "<code>~/.qgis_gee_data_catalogs/</code><br><br>"
            "Your QGIS Python environment will not be modified."
        )
        info.setWordWrap(True)
        info.setTextFormat(Qt.RichText)
        layout.addWidget(info)

        # Status label
        self._status_label = QLabel("Click 'Install Dependencies' to begin.")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # Progress bar (hidden initially)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        # Log text area (hidden initially)
        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumHeight(120)
        self._log_text.setVisible(False)
        layout.addWidget(self._log_text)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._install_btn = QPushButton("Install Dependencies")
        self._install_btn.setMinimumWidth(160)
        self._install_btn.clicked.connect(self._start_install)
        btn_layout.addWidget(self._install_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._cancel_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _start_install(self):
        """Start the dependency installation."""
        self._install_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._log_text.setVisible(True)
        self._log_text.clear()
        self._status_label.setText("Installing dependencies...")
        self._status_label.setStyleSheet("color: palette(text);")

        self._worker = DepsInstallWorker(self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, percent, message):
        """Handle progress updates from the worker.

        Args:
            percent: Progress percentage (0-100).
            message: Status message.
        """
        self._progress_bar.setValue(percent)
        self._status_label.setText(message)
        self._log_text.append(message)

    def _on_finished(self, success, message):
        """Handle installation completion.

        Args:
            success: Whether the installation succeeded.
            message: Result message.
        """
        self._worker = None

        if success:
            self._status_label.setText("Dependencies installed successfully!")
            self._status_label.setStyleSheet("color: green; font-weight: bold;")
            self._progress_bar.setValue(100)
            self._log_text.append("\nDependencies installed successfully!")
            self._install_btn.setText("Done")
            self._install_btn.setEnabled(True)
            self._install_btn.clicked.disconnect()
            self._install_btn.clicked.connect(self.accept)
            self._cancel_btn.setVisible(False)
            self.install_succeeded.emit()
        else:
            self._status_label.setText(f"Installation failed: {message[:200]}")
            self._status_label.setStyleSheet("color: red;")
            self._log_text.append(f"\nERROR: {message}")
            self._install_btn.setText("Retry")
            self._install_btn.setEnabled(True)
            self._install_btn.clicked.disconnect()
            self._install_btn.clicked.connect(self._start_install)

    def _on_cancel(self):
        """Handle cancel button click."""
        if self._worker and self._worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Cancel Installation",
                "Installation is in progress. Are you sure you want to cancel?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self._worker.cancel()
                self._status_label.setText("Cancelling...")
                self._worker.finished.connect(lambda *_: self.reject())
            return
        self.reject()

    def closeEvent(self, event):
        """Handle dialog close event.

        Args:
            event: The close event.
        """
        if self._worker and self._worker.isRunning():
            event.ignore()
            self._on_cancel()
        else:
            event.accept()
