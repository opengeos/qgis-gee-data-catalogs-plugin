import sys
import types

from gee_data_catalogs.dialogs import chat_dock, settings_dock


class _FakeSettings:
    def __init__(self, values=None):
        self.values = values or {}

    def value(self, key, default="", type=str):  # noqa: A002
        return self.values.get(key, default)


class _CredentialHarness:
    SETTINGS_PREFIX = "GeeDataCatalogs/"

    def __init__(self, values=None):
        self.settings = _FakeSettings(values)


def test_openai_codex_is_default_provider():
    assert chat_dock.DEFAULT_PROVIDER == "openai-codex"
    assert "openai-codex" in chat_dock.PROVIDERS
    assert chat_dock.DEFAULT_MODELS["openai-codex"] == "gpt-5.5"
    assert settings_dock.DEFAULT_PROVIDER == "openai-codex"


def test_conversation_markdown_includes_full_history():
    markdown = chat_dock._conversation_markdown(
        [
            {"sender": "You", "body": "Find Sentinel-2 data"},
            {"sender": "GeoAgent", "body": "Use `COPERNICUS/S2_SR_HARMONIZED`."},
        ]
    )

    assert markdown == (
        "## You\n\nFind Sentinel-2 data\n\n"
        "## GeoAgent\n\nUse `COPERNICUS/S2_SR_HARMONIZED`."
    )


def test_extract_earth_engine_snippet_from_tool_metadata():
    snippet = "import ee\nimage = ee.Image('NASA/NASADEM_HGT/001')"
    tool_calls = [
        {
            "name": "load_gee_dataset",
            "result": {
                "content": [
                    {
                        "text": repr(
                            {
                                "success": True,
                                "earth_engine_python_snippet": snippet,
                            }
                        )
                    }
                ]
            },
        }
    ]

    assert chat_dock._extract_earth_engine_snippets(tool_calls) == [snippet]


def test_extract_python_code_block_fallback():
    answer = "Layer code:\n```python\nimport ee\nimage = ee.Image('A/B')\n```"

    assert chat_dock._extract_python_code_blocks(answer) == [
        "import ee\nimage = ee.Image('A/B')"
    ]


def test_credential_value_prefers_saved_setting_over_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    harness = _CredentialHarness({"GeeDataCatalogs/openai_api_key": "saved-key"})

    assert settings_dock.SettingsDockWidget._credential_value(
        harness, "openai_api_key"
    ) == ("saved-key", False)


def test_credential_value_falls_back_to_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    harness = _CredentialHarness()

    assert settings_dock.SettingsDockWidget._credential_value(
        harness, "openai_api_key"
    ) == ("env-key", True)


def test_apply_environment_keeps_existing_env_when_setting_empty(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "existing-key")

    chat_dock._apply_environment_from_settings(_FakeSettings())

    assert chat_dock.os.environ["OPENAI_API_KEY"] == "existing-key"


def test_confirm_tool_auto_approve_bypasses_confirmation(monkeypatch):
    class _MessageBox:
        @staticmethod
        def question(*_args, **_kwargs):
            raise AssertionError("confirmation dialog should not open")

    monkeypatch.setattr(chat_dock, "QMessageBox", _MessageBox)
    worker = chat_dock.ChatWorker(
        None, None, "prompt", "openai", "gpt-5.5", False, 4096, True
    )

    assert worker._confirm_tool(types.SimpleNamespace(args={}, tool_name="tool"))


def test_confirm_tool_uses_confirmation_when_auto_approve_is_off(monkeypatch):
    qt_marshal = types.ModuleType("geoagent.tools._qt_marshal")
    qt_marshal.run_on_qt_gui_thread = lambda callback: callback()
    monkeypatch.setitem(sys.modules, "geoagent", types.ModuleType("geoagent"))
    monkeypatch.setitem(
        sys.modules, "geoagent.tools", types.ModuleType("geoagent.tools")
    )
    monkeypatch.setitem(sys.modules, "geoagent.tools._qt_marshal", qt_marshal)

    class _StandardButton:
        Yes = 1
        No = 2

    class _MessageBox:
        StandardButton = _StandardButton

        @staticmethod
        def question(*_args, **_kwargs):
            return _StandardButton.No

    monkeypatch.setattr(chat_dock, "QMessageBox", _MessageBox)
    iface = types.SimpleNamespace(mainWindow=lambda: None)
    worker = chat_dock.ChatWorker(
        iface, None, "prompt", "openai", "gpt-5.5", False, 4096, False
    )
    request = types.SimpleNamespace(args={"asset_id": "LANDSAT/LC09"}, tool_name="load")

    assert not worker._confirm_tool(request)
