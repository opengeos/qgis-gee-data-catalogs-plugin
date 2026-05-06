from types import SimpleNamespace
from unittest.mock import MagicMock

import qgis.utils as qgis_utils

from gee_data_catalogs.gee_data_catalogs import GeeDataCatalogs


def test_ai_assistant_button_opens_loaded_open_geoagent(monkeypatch):
    plugin = SimpleNamespace(toggle_chat_dock=MagicMock(), _chat_dock=None)
    monkeypatch.setattr(qgis_utils, "plugins", {"open_geoagent": plugin}, raising=False)
    monkeypatch.setattr(qgis_utils, "available_plugins", [], raising=False)

    GeeDataCatalogs(MagicMock()).open_ai_assistant()

    plugin.toggle_chat_dock.assert_called_once_with()


def test_ai_assistant_button_raises_visible_open_geoagent_chat(monkeypatch):
    dock = MagicMock()
    dock.isVisible.return_value = True
    plugin = SimpleNamespace(toggle_chat_dock=MagicMock(), _chat_dock=dock)
    monkeypatch.setattr(qgis_utils, "plugins", {"open_geoagent": plugin}, raising=False)
    monkeypatch.setattr(qgis_utils, "available_plugins", [], raising=False)

    GeeDataCatalogs(MagicMock()).open_ai_assistant()

    dock.show.assert_called_once_with()
    dock.raise_.assert_called_once_with()
    plugin.toggle_chat_dock.assert_not_called()


def test_ai_assistant_button_prompts_install_when_open_geoagent_missing(monkeypatch):
    monkeypatch.setattr(qgis_utils, "plugins", {}, raising=False)
    monkeypatch.setattr(qgis_utils, "available_plugins", [], raising=False)

    plugin = GeeDataCatalogs(MagicMock())
    prompt = MagicMock()
    monkeypatch.setattr(plugin, "_prompt_open_geoagent_install", prompt)

    plugin.open_ai_assistant()

    prompt.assert_called_once_with()


def test_ai_assistant_button_loads_available_open_geoagent(monkeypatch):
    plugin = SimpleNamespace(toggle_chat_dock=MagicMock(), _chat_dock=None)

    def _load_plugin(package_name):
        assert package_name == "open_geoagent"

    def _start_plugin(package_name):
        assert package_name == "open_geoagent"
        qgis_utils.plugins = {"open_geoagent": plugin}

    monkeypatch.setattr(qgis_utils, "plugins", {}, raising=False)
    monkeypatch.setattr(
        qgis_utils, "available_plugins", ["open_geoagent"], raising=False
    )
    monkeypatch.setattr(qgis_utils, "active_plugins", [], raising=False)
    monkeypatch.setattr(qgis_utils, "loadPlugin", _load_plugin, raising=False)
    monkeypatch.setattr(qgis_utils, "startPlugin", _start_plugin, raising=False)

    GeeDataCatalogs(MagicMock()).open_ai_assistant()

    plugin.toggle_chat_dock.assert_called_once_with()
