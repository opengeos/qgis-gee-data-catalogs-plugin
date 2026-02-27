"""
Dependency Installation Worker for GEE Data Catalogs Plugin.

Provides a QThread-based worker that runs the full dependency
installation (Python download + uv download + venv creation +
package install) in the background to avoid freezing the QGIS UI.
"""

import traceback

from qgis.PyQt.QtCore import QThread, pyqtSignal


class DepsInstallWorker(QThread):
    """Worker thread that installs all plugin dependencies.

    Runs the full installation pipeline: download standalone Python,
    download uv, create virtual environment, install packages, and verify.

    Signals:
        progress: Emitted with (percent: int, message: str) during installation.
        finished: Emitted with (success: bool, message: str) when done.
    """

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        """Initialize the dependency install worker.

        Args:
            parent: Parent QObject.
        """
        super().__init__(parent)
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the installation."""
        self._cancelled = True

    def run(self):
        """Execute the full dependency installation pipeline."""
        try:
            from ..core.venv_manager import create_venv_and_install

            success, message = create_venv_and_install(
                progress_callback=lambda percent, msg: self.progress.emit(percent, msg),
                cancel_check=lambda: self._cancelled,
            )
            self.finished.emit(success, message)
        except Exception as e:
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.finished.emit(False, error_msg)
