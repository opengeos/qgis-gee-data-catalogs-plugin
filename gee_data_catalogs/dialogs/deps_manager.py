"""
Dependency Installation Worker for GEE Data Catalogs Plugin.

Provides QThread-based workers that run dependency installation and
Earth Engine authentication in the background to avoid freezing the
QGIS UI.
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


class EEAuthWorker(QThread):
    """Worker thread that runs ee.Authenticate() in the background.

    Launches the authentication subprocess which opens a browser for
    OAuth, then waits for the user to complete authentication.

    Signals:
        progress: Emitted with (percent: int, message: str) during auth.
        finished: Emitted with (success: bool, message: str) when done.
    """

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        """Initialize the EE authentication worker.

        Args:
            parent: Parent QObject.
        """
        super().__init__(parent)

    def run(self):
        """Run ee.Authenticate() in the venv Python."""
        try:
            from ..core.venv_manager import authenticate_ee

            success, message = authenticate_ee(
                progress_callback=lambda percent, msg: self.progress.emit(percent, msg),
            )
            self.finished.emit(success, message)
        except Exception as e:
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.finished.emit(False, error_msg)
