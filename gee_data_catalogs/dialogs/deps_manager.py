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


class EEInitWorker(QThread):
    """Worker thread that initializes and verifies Earth Engine.

    Runs ``core.ee_utils.initialize_ee`` and a small ``getInfo()`` round-trip
    off the UI thread so QGIS does not freeze on slow networks.

    Signals:
        finished: Emitted with (success: bool, message: str) when done.
    """

    finished = pyqtSignal(bool, str)

    def __init__(self, project, credentials_path=None, parent=None):
        """Initialize the EE init worker.

        Args:
            project: Google Cloud project ID to pass through to Earth Engine.
            credentials_path: Optional filesystem path to a service-account
                JSON credentials file.
            parent: Parent QObject.
        """
        super().__init__(parent)
        self._project = project
        self._credentials_path = credentials_path

    def run(self):
        """Initialize EE and verify with a getInfo round-trip."""
        try:
            credentials = None
            if self._credentials_path:
                try:
                    from google.oauth2 import service_account
                except ImportError:
                    self.finished.emit(
                        False,
                        "Service-account credentials require the 'google-auth' "
                        "package. Install it via Settings -> Dependencies, then "
                        "retry.",
                    )
                    return
                try:
                    credentials = service_account.Credentials.from_service_account_file(
                        self._credentials_path,
                        scopes=["https://www.googleapis.com/auth/earthengine"],
                    )
                except Exception as exc:
                    self.finished.emit(
                        False,
                        f"Failed to load credentials file: {exc}",
                    )
                    return

            from ..core.ee_utils import get_last_init_error, initialize_ee

            ok = initialize_ee(
                project=self._project, force=True, credentials=credentials
            )
            if not ok:
                self.finished.emit(
                    False,
                    get_last_init_error() or "Earth Engine initialization failed.",
                )
                return

            try:
                import ee
            except ImportError:
                self.finished.emit(False, "earthengine-api is not installed.")
                return

            try:
                ee.Number(1).getInfo()
            except Exception as exc:
                project_desc = self._project or "(no project)"
                self.finished.emit(
                    False,
                    "Initialize succeeded but a test request failed: "
                    f"{exc}. Common causes: the Earth Engine API is not "
                    f"enabled for project '{project_desc}', the account is "
                    "not registered, or the credentials are missing the "
                    "required scopes.",
                )
                return

            self.finished.emit(True, "Earth Engine initialized & verified.")
        except Exception as e:
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.finished.emit(False, error_msg)
