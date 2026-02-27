"""
Python Standalone Manager for GEE Data Catalogs Plugin.

Downloads and manages a standalone Python interpreter that matches
the QGIS Python version, ensuring compatibility for the plugin's
virtual environment.

Source: https://github.com/astral-sh/python-build-standalone
"""

import os
import platform
import shutil
import stat
import subprocess  # nosec B404
import sys
import tarfile
import tempfile
import zipfile
from typing import Callable, Optional, Tuple

from qgis.core import Qgis, QgsBlockingNetworkRequest, QgsMessageLog
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

PLUGIN_NAME = "GEE Data Catalogs"
CACHE_DIR = os.path.expanduser("~/.qgis_gee_data_catalogs")
STANDALONE_DIR = os.path.join(CACHE_DIR, "python_standalone")

# Release tag from python-build-standalone
RELEASE_TAG = "20241219"

# Mapping of Python minor versions to their latest patch versions in the release
PYTHON_VERSIONS = {
    (3, 9): "3.9.21",
    (3, 10): "3.10.16",
    (3, 11): "3.11.11",
    (3, 12): "3.12.8",
    (3, 13): "3.13.1",
}


def _log(message: str, level=Qgis.Info):
    """Log a message to the QGIS message log.

    Args:
        message: The message to log.
        level: The log level (Qgis.Info, Qgis.Warning, Qgis.Critical).
    """
    QgsMessageLog.logMessage(str(message), PLUGIN_NAME, level=level)


def _safe_extract_tar(tar: tarfile.TarFile, dest_dir: str):
    """Safely extract tar archive with path traversal protection.

    Args:
        tar: An open tarfile.TarFile object.
        dest_dir: Destination directory for extraction.
    """
    dest_dir = os.path.realpath(dest_dir)
    use_filter = sys.version_info >= (3, 12)
    for member in tar.getmembers():
        member_path = os.path.realpath(os.path.join(dest_dir, member.name))
        if not member_path.startswith(dest_dir + os.sep) and member_path != dest_dir:
            raise ValueError(f"Attempted path traversal in tar archive: {member.name}")
        if use_filter:
            tar.extract(member, dest_dir, filter="data")
        else:
            tar.extract(member, dest_dir)


def _safe_extract_zip(zip_file: zipfile.ZipFile, dest_dir: str):
    """Safely extract zip archive with path traversal protection.

    Args:
        zip_file: An open zipfile.ZipFile object.
        dest_dir: Destination directory for extraction.
    """
    dest_dir = os.path.realpath(dest_dir)
    for member in zip_file.namelist():
        member_path = os.path.realpath(os.path.join(dest_dir, member))
        if not member_path.startswith(dest_dir + os.sep) and member_path != dest_dir:
            raise ValueError(f"Attempted path traversal in zip archive: {member}")
        zip_file.extract(member, dest_dir)


def get_qgis_python_version() -> Tuple[int, int]:
    """Get the Python version used by QGIS.

    Returns:
        A tuple of (major, minor) version numbers.
    """
    return (sys.version_info.major, sys.version_info.minor)


def get_python_full_version() -> str:
    """Get the full Python version string for download.

    Returns:
        A version string like '3.12.8'.
    """
    version_tuple = get_qgis_python_version()
    if version_tuple in PYTHON_VERSIONS:
        return PYTHON_VERSIONS[version_tuple]
    return f"{version_tuple[0]}.{version_tuple[1]}.0"


def get_standalone_python_path() -> str:
    """Get the path to the standalone Python executable.

    Returns:
        The absolute path to the Python executable.
    """
    python_dir = os.path.join(STANDALONE_DIR, "python")
    if sys.platform == "win32":
        return os.path.join(python_dir, "python.exe")
    return os.path.join(python_dir, "bin", "python3")


def standalone_python_exists() -> bool:
    """Check if standalone Python is already installed.

    Returns:
        True if the standalone Python executable exists.
    """
    return os.path.exists(get_standalone_python_path())


def _get_platform_info() -> Tuple[str, str]:
    """Get platform and architecture info for download URL.

    Returns:
        A tuple of (platform_string, file_extension).
    """
    system = sys.platform
    machine = platform.machine().lower()

    if system == "darwin":
        if machine in ("arm64", "aarch64"):
            return ("aarch64-apple-darwin", ".tar.gz")
        return ("x86_64-apple-darwin", ".tar.gz")
    elif system == "win32":
        return ("x86_64-pc-windows-msvc", ".tar.gz")
    else:
        if machine in ("arm64", "aarch64"):
            return ("aarch64-unknown-linux-gnu", ".tar.gz")
        return ("x86_64-unknown-linux-gnu", ".tar.gz")


def get_download_url() -> str:
    """Construct the download URL for the standalone Python.

    Returns:
        The full download URL string.
    """
    python_version = get_python_full_version()
    platform_str, ext = _get_platform_info()
    filename = (
        f"cpython-{python_version}+{RELEASE_TAG}-{platform_str}-install_only{ext}"
    )
    url = (
        f"https://github.com/astral-sh/python-build-standalone/releases/"
        f"download/{RELEASE_TAG}/{filename}"
    )
    return url


