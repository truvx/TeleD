from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Label, Input, Button, Select, Switch
from textual.containers import Vertical, Horizontal, Grid
from tgdl.screens.error_modal import ErrorModal
import tgdl.database as db

class SettingsScreen(ModalScreen):
    """Full-featured Settings configuration screen for TeleD."""

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #settings-container {
        width: 70;
        height: auto;
        max-height: 90%;
        background: $panel;
        border: round $primary;
        padding: 1 2;
    }
    #settings-title {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
        content-align: center middle;
    }
    .field-label {
        color: $text;
        text-style: bold;
        margin-top: 1;
    }
    .setting-input {
        margin-bottom: 1;
    }
    #button-row {
        margin-top: 2;
        content-align: right middle;
    }
    Button {
        margin-left: 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.download_dir = ""
        self.theme = "textual-dark"
        self.concurrent = "3"
        self.resume = "true"
        self.retries = "5"
        self.cache_dir = ""
        self.session_path = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-container"):
            yield Label("⚙️ TeleD Configuration Settings", id="settings-title")
            
            yield Label("Download Directory:", classes="field-label")
            yield Input(placeholder="Target folder path", id="input-dl-dir", classes="setting-input")

            yield Label("UI Theme:", classes="field-label")
            yield Select([("Dark Theme", "textual-dark"), ("Light Theme", "textual-light")], id="select-theme", classes="setting-input")

            yield Label("Concurrent Downloads (1-10):", classes="field-label")
            yield Input(placeholder="Parallel downloads count", id="input-concurrent", classes="setting-input")

            yield Label("Resume Partial Downloads:", classes="field-label")
            yield Select([("Enabled", "true"), ("Disabled", "false")], id="select-resume", classes="setting-input")

            yield Label("Max Retry Count (1-10):", classes="field-label")
            yield Input(placeholder="Maximum retry attempts", id="input-retries", classes="setting-input")

            yield Label("Cache Location:", classes="field-label")
            yield Input(placeholder="SQLite database folder", id="input-cache", classes="setting-input")

            yield Label("Telegram Session Path:", classes="field-label")
            yield Input(placeholder="Session folder location", id="input-session", classes="setting-input")

            with Horizontal(id="button-row"):
                yield Button("Save", variant="primary", id="btn-save")
                yield Button("Cancel", variant="default", id="btn-cancel")

    async def on_mount(self) -> None:
        from tgdl.config import DOWNLOAD_DIR, CACHE_DIR, SESSION_DIR, CONCURRENT_DOWNLOADS
        self.download_dir = await db.get_setting("download_dir", DOWNLOAD_DIR)
        self.theme = await db.get_setting("theme", "textual-dark")
        self.concurrent = await db.get_setting("concurrent_downloads", str(CONCURRENT_DOWNLOADS))
        self.resume = await db.get_setting("resume_downloads", "true")
        self.retries = await db.get_setting("retry_count", "5")
        self.cache_dir = await db.get_setting("cache_dir", CACHE_DIR)
        self.session_path = await db.get_setting("session_path", SESSION_DIR)

        self.query_one("#input-dl-dir", Input).value = self.download_dir
        self.query_one("#select-theme", Select).value = self.theme
        self.query_one("#input-concurrent", Input).value = str(self.concurrent)
        self.query_one("#select-resume", Select).value = self.resume
        self.query_one("#input-retries", Input).value = str(self.retries)
        self.query_one("#input-cache", Input).value = self.cache_dir
        self.query_one("#input-session", Input).value = self.session_path

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss()
            return
        elif event.button.id == "btn-save":
            try:
                dl_dir = self.query_one("#input-dl-dir", Input).value.strip()
                theme_val = str(self.query_one("#select-theme", Select).value)
                conc_val = self.query_one("#input-concurrent", Input).value.strip()
                res_val = str(self.query_one("#select-resume", Select).value)
                ret_val = self.query_one("#input-retries", Input).value.strip()
                cache_val = self.query_one("#input-cache", Input).value.strip()
                sess_val = self.query_one("#input-session", Input).value.strip()

                if not conc_val.isdigit() or not (1 <= int(conc_val) <= 10):
                    self.app.push_screen(ErrorModal("Invalid Setting", "Concurrent downloads must be a number between 1 and 10."))
                    return
                if not ret_val.isdigit() or not (1 <= int(ret_val) <= 10):
                    self.app.push_screen(ErrorModal("Invalid Setting", "Retry count must be a number between 1 and 10."))
                    return

                await db.set_setting("download_dir", dl_dir)
                await db.set_setting("theme", theme_val)
                await db.set_setting("concurrent_downloads", conc_val)
                await db.set_setting("resume_downloads", res_val)
                await db.set_setting("retry_count", ret_val)
                await db.set_setting("cache_dir", cache_val)
                await db.set_setting("session_path", sess_val)

                self.app.theme = theme_val
                self.dismiss(True)
            except Exception as e:
                self.app.push_screen(ErrorModal("Settings Error", f"Failed to save settings: {e}"))
