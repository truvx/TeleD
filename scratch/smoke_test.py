"""Minimal Textual smoke test - bypasses Telegram auth entirely."""
import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Label
from textual.screen import Screen


class SmokeScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Label("✅ TeleD TUI is working! Press Q to quit.")
        yield Footer()
    
    def on_key(self, event) -> None:
        if event.key == "q":
            self.app.exit()


class SmokeApp(App):
    TITLE = "TeleD Smoke Test"
    def on_mount(self) -> None:
        self.push_screen(SmokeScreen())


if __name__ == "__main__":
    SmokeApp().run()
