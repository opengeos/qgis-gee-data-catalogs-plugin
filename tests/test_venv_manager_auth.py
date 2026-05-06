import sys
import types

from gee_data_catalogs.core import venv_manager


def test_authenticate_ee_falls_back_to_current_python(monkeypatch):
    calls = {}

    def fake_run(cmd, capture_output, text, timeout, env, **kwargs):
        calls["cmd"] = cmd
        calls["env"] = env
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(venv_manager, "venv_exists", lambda: False)
    monkeypatch.setattr(
        venv_manager.importlib.util,
        "find_spec",
        lambda name: object() if name == "ee" else None,
    )
    monkeypatch.setattr(venv_manager.subprocess, "run", fake_run)

    success, message = venv_manager.authenticate_ee()

    assert success is True
    assert "completed successfully" in message
    assert calls["cmd"][0] == sys.executable
    assert "PYTHONPATH" in calls["env"] or isinstance(calls["env"], dict)


def test_authenticate_ee_reports_missing_envs(monkeypatch):
    monkeypatch.setattr(venv_manager, "venv_exists", lambda: False)
    monkeypatch.setattr(venv_manager.importlib.util, "find_spec", lambda name: None)

    success, message = venv_manager.authenticate_ee()

    assert success is False
    assert "Virtual environment not found" in message
