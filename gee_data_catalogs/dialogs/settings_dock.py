"""
Settings Dock Widget for GEE Data Catalogs

This module provides a settings panel for configuring plugin options.
"""

import os
import time

from qgis.PyQt.QtCore import Qt, QSettings, QThread, QUrl, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QGroupBox,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QFormLayout,
    QMessageBox,
    QTabWidget,
    QFileDialog,
    QProgressBar,
)
from qgis.PyQt.QtGui import QDesktopServices, QFont

from .chat_dock import DEFAULT_MODELS, DEFAULT_PROVIDER, PROVIDERS
from ..oauth import (
    CODEX_DEFAULT_CONFIG,
    OPENAI_CODEX_AUTH_EXTRA_PARAMS,
    OPENAI_CODEX_CALLBACK_PATH,
    OPENAI_CODEX_CALLBACK_PORT,
    clear_token_payload,
    store_token_payload,
)

try:
    import ee
except ImportError:
    ee = None

ENV_FALLBACKS = {
    "openai_api_key": ("OPENAI_API_KEY",),
    "anthropic_api_key": ("ANTHROPIC_API_KEY",),
    "gemini_api_key": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "aws_region": ("AWS_REGION", "AWS_DEFAULT_REGION"),
    "ollama_host": ("OLLAMA_HOST",),
    "litellm_api_key": ("LITELLM_API_KEY",),
    "litellm_base_url": ("LITELLM_BASE_URL",),
}


def _enum_value(cls, enum_name, member_name):
    """Return an enum member from either scoped or legacy Qt APIs."""
    container = getattr(cls, enum_name, cls)
    return getattr(container, member_name)


def _env_fallback(*env_names):
    """Return the first non-empty environment value from ``env_names``."""
    for env_name in env_names:
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    return ""


class OAuthLoginWorker(QThread):
    """Run an OpenAI OAuth login flow without blocking QGIS."""

    auth_url = pyqtSignal(str)
    finished = pyqtSignal(dict)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = dict(config)

    def run(self):
        """Open a loopback OAuth flow and exchange the callback code."""
        try:
            from ..oauth import complete_loopback_flow, start_loopback_flow

            is_codex = bool(self.config.get("codex"))
            flow = start_loopback_flow(
                self.config["authorization_url"],
                client_id=self.config["client_id"],
                scope=self.config.get("scope", ""),
                redirect_host="localhost" if is_codex else "127.0.0.1",
                port=OPENAI_CODEX_CALLBACK_PORT if is_codex else 0,
                callback_path=OPENAI_CODEX_CALLBACK_PATH if is_codex else "/callback",
                extra_params=OPENAI_CODEX_AUTH_EXTRA_PARAMS if is_codex else None,
                fallback_port=not is_codex,
            )
            self.auth_url.emit(flow.authorization_url)
            token = complete_loopback_flow(
                flow,
                token_url=self.config["token_url"],
                client_id=self.config["client_id"],
            )
            self.finished.emit({"success": True, "token": token, "error": ""})
        except Exception as exc:
            self.finished.emit({"success": False, "token": {}, "error": str(exc)})


class OAuthRefreshWorker(QThread):
    """Refresh OpenAI OAuth tokens without blocking QGIS."""

    finished = pyqtSignal(dict)

    def __init__(self, config, refresh_token, parent=None):
        super().__init__(parent)
        self.config = dict(config)
        self.refresh_token = refresh_token

    def run(self):
        """Refresh the OAuth token."""
        try:
            from ..oauth import refresh_oauth_token

            token = refresh_oauth_token(
                self.config["token_url"],
                client_id=self.config["client_id"],
                refresh_token=self.refresh_token,
                scope=self.config.get("scope", ""),
            )
            self.finished.emit({"success": True, "token": token, "error": ""})
        except Exception as exc:
            self.finished.emit({"success": False, "token": {}, "error": str(exc)})