def download_python_standalone(
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Tuple[bool, str]:
    """Download and install Python standalone using QGIS network manager.

    Uses QgsBlockingNetworkRequest to respect QGIS proxy settings.

    Args:
        progress_callback: Function called with (percent, message) for progress.
        cancel_check: Function that returns True if operation should be cancelled.

    Returns:
        A tuple of (success, message).
    """
    if standalone_python_exists():
        _log("Python standalone already exists")
        return True, "Python standalone already installed"

    url = get_download_url()
    python_version = get_python_full_version()

    _log(f"Downloading Python {python_version} from: {url}")

    if progress_callback:
        progress_callback(0, f"Downloading Python {python_version}...")

    fd, temp_path = tempfile.mkstemp(suffix=".tar.gz")
    os.close(fd)

    try:
        if cancel_check and cancel_check():
            return False, "Download cancelled"

        request = QgsBlockingNetworkRequest()
        qurl = QUrl(url)

        if progress_callback:
            progress_callback(5, "Connecting to download server...")

        err = request.get(QNetworkRequest(qurl))

        if err != QgsBlockingNetworkRequest.NoError:
            error_msg = request.errorMessage()
            if "404" in error_msg or "Not Found" in error_msg:
                error_msg = (
                    f"Python {python_version} not available for this platform. "
                    f"URL: {url}"
                )
            else:
                error_msg = f"Download failed: {error_msg}"
            _log(error_msg, Qgis.Critical)
            return False, error_msg

        if cancel_check and cancel_check():
            return False, "Download cancelled"

        reply = request.reply()
        content = reply.content()

        if progress_callback:
            total_mb = len(content) / (1024 * 1024)
            progress_callback(50, f"Downloaded {total_mb:.1f} MB, saving...")

        with open(temp_path, "wb") as f:
            f.write(content.data())

        _log(f"Download complete ({len(content)} bytes), extracting...")

        if progress_callback:
            progress_callback(55, "Extracting Python...")

        if os.path.exists(STANDALONE_DIR):
            shutil.rmtree(STANDALONE_DIR)

        os.makedirs(STANDALONE_DIR, exist_ok=True)

        if temp_path.endswith((".tar.gz", ".tgz")):
            with tarfile.open(temp_path, "r:gz") as tar:
                _safe_extract_tar(tar, STANDALONE_DIR)
        else:
            with zipfile.ZipFile(temp_path, "r") as z:
                _safe_extract_zip(z, STANDALONE_DIR)

        if progress_callback:
            progress_callback(80, "Verifying Python installation...")

        success, verify_msg = verify_standalone_python()

        if success:
            if progress_callback:
                progress_callback(100, f"Python {python_version} installed")
            _log("Python standalone installed successfully")
            return True, f"Python {python_version} installed successfully"
        else:
            return False, f"Verification failed: {verify_msg}"

    except InterruptedError:
        return False, "Download cancelled"
    except Exception as e:
        error_msg = f"Installation failed: {str(e)}"
        _log(error_msg, Qgis.Critical)

        if sys.platform == "win32":
            error_lower = str(e).lower()
            if any(kw in error_lower for kw in ("denied", "access", "permission")):
                error_msg += (
                    "\n\nThis may be caused by antivirus software. "
                    "Try adding an exclusion for: " + STANDALONE_DIR
                )

        return False, error_msg
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def verify_standalone_python() -> Tuple[bool, str]:
    """Verify that the standalone Python installation works.

    Returns:
        A tuple of (success, message).
    """
    python_path = get_standalone_python_path()

    if not os.path.exists(python_path):
        return False, f"Python executable not found at {python_path}"

    if sys.platform != "win32":
        try:
            os.chmod(
                python_path,
                stat.S_IRWXU
                | stat.S_IRGRP
                | stat.S_IXGRP
                | stat.S_IROTH
                | stat.S_IXOTH,
            )
        except OSError:
            pass

    try:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env["PYTHONIOENCODING"] = "utf-8"

        kwargs: dict = {}
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = startupinfo

        result = subprocess.run(  # nosec B603
            [python_path, "-c", "import sys; print(sys.version)"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
            **kwargs,
        )

        if result.returncode == 0:
            version_output = result.stdout.strip().split()[0]
            if not version_output.startswith(
                f"{sys.version_info.major}.{sys.version_info.minor}"
            ):
                _log(f"Python version mismatch: got {version_output}", Qgis.Warning)
                return False, f"Version mismatch: {version_output}"

            _log(f"Verified Python standalone: {version_output}")
            return True, f"Python {version_output} verified"
        else:
            error = result.stderr or "Unknown error"
            _log(f"Python verification failed: {error}", Qgis.Warning)
            return False, f"Verification failed: {error[:100]}"

    except subprocess.TimeoutExpired:
        return False, "Python verification timed out"
    except Exception as e:
        return False, f"Verification error: {str(e)[:100]}"


def remove_standalone_python() -> Tuple[bool, str]:
    """Remove the standalone Python installation.

    Returns:
        A tuple of (success, message).
    """
    if not os.path.exists(STANDALONE_DIR):
        return True, "Standalone Python not installed"

    try:
        shutil.rmtree(STANDALONE_DIR)
        _log("Removed standalone Python installation")
        return True, "Standalone Python removed"
    except Exception as e:
        error_msg = f"Failed to remove: {str(e)}"
        _log(error_msg, Qgis.Warning)
        return False, error_msg
