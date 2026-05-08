import types

from gee_data_catalogs.core import venv_manager
from gee_data_catalogs.core import uv_manager


def test_create_venv_uses_uv_managed_python_when_system_python_missing(
    monkeypatch, tmp_path
):
    calls = {}
    venv_dir = str(tmp_path / "venv")

    def fake_run(cmd, capture_output, text, timeout, env, **kwargs):
        calls["cmd"] = cmd
        calls["env"] = env
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        venv_manager,
        "_get_system_python",
        lambda: (_ for _ in ()).throw(RuntimeError("no local python")),
    )
    monkeypatch.setattr(uv_manager, "uv_exists", lambda: True)
    monkeypatch.setattr(uv_manager, "get_uv_path", lambda: "/tmp/uv")
    monkeypatch.setattr(venv_manager.subprocess, "run", fake_run)

    success, message = venv_manager.create_venv(venv_dir=venv_dir)

    assert success is True
    assert message == "Virtual environment created"
    assert calls["cmd"] == [
        "/tmp/uv",
        "venv",
        "--managed-python",
        "--python",
        f"{venv_manager.sys.version_info.major}.{venv_manager.sys.version_info.minor}",
        venv_dir,
    ]
    assert "PYTHONHOME" not in calls["env"]
    assert "PYTHONPATH" not in calls["env"]


def test_authenticate_ee_falls_back_to_resolved_python(monkeypatch):
    calls = {}
    resolved_python = r"C:\Program Files\QGIS 4.0.1\apps\Python312\python.exe"

    def fake_run(cmd, capture_output, text, timeout, env, **kwargs):
        calls["cmd"] = cmd
        calls["env"] = env
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setenv("PYTHONHOME", "/qgis/python")
    monkeypatch.setenv("PYTHONPATH", "/qgis/python/site-packages")
    monkeypatch.setenv("QGIS_PREFIX_PATH", "/qgis")

    monkeypatch.setattr(venv_manager, "venv_exists", lambda: False)
    monkeypatch.setattr(
        venv_manager.importlib.util,
        "find_spec",
        lambda name: object() if name == "ee" else None,
    )
    monkeypatch.setattr(
        venv_manager,
        "_find_python_executable",
        lambda: resolved_python,
    )
    monkeypatch.setattr(venv_manager.subprocess, "run", fake_run)

    success, message = venv_manager.authenticate_ee()

    assert success is True
    assert "completed successfully" in message
    assert calls["cmd"][0] == resolved_python
    assert "PYTHONHOME" not in calls["env"]
    assert "PYTHONPATH" not in calls["env"]
    assert "QGIS_PREFIX_PATH" not in calls["env"]
    assert calls["env"].get("PYTHONIOENCODING") == "utf-8"


def test_authenticate_ee_reports_missing_python_executable(monkeypatch):
    monkeypatch.setattr(venv_manager, "venv_exists", lambda: False)
    monkeypatch.setattr(
        venv_manager.importlib.util,
        "find_spec",
        lambda name: object() if name == "ee" else None,
    )
    monkeypatch.setattr(
        venv_manager,
        "_find_python_executable",
        lambda: (_ for _ in ()).throw(RuntimeError("not found")),
    )

    success, message = venv_manager.authenticate_ee()

    assert success is False
    assert "could not find a real Python executable" in message


def test_authenticate_ee_reports_missing_envs(monkeypatch):
    monkeypatch.setattr(venv_manager, "venv_exists", lambda: False)
    monkeypatch.setattr(venv_manager.importlib.util, "find_spec", lambda name: None)

    success, message = venv_manager.authenticate_ee()

    assert success is False
    assert "Virtual environment not found" in message