class SettingsDockWidget(QDockWidget):
    """A settings panel for configuring plugin options."""

    auth_succeeded = pyqtSignal()
    settings_saved = pyqtSignal()

    # Settings keys
    SETTINGS_PREFIX = "GeeDataCatalogs/"

    def __init__(self, iface, parent=None):
        """Initialize the settings dock widget.

        Args:
            iface: QGIS interface instance.
            parent: Parent widget.
        """
        super().__init__("GEE Data Catalogs Settings", parent)
        self.iface = iface
        self.settings = QSettings()
        self._auth_worker = None
        self._oauth_worker = None
        self._env_sourced_credentials = {}

        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        """Set up the settings UI."""
        # Main widget
        main_widget = QWidget()
        self.setWidget(main_widget)

        # Main layout
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(10)

        # Header
        header_label = QLabel("Plugin Settings")
        header_font = QFont()
        header_font.setPointSize(12)
        header_font.setBold(True)
        header_label.setFont(header_font)
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header_label)

        # Tab widget for organized settings
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # General settings tab
        general_tab = self._create_general_tab()
        self.tab_widget.addTab(general_tab, "General")

        # Earth Engine tab
        ee_tab = self._create_ee_tab()
        self.tab_widget.addTab(ee_tab, "Earth Engine")

        # Display tab
        display_tab = self._create_display_tab()
        self.tab_widget.addTab(display_tab, "Display")

        model_tab = self._create_model_tab()
        self.tab_widget.addTab(model_tab, "Model")

        # Buttons
        button_layout = QHBoxLayout()

        self.save_btn = QPushButton("Save Settings")
        self.save_btn.clicked.connect(self._save_settings)
        button_layout.addWidget(self.save_btn)

        self.reset_btn = QPushButton("Reset Defaults")
        self.reset_btn.clicked.connect(self._reset_defaults)
        button_layout.addWidget(self.reset_btn)

        layout.addLayout(button_layout)

        # Stretch at the end
        layout.addStretch()

        # Status label
        self.status_label = QLabel("Settings loaded")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.status_label)

    def show_ee_tab(self):
        """Switch to the Earth Engine tab and focus the project ID input."""
        self.tab_widget.setCurrentIndex(1)
        self.ee_project_input.setFocus()

    def _create_general_tab(self):
        """Create the general settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # General options group
        general_group = QGroupBox("General Options")
        general_layout = QFormLayout(general_group)

        # Auto-initialize EE
        self.auto_init_check = QCheckBox()
        self.auto_init_check.setChecked(True)
        general_layout.addRow("Auto-initialize Earth Engine:", self.auto_init_check)

        # Show notifications
        self.notifications_check = QCheckBox()
        self.notifications_check.setChecked(True)
        general_layout.addRow("Show notifications:", self.notifications_check)

        # Default category (aligned with official GEE categories)
        self.default_category = QComboBox()
        self.default_category.addItems(
            [
                "Agriculture",
                "Atmosphere",
                "Climate",
                "Cryosphere",
                "Ecosystems",
                "Elevation & Topography",
                "Fire",
                "Forest & Biomass",
                "Infrastructure & Boundaries",
                "Land Use & Land Cover",
                "Oceans",
                "Orthophotos",
                "Plant Productivity",
                "Population",
                "Precipitation",
                "Satellite Imagery",
                "Soil",
                "Surface & Ground Water",
                "Vegetation Indices",
                "Water Vapor",
                "Other",
            ]
        )
        general_layout.addRow("Default category:", self.default_category)

        layout.addWidget(general_group)

        # Cache options
        cache_group = QGroupBox("Cache")
        cache_layout = QFormLayout(cache_group)

        self.cache_enabled = QCheckBox()
        self.cache_enabled.setChecked(True)
        cache_layout.addRow("Enable catalog cache:", self.cache_enabled)

        self.cache_duration = QSpinBox()
        self.cache_duration.setRange(1, 168)  # 1 hour to 1 week
        self.cache_duration.setValue(24)
        self.cache_duration.setSuffix(" hours")
        cache_layout.addRow("Cache duration:", self.cache_duration)

        layout.addWidget(cache_group)

        layout.addStretch()
        return widget

    def _create_ee_tab(self):
        """Create the Earth Engine settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Project settings
        project_group = QGroupBox("Earth Engine Project")
        project_layout = QFormLayout(project_group)

        self.ee_project_input = QLineEdit()
        self.ee_project_input.setPlaceholderText("Enter GCP project ID...")
        project_layout.addRow("Project ID:", self.ee_project_input)

        info_label = QLabel(
            "<small>Leave empty to use EE_PROJECT_ID environment variable.<br>"
            "Set the project ID if auto-initialization fails.</small>"
        )
        info_label.setWordWrap(True)
        project_layout.addRow("", info_label)

        cred_layout = QHBoxLayout()
        self.credentials_input = QLineEdit()
        self.credentials_input.setPlaceholderText("Optional path to credentials JSON")
        cred_layout.addWidget(self.credentials_input)
        self.browse_cred_btn = QPushButton("...")
        self.browse_cred_btn.setMaximumWidth(30)
        self.browse_cred_btn.clicked.connect(self._browse_credentials)
        cred_layout.addWidget(self.browse_cred_btn)
        project_layout.addRow("Credentials:", cred_layout)

        layout.addWidget(project_group)

        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout(actions_group)

        auth_btn = QPushButton("Authenticate (opens browser)")
        auth_btn.clicked.connect(self._authenticate_ee)
        actions_layout.addWidget(auth_btn)

        init_btn = QPushButton("Initialize Earth Engine")
        init_btn.clicked.connect(self._initialize_ee)
        actions_layout.addWidget(init_btn)

        self.ee_status_label = QLabel("Status: Not initialized")
        self.ee_status_label.setStyleSheet("color: gray;")
        self.ee_status_label.setWordWrap(True)
        actions_layout.addWidget(self.ee_status_label)

        self.ee_progress_bar = QProgressBar()
        self.ee_progress_bar.setVisible(False)
        actions_layout.addWidget(self.ee_progress_bar)

        layout.addWidget(actions_group)

        # Default filters
        filters_group = QGroupBox("Default Filters")
        filters_layout = QFormLayout(filters_group)

        self.default_cloud_cover = QSpinBox()
        self.default_cloud_cover.setRange(0, 100)
        self.default_cloud_cover.setValue(20)
        self.default_cloud_cover.setSuffix("%")
        filters_layout.addRow("Default max cloud cover:", self.default_cloud_cover)

        self.default_date_range = QSpinBox()
        self.default_date_range.setRange(1, 365 * 10)
        self.default_date_range.setValue(365)
        self.default_date_range.setSuffix(" days")
        filters_layout.addRow("Default date range:", self.default_date_range)

        layout.addWidget(filters_group)

        # Performance
        perf_group = QGroupBox("Performance")
        perf_layout = QFormLayout(perf_group)

        self.max_features = QSpinBox()
        self.max_features.setRange(100, 50000)
        self.max_features.setValue(5000)
        perf_layout.addRow("Max features to load:", self.max_features)

        self.tile_size = QComboBox()
        self.tile_size.addItems(["256", "512", "1024"])
        self.tile_size.setCurrentText("256")
        perf_layout.addRow("Tile size:", self.tile_size)

        layout.addWidget(perf_group)

        layout.addStretch()
        return widget

    def _create_display_tab(self):
        """Create the display settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Layer options
        layer_group = QGroupBox("Layer Options")
        layer_layout = QFormLayout(layer_group)

        self.default_opacity = QDoubleSpinBox()
        self.default_opacity.setRange(0.0, 1.0)
        self.default_opacity.setValue(1.0)
        self.default_opacity.setSingleStep(0.1)
        layer_layout.addRow("Default layer opacity:", self.default_opacity)

        self.add_to_top = QCheckBox()
        self.add_to_top.setChecked(True)
        layer_layout.addRow("Add layers to top:", self.add_to_top)

        self.auto_zoom = QCheckBox()
        self.auto_zoom.setChecked(False)
        layer_layout.addRow("Auto-zoom to layer extent:", self.auto_zoom)

        layout.addWidget(layer_group)

        # Visualization defaults
        vis_group = QGroupBox("Visualization Defaults")
        vis_layout = QFormLayout(vis_group)

        self.default_palette = QComboBox()
        self.default_palette.addItems(
            [
                "viridis",
                "terrain",
                "inferno",
                "plasma",
                "magma",
                "cividis",
                "coolwarm",
                "spectral",
            ]
        )
        vis_layout.addRow("Default color palette:", self.default_palette)

        self.stretch_type = QComboBox()
        self.stretch_type.addItems(["Linear", "Histogram Equalization", "Min-Max"])
        vis_layout.addRow("Default stretch:", self.stretch_type)

        layout.addWidget(vis_group)

        layout.addStretch()
        return widget

    def _create_model_tab(self):
        """Create the AI model settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        model_group = QGroupBox("AI Provider")
        form = QFormLayout(model_group)

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(PROVIDERS)
        self.provider_combo.setMinimumContentsLength(10)
        self.provider_combo.setSizeAdjustPolicy(
            _enum_value(
                QComboBox,
                "SizeAdjustPolicy",
                "AdjustToMinimumContentsLengthWithIcon",
            )
        )
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        form.addRow("Provider:", self.provider_combo)

        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("Provider default")
        form.addRow("Model:", self.model_input)

        self.fast_check = QCheckBox("Use fast GeoAgent prompt")
        form.addRow("", self.fast_check)

        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(256, 32768)
        self.max_tokens_spin.setValue(4096)
        self.max_tokens_spin.setSingleStep(256)
        form.addRow("Max tokens:", self.max_tokens_spin)

        layout.addWidget(model_group)

        credentials_group = QGroupBox("Credentials and Hosts")
        credentials_form = QFormLayout(credentials_group)

        password_mode = getattr(getattr(QLineEdit, "EchoMode", QLineEdit), "Password")

        self.openai_key_input = QLineEdit()
        self.openai_key_input.setEchoMode(password_mode)
        credentials_form.addRow("OpenAI API key:", self.openai_key_input)

        self.anthropic_key_input = QLineEdit()
        self.anthropic_key_input.setEchoMode(password_mode)
        credentials_form.addRow("Anthropic API key:", self.anthropic_key_input)

        self.gemini_key_input = QLineEdit()
        self.gemini_key_input.setEchoMode(password_mode)
        credentials_form.addRow("Gemini API key:", self.gemini_key_input)

        self.aws_region_input = QLineEdit()
        self.aws_region_input.setPlaceholderText("e.g. us-east-1")
        credentials_form.addRow("AWS region:", self.aws_region_input)

        self.ollama_host_input = QLineEdit()
        self.ollama_host_input.setPlaceholderText("http://127.0.0.1:11434")
        credentials_form.addRow("Ollama host:", self.ollama_host_input)

        self.litellm_key_input = QLineEdit()
        self.litellm_key_input.setEchoMode(password_mode)
        credentials_form.addRow("LiteLLM API key:", self.litellm_key_input)

        self.litellm_base_url_input = QLineEdit()
        self.litellm_base_url_input.setPlaceholderText("https://proxy.example.com")
        credentials_form.addRow("LiteLLM base URL:", self.litellm_base_url_input)

        layout.addWidget(credentials_group)
        self._credential_inputs = (
            ("openai_api_key", self.openai_key_input),
            ("anthropic_api_key", self.anthropic_key_input),
            ("gemini_api_key", self.gemini_key_input),
            ("aws_region", self.aws_region_input),
            ("ollama_host", self.ollama_host_input),
            ("litellm_api_key", self.litellm_key_input),
            ("litellm_base_url", self.litellm_base_url_input),
        )

        oauth_group = QGroupBox("ChatGPT Login")
        oauth_form = QFormLayout(oauth_group)

        oauth_note = QLabel(
            "Login opens ChatGPT in your browser using the Codex OAuth flow."
        )
        oauth_note.setWordWrap(True)
        oauth_note.setStyleSheet("font-size: 10px; color: gray;")
        oauth_form.addRow(oauth_note)

        oauth_button_layout = QHBoxLayout()
        self.openai_oauth_login_btn = QPushButton("Login with ChatGPT")
        self.openai_oauth_login_btn.clicked.connect(self._login_openai_oauth)
        oauth_button_layout.addWidget(self.openai_oauth_login_btn)

        self.openai_oauth_refresh_btn = QPushButton("Refresh")
        self.openai_oauth_refresh_btn.clicked.connect(self._refresh_openai_oauth)
        oauth_button_layout.addWidget(self.openai_oauth_refresh_btn)

        self.openai_oauth_logout_btn = QPushButton("Logout")
        self.openai_oauth_logout_btn.clicked.connect(self._logout_openai_oauth)
        oauth_button_layout.addWidget(self.openai_oauth_logout_btn)
        oauth_form.addRow("", oauth_button_layout)

        self.openai_oauth_status_label = QLabel("Not logged in")
        self.openai_oauth_status_label.setWordWrap(True)
        self.openai_oauth_status_label.setStyleSheet("font-size: 10px; color: gray;")
        oauth_form.addRow("Status:", self.openai_oauth_status_label)

        layout.addWidget(oauth_group)

        note = QLabel(
            "Credential values are saved in QGIS settings and applied to the "
            "current QGIS process when the AI assistant runs."
        )
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 10px; color: gray;")
        layout.addWidget(note)
        layout.addStretch()
        return widget

    def _browse_credentials(self):
        """Open file browser for an optional credentials JSON file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Credentials File",
            "",
            "JSON Files (*.json);;All Files (*)",
        )
        if file_path:
            self.credentials_input.setText(file_path)

    def _get_ee_module(self):
        """Return the Earth Engine module, re-importing after installs if needed."""
        global ee
        if ee is None:
            try:
                import ee as _ee

                ee = _ee
            except ImportError:
                return None
        return ee

    def _initialize_ee(self):
        """Initialize and verify Earth Engine with current settings."""
        ee_module = self._get_ee_module()
        if ee_module is None:
            QMessageBox.warning(
                self,
                "Warning",
                "Earth Engine API not installed.\n\nPlease install earthengine-api.",
            )
            return

        project = self.ee_project_input.text().strip()
        if not project:
            project = os.environ.get("EE_PROJECT_ID", "")

        if not project:
            QMessageBox.warning(
                self,
                "Project ID Required",
                "A Google Cloud project ID is required to initialize "
                "Earth Engine.\n\nPlease enter your project ID above.",
            )
            self.ee_project_input.setFocus()
            return

        try:
            cred_file = self.credentials_input.text().strip()
            credentials = None

            if cred_file:
                from google.oauth2 import service_account

                credentials = service_account.Credentials.from_service_account_file(
                    cred_file,
                    scopes=["https://www.googleapis.com/auth/earthengine"],
                )

            if credentials is not None:
                ee_module.Initialize(credentials=credentials, project=project)
            else:
                ee_module.Initialize(project=project)
        except Exception as e:
            self.ee_status_label.setText("Status: Error")
            self.ee_status_label.setStyleSheet("color: red;")
            QMessageBox.critical(
                self,
                "Initialization Error",
                f"Failed to initialize Earth Engine:\n\n{str(e)}",
            )
            return

        try:
            ee_module.Number(1).getInfo()
        except Exception as e:
            self.ee_status_label.setText("Status: Error")
            self.ee_status_label.setStyleSheet("color: red;")
            QMessageBox.critical(
                self,
                "Earth Engine Verification Failed",
                "Initialize succeeded but a test request failed:\n\n"
                f"{str(e)}\n\n"
                "Common causes: the Earth Engine API is not enabled for "
                f"project '{project}', the account is not registered, or "
                "the credentials are missing the required scopes.",
            )
            return

        from ..core.ee_utils import mark_ee_initialized

        mark_ee_initialized(True)

        self.ee_status_label.setText("Status: Initialized & verified")
        self.ee_status_label.setStyleSheet("color: green; font-weight: bold;")
        self.iface.messageBar().pushSuccess(
            "GEE Data Catalogs", "Earth Engine initialized successfully!"
        )

    def _authenticate_ee(self):
        """Start Earth Engine authentication in the background."""
        from .deps_manager import EEAuthWorker

        if self._auth_worker is not None and self._auth_worker.isRunning():
            return

        self.ee_status_label.setText(
            "Authenticating... A browser window should open.\n"
            "Complete the sign-in and return here."
        )
        self.ee_status_label.setStyleSheet("color: blue;")
        self.ee_progress_bar.setVisible(True)
        self.ee_progress_bar.setRange(0, 0)

        self._auth_worker = EEAuthWorker()
        self._auth_worker.progress.connect(self._on_auth_progress)
        self._auth_worker.finished.connect(self._on_auth_finished)
        self._auth_worker.start()

    def _on_auth_progress(self, percent: int, message: str):
        """Handle Earth Engine auth progress updates."""
        self.ee_status_label.setText(message)

    def _on_auth_finished(self, success: bool, message: str):
        """Handle Earth Engine authentication completion."""
        self._auth_worker = None
        self.ee_progress_bar.setVisible(False)
        self.ee_progress_bar.setRange(0, 100)

        if success:
            self.ee_status_label.setText("Status: Credentials found")
            self.ee_status_label.setStyleSheet("color: green; font-weight: bold;")
            self.iface.messageBar().pushSuccess(
                "GEE Data Catalogs",
                "Earth Engine authenticated successfully!",
            )
            self.auth_succeeded.emit()
        else:
            self.ee_status_label.setText(f"Authentication failed: {message[:150]}")
            self.ee_status_label.setStyleSheet("color: red;")

    def _oauth_config(self):
        """Return the built-in ChatGPT/Codex login settings."""
        config = dict(CODEX_DEFAULT_CONFIG)
        config["codex"] = True
        return config

    def _set_oauth_buttons_enabled(self, enabled):
        """Enable or disable OAuth action buttons."""
        self.openai_oauth_login_btn.setEnabled(enabled)
        self.openai_oauth_refresh_btn.setEnabled(enabled)
        self.openai_oauth_logout_btn.setEnabled(enabled)

    def _login_openai_oauth(self):
        """Start OpenAI OAuth login."""
        if self._oauth_worker is not None:
            return
        try:
            config = self._oauth_config()
        except Exception as exc:
            QMessageBox.warning(self, "ChatGPT Login", str(exc))
            return

        self.openai_oauth_status_label.setText("Waiting for browser login...")
        self.openai_oauth_status_label.setStyleSheet("font-size: 10px; color: #1976D2;")
        self._set_oauth_buttons_enabled(False)
        self._oauth_worker = OAuthLoginWorker(config, self)
        self._oauth_worker.auth_url.connect(self._open_oauth_browser)
        self._oauth_worker.finished.connect(self._on_oauth_worker_finished)
        self._oauth_worker.start()

    def _refresh_openai_oauth(self):
        """Refresh the stored OpenAI OAuth token."""
        if self._oauth_worker is not None:
            return
        try:
            config = self._oauth_config()
            from ..oauth import load_token_payload

            payload = load_token_payload(self.settings)
            refresh_token = str(payload.get("refresh_token", "")).strip()
            if not refresh_token:
                raise ValueError("No refresh token is stored. Login again.")
        except Exception as exc:
            QMessageBox.warning(self, "ChatGPT Login", str(exc))
            return

        self.openai_oauth_status_label.setText("Refreshing token...")
        self.openai_oauth_status_label.setStyleSheet("font-size: 10px; color: #1976D2;")
        self._set_oauth_buttons_enabled(False)
        self._oauth_worker = OAuthRefreshWorker(config, refresh_token, self)
        self._oauth_worker.finished.connect(self._on_oauth_worker_finished)
        self._oauth_worker.start()

    def _logout_openai_oauth(self):
        """Clear stored OpenAI OAuth tokens."""
        try:
            clear_token_payload(self.settings)
        except Exception as exc:
            QMessageBox.warning(self, "ChatGPT Login", str(exc))
            return
        self._refresh_oauth_status()
        self.iface.messageBar().pushSuccess("GEE Data Catalogs", "ChatGPT logged out.")

    def _open_oauth_browser(self, url):
        """Open the OAuth authorization URL in the user's browser."""
        QDesktopServices.openUrl(QUrl(url))

    def _on_oauth_worker_finished(self, result):
        """Persist OAuth tokens from the login or refresh worker."""
        self._set_oauth_buttons_enabled(True)
        self._oauth_worker = None
        if not result.get("success"):
            self.openai_oauth_status_label.setText("Login failed")
            self.openai_oauth_status_label.setStyleSheet("font-size: 10px; color: red;")
            QMessageBox.critical(self, "ChatGPT Login", result.get("error", "Failed"))
            return
        try:
            store_token_payload(self.settings, result["token"])
            index = self.provider_combo.findText("openai-codex")
            if index >= 0:
                self.provider_combo.setCurrentIndex(index)
                self.settings.setValue(
                    f"{self.SETTINGS_PREFIX}provider", "openai-codex"
                )
                model = self.model_input.text().strip() or DEFAULT_MODELS.get(
                    "openai-codex", ""
                )
                if model:
                    self.model_input.setText(model)
                    self.settings.setValue(f"{self.SETTINGS_PREFIX}model", model)
        except Exception as exc:
            self.openai_oauth_status_label.setText("Token storage failed")
            self.openai_oauth_status_label.setStyleSheet("font-size: 10px; color: red;")
            QMessageBox.critical(self, "ChatGPT Login", str(exc))
            return
        self._refresh_oauth_status()
        self.iface.messageBar().pushSuccess("GEE Data Catalogs", "ChatGPT connected.")

    def _refresh_oauth_status(self):
        """Update the OAuth login status label."""
        authcfg = self.settings.value(f"{self.SETTINGS_PREFIX}openai_oauth_authcfg", "")
        expires_at = self.settings.value(
            f"{self.SETTINGS_PREFIX}openai_oauth_expires_at", "", type=str
        )
        if not str(authcfg).strip():
            self.openai_oauth_status_label.setText("Not logged in")
            self.openai_oauth_status_label.setStyleSheet(
                "font-size: 10px; color: gray;"
            )
            return
        if expires_at:
            try:
                expiry = time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    time.localtime(float(expires_at)),
                )
                text = f"Logged in. Access token expires at {expiry}."
            except (TypeError, ValueError):
                text = "Logged in. Access token expiry is unknown."
        else:
            text = "Logged in. Access token expiry is unknown."
        self.openai_oauth_status_label.setText(text)
        self.openai_oauth_status_label.setStyleSheet("font-size: 10px; color: green;")

    def _on_provider_changed(self, provider):
        """Update the model field when the provider changes."""
        self.model_input.setText(DEFAULT_MODELS.get(provider, ""))

    def _credential_value(self, key):
        """Return ``(value, from_env)`` for a credential field."""
        saved = self.settings.value(f"{self.SETTINGS_PREFIX}{key}", "", type=str)
        if str(saved).strip():
            return str(saved), False
        fallback = _env_fallback(*ENV_FALLBACKS.get(key, ()))
        return fallback, bool(fallback)

    def _load_settings(self):
        """Load settings from QSettings."""
        # General
        self.auto_init_check.setChecked(
            self.settings.value(f"{self.SETTINGS_PREFIX}auto_init", True, type=bool)
        )
        self.notifications_check.setChecked(
            self.settings.value(f"{self.SETTINGS_PREFIX}notifications", True, type=bool)
        )
        self.default_category.setCurrentIndex(
            self.settings.value(f"{self.SETTINGS_PREFIX}default_category", 0, type=int)
        )
        self.cache_enabled.setChecked(
            self.settings.value(f"{self.SETTINGS_PREFIX}cache_enabled", True, type=bool)
        )
        self.cache_duration.setValue(
            self.settings.value(f"{self.SETTINGS_PREFIX}cache_duration", 24, type=int)
        )

        # Earth Engine
        self.ee_project_input.setText(
            self.settings.value(f"{self.SETTINGS_PREFIX}ee_project", "", type=str)
        )
        self.credentials_input.setText(
            self.settings.value(f"{self.SETTINGS_PREFIX}credentials", "", type=str)
        )
        self.default_cloud_cover.setValue(
            self.settings.value(
                f"{self.SETTINGS_PREFIX}default_cloud_cover", 20, type=int
            )
        )
        self.default_date_range.setValue(
            self.settings.value(
                f"{self.SETTINGS_PREFIX}default_date_range", 365, type=int
            )
        )
        self.max_features.setValue(
            self.settings.value(f"{self.SETTINGS_PREFIX}max_features", 5000, type=int)
        )
        tile_size_index = self.tile_size.findText(
            self.settings.value(f"{self.SETTINGS_PREFIX}tile_size", "256", type=str)
        )
        if tile_size_index >= 0:
            self.tile_size.setCurrentIndex(tile_size_index)

        # Display
        self.default_opacity.setValue(
            self.settings.value(
                f"{self.SETTINGS_PREFIX}default_opacity", 1.0, type=float
            )
        )
        self.add_to_top.setChecked(
            self.settings.value(f"{self.SETTINGS_PREFIX}add_to_top", True, type=bool)
        )
        self.auto_zoom.setChecked(
            self.settings.value(f"{self.SETTINGS_PREFIX}auto_zoom", False, type=bool)
        )
        self.default_palette.setCurrentIndex(
            self.settings.value(f"{self.SETTINGS_PREFIX}default_palette", 0, type=int)
        )
        self.stretch_type.setCurrentIndex(
            self.settings.value(f"{self.SETTINGS_PREFIX}stretch_type", 0, type=int)
        )

        # AI model
        provider = self.settings.value(
            f"{self.SETTINGS_PREFIX}provider", DEFAULT_PROVIDER, type=str
        )
        provider_index = self.provider_combo.findText(provider)
        if provider_index < 0:
            provider_index = self.provider_combo.findText(DEFAULT_PROVIDER)
        self.provider_combo.setCurrentIndex(
            provider_index if provider_index >= 0 else 0
        )
        effective_provider = self.provider_combo.currentText()
        model = self.settings.value(f"{self.SETTINGS_PREFIX}model", "", type=str)
        self.model_input.setText(model or DEFAULT_MODELS.get(effective_provider, ""))
        self.fast_check.setChecked(
            self.settings.value(f"{self.SETTINGS_PREFIX}fast_mode", False, type=bool)
        )
        self.max_tokens_spin.setValue(
            self.settings.value(f"{self.SETTINGS_PREFIX}max_tokens", 4096, type=int)
        )
        self._env_sourced_credentials = {}
        for key, widget in self._credential_inputs:
            value, from_env = self._credential_value(key)
            widget.setText(value)
            if from_env:
                self._env_sourced_credentials[key] = value

        self._refresh_oauth_status()

        self.status_label.setText("Settings loaded")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")

    def _save_settings(self):
        """Save settings to QSettings."""
        # General
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}auto_init", self.auto_init_check.isChecked()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}notifications", self.notifications_check.isChecked()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}default_category",
            self.default_category.currentIndex(),
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}cache_enabled", self.cache_enabled.isChecked()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}cache_duration", self.cache_duration.value()
        )

        # Earth Engine
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}ee_project", self.ee_project_input.text()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}credentials", self.credentials_input.text()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}default_cloud_cover",
            self.default_cloud_cover.value(),
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}default_date_range", self.default_date_range.value()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}max_features", self.max_features.value()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}tile_size", self.tile_size.currentText()
        )

        # Display
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}default_opacity", self.default_opacity.value()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}add_to_top", self.add_to_top.isChecked()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}auto_zoom", self.auto_zoom.isChecked()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}default_palette",
            self.default_palette.currentIndex(),
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}stretch_type", self.stretch_type.currentIndex()
        )

        # AI model
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}provider", self.provider_combo.currentText()
        )
        self.settings.setValue(f"{self.SETTINGS_PREFIX}model", self.model_input.text())
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}fast_mode", self.fast_check.isChecked()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}max_tokens", self.max_tokens_spin.value()
        )
        for key, widget in self._credential_inputs:
            current = widget.text()
            env_value = self._env_sourced_credentials.get(key)
            if env_value is not None and current == env_value:
                continue
            self.settings.setValue(f"{self.SETTINGS_PREFIX}{key}", current)

        self.settings.sync()

        self.status_label.setText("Settings saved")
        self.status_label.setStyleSheet("color: green; font-size: 10px;")

        self.iface.messageBar().pushSuccess(
            "GEE Data Catalogs", "Settings saved successfully!"
        )
        self.settings_saved.emit()

    def _reset_defaults(self):
        """Reset all settings to defaults."""
        reply = QMessageBox.question(
            self,
            "Reset Settings",
            "Are you sure you want to reset all settings to defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            clear_token_payload(self.settings)
        except Exception as exc:
            QMessageBox.warning(self, "ChatGPT Login", str(exc))
            return

        # General
        self.auto_init_check.setChecked(True)
        self.notifications_check.setChecked(True)
        self.default_category.setCurrentIndex(0)
        self.cache_enabled.setChecked(True)
        self.cache_duration.setValue(24)

        # Earth Engine
        self.ee_project_input.clear()
        self.credentials_input.clear()
        self.default_cloud_cover.setValue(20)
        self.default_date_range.setValue(365)
        self.max_features.setValue(5000)
        self.tile_size.setCurrentText("256")

        # Display
        self.default_opacity.setValue(1.0)
        self.add_to_top.setChecked(True)
        self.auto_zoom.setChecked(False)
        self.default_palette.setCurrentIndex(0)
        self.stretch_type.setCurrentIndex(0)

        # AI model
        self.provider_combo.setCurrentText(DEFAULT_PROVIDER)
        self.model_input.setText(DEFAULT_MODELS[DEFAULT_PROVIDER])
        self.fast_check.setChecked(False)
        self.max_tokens_spin.setValue(4096)
        self.openai_key_input.clear()
        self.anthropic_key_input.clear()
        self.gemini_key_input.clear()
        self.aws_region_input.clear()
        self.ollama_host_input.clear()
        self.litellm_key_input.clear()
        self.litellm_base_url_input.clear()
        self._env_sourced_credentials = {}
        self._refresh_oauth_status()

        self.status_label.setText("Defaults restored (not saved)")
        self.status_label.setStyleSheet("color: orange; font-size: 10px;")
