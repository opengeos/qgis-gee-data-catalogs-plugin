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
