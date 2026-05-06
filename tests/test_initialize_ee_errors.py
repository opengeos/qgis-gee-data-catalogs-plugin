import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EE_UTILS_PATH = REPO_ROOT / "gee_data_catalogs" / "core" / "ee_utils.py"


def _install_qgis_stubs(monkeypatch, settings_store=None):
    settings_store = settings_store if settings_store is not None else {}

    class FakeQSettings:
        def value(self, key, default=None, type=None):
            value = settings_store.get(key, default)
            if type is not None and value is not None:
                try:
                    return type(value)
                except Exception:
                    return value
            return value

    class FakeQgsProject:
        @classmethod
        def instance(cls):
            return cls()

    class FakeQgsMessageLog:
        @staticmethod
        def logMessage(*args, **kwargs):
            return None

    fake_qgis = types.ModuleType("qgis")
    fake_qgis_core = types.ModuleType("qgis.core")
    fake_qgis_core.QgsProject = FakeQgsProject
    fake_qgis_core.QgsRasterLayer = type("QgsRasterLayer", (), {})
    fake_qgis_core.QgsMessageLog = FakeQgsMessageLog
    fake_qgis_core.Qgis = types.SimpleNamespace(
        Info=1,
        Warning=2,
        MessageLevel=types.SimpleNamespace(Info=1, Warning=2, Success=3),
    )

    fake_pyqt = types.ModuleType("qgis.PyQt")
    fake_qtcore = types.ModuleType("qgis.PyQt.QtCore")
    fake_qtcore.QSettings = FakeQSettings

    monkeypatch.setitem(sys.modules, "qgis", fake_qgis)
    monkeypatch.setitem(sys.modules, "qgis.core", fake_qgis_core)
    monkeypatch.setitem(sys.modules, "qgis.PyQt", fake_pyqt)
    monkeypatch.setitem(sys.modules, "qgis.PyQt.QtCore", fake_qtcore)


def _load_ee_utils(monkeypatch, fake_ee, settings_store=None):
    _install_qgis_stubs(monkeypatch, settings_store=settings_store)
    monkeypatch.setitem(sys.modules, "ee", fake_ee)

    module_name = "ee_utils_under_test"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, EE_UTILS_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_initialize_failure_preserves_error_and_does_not_authenticate(monkeypatch):
    def initialize(*args, **kwargs):
        raise RuntimeError("project does not have Earth Engine API enabled")

    def authenticate(*args, **kwargs):
        raise AssertionError("initialize_ee must not call ee.Authenticate()")

    fake_ee = types.SimpleNamespace(Initialize=initialize, Authenticate=authenticate)
    ee_utils = _load_ee_utils(monkeypatch, fake_ee)
    monkeypatch.setattr(ee_utils, "_check_credentials_exist", lambda: True)

    assert ee_utils.initialize_ee(project="bad-project") is False
    assert "project does not have Earth Engine API enabled" in (
        ee_utils.get_last_init_error() or ""
    )


def test_initialize_does_not_pass_credentials_kwarg(monkeypatch):
    received_kwargs = {}

    def initialize(*args, **kwargs):
        received_kwargs.update(kwargs)

    fake_ee = types.SimpleNamespace(
        Initialize=initialize,
        data=types.SimpleNamespace(
            getUserAgent=lambda: "old-agent",
            setUserAgent=lambda value: None,
        ),
    )
    ee_utils = _load_ee_utils(monkeypatch, fake_ee)
    monkeypatch.setattr(ee_utils, "_check_credentials_exist", lambda: True)

    assert ee_utils.initialize_ee(project="my-project") is True
    assert received_kwargs == {"project": "my-project"}
    assert "credentials" not in received_kwargs


def test_project_lookup_prefers_explicit_then_settings_then_env(monkeypatch):
    projects = []

    def initialize(*args, **kwargs):
        projects.append(kwargs.get("project"))

    fake_ee = types.SimpleNamespace(
        Initialize=initialize,
        data=types.SimpleNamespace(
            getUserAgent=lambda: "old-agent",
            setUserAgent=lambda value: None,
        ),
    )
    settings_store = {"GeeDataCatalogs/ee_project": "settings-project"}
    ee_utils = _load_ee_utils(monkeypatch, fake_ee, settings_store=settings_store)
    monkeypatch.setattr(ee_utils, "_check_credentials_exist", lambda: True)

    assert ee_utils.initialize_ee(project="explicit-project", force=True) is True
    ee_utils.mark_ee_initialized(False)

    assert ee_utils.initialize_ee(force=True) is True
    ee_utils.mark_ee_initialized(False)

    settings_store.clear()
    monkeypatch.setenv("EE_PROJECT_ID", "env-project")
    assert ee_utils.initialize_ee(force=True) is True

    assert projects == ["explicit-project", "settings-project", "env-project"]


def test_mark_initialized_clears_last_init_error(monkeypatch):
    def initialize(*args, **kwargs):
        raise RuntimeError("refresh token expired")

    fake_ee = types.SimpleNamespace(
        Initialize=initialize,
        data=types.SimpleNamespace(
            getUserAgent=lambda: "old-agent",
            setUserAgent=lambda value: None,
        ),
    )
    ee_utils = _load_ee_utils(monkeypatch, fake_ee)
    monkeypatch.setattr(ee_utils, "_check_credentials_exist", lambda: True)

    assert ee_utils.initialize_ee(project="bad-project", force=True) is False
    assert "refresh token expired" in (ee_utils.get_last_init_error() or "")

    ee_utils.mark_ee_initialized(True)

    assert ee_utils.is_ee_initialized() is True
    assert ee_utils.get_last_init_error() is None
