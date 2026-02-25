"""
Virtual Environment Manager for GEE Data Catalogs

This module handles creating and managing an isolated Python virtual environment
for plugin dependencies (earthengine-api). The venv is stored externally at
~/.qgis_gee_data_catalogs/ so it persists across plugin reinstalls.
"""

import hashlib
import os
import platform
import shutil
import subprocess  # nosec B404 — used with hardcoded commands only, no user input
import sys
from typing import Callable, List, Optional, Tuple

from qgis.core import QgsMessageLog, Qgis

PLUGIN_NAME = "GEE Data Catalogs"
PYTHON_VERSION = f"py{sys.version_info.major}.{sys.version_info.minor}"
VENV_BASE_DIR = os.path.expanduser("~/.qgis_gee_data_catalogs")
VENV_DIR = os.path.join(VENV_BASE_DIR, f"venv_{PYTHON_VERSION}")

REQUIRED_PACKAGES = [
    ("earthengine-api", ">=1.4.0"),
]

DEPS_HASH_FILE = os.path.join(VENV_DIR, "deps_hash.txt")

# Bump this when install logic changes significantly to force a re-install.
_INSTALL_LOGIC_VERSION = "1"


def _log(message: str, level=Qgis.Info):
    """Log a message to the QGIS message log.

    Args:
        message: The message to log.
        level: The log level (Qgis.Info, Qgis.Warning, Qgis.Critical).
    """
    QgsMessageLog.logMessage(message, PLUGIN_NAME, level=level)


# ---------------------------------------------------------------------------
# Hash-based invalidation
# ---------------------------------------------------------------------------


def _compute_deps_hash() -> str:
    """Compute MD5 hash of REQUIRED_PACKAGES + install logic version.

    Returns:
        The hex digest of the hash.
    """
    data = repr(REQUIRED_PACKAGES).encode("utf-8")
    data += _INSTALL_LOGIC_VERSION.encode("utf-8")
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def _read_deps_hash() -> Optional[str]:
    """Read stored deps hash from the venv directory.

    Returns:
        The stored hash string, or None if not found.
    """
    try:
        with open(DEPS_HASH_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except (OSError, IOError):
        return None


def _write_deps_hash():
    """Write the current deps hash to the venv directory."""
    try:
        os.makedirs(os.path.dirname(DEPS_HASH_FILE), exist_ok=True)
        with open(DEPS_HASH_FILE, "w", encoding="utf-8") as f:
            f.write(_compute_deps_hash())
    except (OSError, IOError) as e:
        _log(f"Failed to write deps hash: {e}", Qgis.Warning)


# ---------------------------------------------------------------------------
# Platform-aware path helpers
# ---------------------------------------------------------------------------


def get_venv_python_path(venv_dir: str = None) -> str:
    """Get the Python executable path within the venv.

    Args:
        venv_dir: Path to the venv. Defaults to VENV_DIR.

    Returns:
        The absolute path to the Python executable in the venv.
    """
    if venv_dir is None:
        venv_dir = VENV_DIR
    if sys.platform == "win32":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python3")


def get_venv_site_packages(venv_dir: str = None) -> str:
    """Get the site-packages path within the venv.

    Args:
        venv_dir: Path to the venv. Defaults to VENV_DIR.

    Returns:
        The absolute path to the site-packages directory in the venv.
    """
    if venv_dir is None:
        venv_dir = VENV_DIR
    if sys.platform == "win32":
        return os.path.join(venv_dir, "Lib", "site-packages")

    # On Unix, detect the actual pythonX.Y directory inside lib/
    lib_dir = os.path.join(venv_dir, "lib")
    if os.path.exists(lib_dir):
        for entry in sorted(os.listdir(lib_dir)):
            if entry.startswith("python") and os.path.isdir(
                os.path.join(lib_dir, entry)
            ):
                site_packages = os.path.join(lib_dir, entry, "site-packages")
                if os.path.exists(site_packages):
                    return site_packages

    # Fallback based on current interpreter version
    py_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return os.path.join(venv_dir, "lib", py_version, "site-packages")


def venv_exists(venv_dir: str = None) -> bool:
    """Check if the venv exists by looking for the Python executable.

    Args:
        venv_dir: Path to the venv. Defaults to VENV_DIR.

    Returns:
        True if the venv Python executable exists.
    """
    if venv_dir is None:
        venv_dir = VENV_DIR
    return os.path.exists(get_venv_python_path(venv_dir))


# ---------------------------------------------------------------------------
# Status check (fast, filesystem-only)
# ---------------------------------------------------------------------------


def get_venv_status() -> Tuple[bool, str]:
    """Quick filesystem check for dependency readiness.

    Returns:
        Tuple of (is_ready, status_message).
    """
    if not venv_exists():
        return False, "Dependencies not installed"

    site_packages = get_venv_site_packages()
    if not os.path.exists(site_packages):
        return False, "Virtual environment incomplete"

    # Check for earthengine-api marker (the 'ee' package directory)
    ee_dir = os.path.join(site_packages, "ee")
    if not os.path.isdir(ee_dir):
        return False, "earthengine-api not installed"

    # Check hash-based invalidation
    stored_hash = _read_deps_hash()
    current_hash = _compute_deps_hash()
    if stored_hash is not None and stored_hash != current_hash:
        return False, "Dependencies need update"
    if stored_hash is None:
        return False, "Dependencies need verification"

    return True, "Dependencies ready"


# ---------------------------------------------------------------------------
# sys.path injection
# ---------------------------------------------------------------------------


def ensure_venv_packages_available() -> bool:
    """Add venv site-packages to sys.path so dependencies can be imported.

    Also patches the 'ee' module into any already-loaded modules that had
    set ee = None due to ImportError before the venv was available.

    Returns:
        True if site-packages were successfully added, False otherwise.
    """
    if not venv_exists():
        _log("Venv does not exist, cannot load packages", Qgis.Warning)
        return False

    site_packages = get_venv_site_packages()
    if not os.path.exists(site_packages):
        _log(f"Venv site-packages not found: {site_packages}", Qgis.Warning)
        return False

    if site_packages not in sys.path:
        sys.path.insert(0, site_packages)
        _log(f"Added venv site-packages to sys.path: {site_packages}")

    # Patch ee into already-loaded modules that cached ee = None at import time
    _patch_ee_module()

    return True


def _patch_ee_module():
    """Import ee from venv and patch it into modules that cached ee = None.

    When ee_utils.py or catalog_dock.py are loaded before the venv is on
    sys.path, their module-level ``try: import ee except ImportError: ee = None``
    caches ee as None. After injecting the venv site-packages we need to
    force-import ee and update those module globals.
    """
    try:
        # Remove stale ee entry from sys.modules so Python re-imports from venv
        if "ee" in sys.modules and sys.modules["ee"] is None:
            del sys.modules["ee"]

        import ee  # noqa: F811 — now resolves from venv site-packages

        # Patch into any already-loaded plugin modules that have ee = None
        for mod_name, mod in list(sys.modules.items()):
            if mod is None:
                continue
            if not mod_name.startswith("gee_data_catalogs"):
                continue
            if hasattr(mod, "ee") and getattr(mod, "ee") is None:
                mod.ee = ee
                _log(f"Patched ee into {mod_name}")

    except ImportError as exc:
        _log(f"Failed to import ee after venv injection: {exc}", Qgis.Warning)


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------


def _get_clean_env_for_venv() -> dict:
    """Get a clean environment for venv subprocess operations.

    Returns:
        A copy of os.environ with QGIS-specific variables removed.
    """
    env = os.environ.copy()
    vars_to_remove = [
        "PYTHONPATH",
        "PYTHONHOME",
        "VIRTUAL_ENV",
        "QGIS_PREFIX_PATH",
        "QGIS_PLUGINPATH",
    ]
    for var in vars_to_remove:
        env.pop(var, None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _get_subprocess_kwargs() -> dict:
    """Get platform-specific subprocess kwargs (hide console on Windows).

    Returns:
        A dict of kwargs to pass to subprocess.run.
    """
    kwargs = {}
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def _get_python_for_venv() -> str:
    """Get a Python executable suitable for creating venvs.

    Handles the macOS edge case where sys.executable may point to
    the QGIS binary instead of Python.

    Returns:
        Path to a working Python executable.
    """
    subprocess_kwargs = _get_subprocess_kwargs()
    candidates = [sys.executable]

    if sys.platform != "win32":
        candidates.append(os.path.join(sys.prefix, "bin", "python3"))
        candidates.append(os.path.join(sys.prefix, "bin", "python"))
    else:
        candidates.append(os.path.join(sys.prefix, "python.exe"))
        candidates.append(os.path.join(sys.prefix, "python3.exe"))

    for candidate in candidates:
        if not os.path.exists(candidate):
            continue
        try:
            result = subprocess.run(  # nosec B603
                [candidate, "-c", "import venv; print('ok')"],
                capture_output=True,
                text=True,
                timeout=10,
                **subprocess_kwargs,
            )
            if result.returncode == 0 and "ok" in result.stdout:
                return candidate
        except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
            _log(f"Python candidate {candidate} failed: {exc}", Qgis.Warning)

    # Last resort
    return sys.executable


# ---------------------------------------------------------------------------
# Venv creation
# ---------------------------------------------------------------------------


def _cleanup_partial_venv(venv_dir: str):
    """Remove a partially-created venv to prevent broken state on retry.

    Args:
        venv_dir: Path to the venv directory to clean up.
    """
    if os.path.exists(venv_dir):
        try:
            shutil.rmtree(venv_dir, ignore_errors=True)
            _log(f"Cleaned up partial venv: {venv_dir}")
        except Exception:
            _log(f"Could not clean up partial venv: {venv_dir}", Qgis.Warning)


def create_venv(
    venv_dir: str = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Tuple[bool, str]:
    """Create a Python virtual environment at the specified directory.

    Args:
        venv_dir: Path for the venv. Defaults to VENV_DIR.
        progress_callback: Callback for progress updates (percent, message).

    Returns:
        Tuple of (success, message).
    """
    if venv_dir is None:
        venv_dir = VENV_DIR

    _log(f"Creating virtual environment at: {venv_dir}")

    if progress_callback:
        progress_callback(5, "Creating virtual environment...")

    system_python = _get_python_for_venv()
    _log(f"Using Python: {system_python}")

    os.makedirs(os.path.dirname(venv_dir), exist_ok=True)
    cmd = [system_python, "-m", "venv", venv_dir]

    try:
        env = _get_clean_env_for_venv()
        subprocess_kwargs = _get_subprocess_kwargs()

        result = subprocess.run(  # nosec B603
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            **subprocess_kwargs,
        )

        if result.returncode != 0:
            error_msg = (
                result.stderr or result.stdout or f"Return code {result.returncode}"
            )
            _log(f"Failed to create venv: {error_msg}", Qgis.Critical)
            _cleanup_partial_venv(venv_dir)
            return False, f"Failed to create virtual environment: {error_msg[:300]}"

        _log("Virtual environment created successfully")

        # Ensure pip is available (bootstrap if needed)
        python_in_venv = get_venv_python_path(venv_dir)
        pip_check_cmd = [python_in_venv, "-m", "pip", "--version"]
        pip_result = subprocess.run(  # nosec B603
            pip_check_cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
            **subprocess_kwargs,
        )

        if pip_result.returncode != 0:
            _log("pip not found in venv, bootstrapping with ensurepip...")
            ensurepip_cmd = [python_in_venv, "-m", "ensurepip", "--upgrade"]
            ensurepip_result = subprocess.run(  # nosec B603
                ensurepip_cmd,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
                **subprocess_kwargs,
            )
            if ensurepip_result.returncode != 0:
                err = ensurepip_result.stderr or ensurepip_result.stdout
                _log(f"ensurepip failed: {err[:200]}", Qgis.Warning)
                _cleanup_partial_venv(venv_dir)
                return False, f"Failed to bootstrap pip: {err[:200]}"

        if progress_callback:
            progress_callback(15, "Virtual environment created")
        return True, "Virtual environment created"

    except subprocess.TimeoutExpired:
        _cleanup_partial_venv(venv_dir)
        return False, "Virtual environment creation timed out"
    except FileNotFoundError:
        return False, f"Python not found: {system_python}"
    except Exception as e:
        _cleanup_partial_venv(venv_dir)
        return False, f"Error creating virtual environment: {str(e)[:300]}"


# ---------------------------------------------------------------------------
# Dependency installation
# ---------------------------------------------------------------------------


def install_dependencies(
    venv_dir: str = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Tuple[bool, str]:
    """Install required packages into the venv using pip.

    Args:
        venv_dir: Path to the venv. Defaults to VENV_DIR.
        progress_callback: Callback for progress updates (percent, message).
        cancel_check: Callback that returns True if user cancelled.

    Returns:
        Tuple of (success, message).
    """
    if venv_dir is None:
        venv_dir = VENV_DIR

    if not venv_exists(venv_dir):
        return False, "Virtual environment does not exist"

    python_path = get_venv_python_path(venv_dir)
    env = _get_clean_env_for_venv()
    subprocess_kwargs = _get_subprocess_kwargs()

    total = len(REQUIRED_PACKAGES)
    base_progress = 20
    progress_range = 70  # 20% to 90%

    for i, (package_name, version_spec) in enumerate(REQUIRED_PACKAGES):
        if cancel_check and cancel_check():
            return False, "Installation cancelled"

        package_spec = f"{package_name}{version_spec}"
        pkg_progress = base_progress + int(progress_range * i / max(total, 1))

        if progress_callback:
            progress_callback(pkg_progress, f"Installing {package_name}...")

        cmd = [
            python_path,
            "-m",
            "pip",
            "install",
            "--no-warn-script-location",
            "--disable-pip-version-check",
            package_spec,
        ]

        _log(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(  # nosec B603
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 min per package
                env=env,
                **subprocess_kwargs,
            )

            if result.returncode != 0:
                error_output = result.stderr or result.stdout or "Unknown error"
                _log(
                    f"Failed to install {package_name}: {error_output}",
                    Qgis.Critical,
                )
                return (
                    False,
                    f"Failed to install {package_name}:\n{error_output[:500]}",
                )

            _log(f"Successfully installed {package_name}")

        except subprocess.TimeoutExpired:
            return False, f"Installation of {package_name} timed out"
        except Exception as e:
            return False, f"Error installing {package_name}: {str(e)[:300]}"

    # Verify installation
    if progress_callback:
        progress_callback(92, "Verifying installation...")

    verify_cmd = [python_path, "-c", "import ee; print(ee.__version__)"]
    try:
        result = subprocess.run(  # nosec B603
            verify_cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
            **subprocess_kwargs,
        )
        if result.returncode != 0:
            error = result.stderr or result.stdout
            return False, f"Verification failed: {error[:300]}"
        _log(f"Verified ee version: {result.stdout.strip()}")
    except Exception as e:
        return False, f"Verification error: {str(e)[:200]}"

    # Write deps hash on success
    _write_deps_hash()

    if progress_callback:
        progress_callback(100, "Installation complete!")

    return True, "Dependencies installed successfully"


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def create_venv_and_install(
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Tuple[bool, str]:
    """Complete installation: create venv + install packages.

    Progress breakdown:
    - 0-15%: Create virtual environment
    - 15-95%: Install packages
    - 95-100%: Verify installation

    Args:
        progress_callback: Callback for progress updates (percent, message).
        cancel_check: Callback that returns True if user cancelled.

    Returns:
        Tuple of (success, message).
    """
    _log("Starting dependency installation...")
    _log(f"Platform: {platform.system()} {platform.machine()}")
    _log(f"Python: {sys.version}")
    _log(f"Venv dir: {VENV_DIR}")

    # Clean up old venv directories from previous Python versions
    cleanup_old_venv_directories()

    if cancel_check and cancel_check():
        return False, "Installation cancelled"

    # Step 1: Create venv if needed
    if not venv_exists():
        if progress_callback:
            progress_callback(2, "Creating virtual environment...")

        success, msg = create_venv(progress_callback=progress_callback)
        if not success:
            return False, msg
    else:
        _log("Venv already exists, skipping creation")
        if progress_callback:
            progress_callback(15, "Virtual environment exists")

    if cancel_check and cancel_check():
        return False, "Installation cancelled"

    # Step 2: Install dependencies
    success, msg = install_dependencies(
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )

    return success, msg


def cleanup_old_venv_directories() -> List[str]:
    """Remove old venv_pyX.Y directories that don't match current Python version.

    Returns:
        List of removed directory paths.
    """
    current_venv_name = f"venv_{PYTHON_VERSION}"
    removed = []

    if not os.path.exists(VENV_BASE_DIR):
        return removed

    try:
        for entry in os.listdir(VENV_BASE_DIR):
            if entry.startswith("venv_py") and entry != current_venv_name:
                old_path = os.path.join(VENV_BASE_DIR, entry)
                if os.path.isdir(old_path):
                    try:
                        shutil.rmtree(old_path)
                        _log(f"Cleaned up old venv: {old_path}")
                        removed.append(old_path)
                    except Exception as e:
                        _log(
                            f"Failed to remove old venv {old_path}: {e}",
                            Qgis.Warning,
                        )
    except Exception as e:
        _log(f"Error scanning for old venvs: {e}", Qgis.Warning)

    return removed
