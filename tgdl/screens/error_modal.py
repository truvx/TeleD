from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Label, Button
from textual.containers import Vertical

class ErrorModal(ModalScreen):
    """A styled modal popup dialog for presenting errors, warnings, and notifications gracefully."""

    DEFAULT_CSS = """
    ErrorModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.75);
    }
    #dialog {
        padding: 1 2;
        width: 62;
        height: auto;
        border: round $accent;
        background: $panel;
        layout: vertical;
    }
    #dialog.variant-error { border: round red; }
    #dialog.variant-warning { border: round yellow; }
    #dialog.variant-info { border: round cyan; }
    
    #modal-title {
        text-style: bold;
        margin-bottom: 1;
        height: 1;
    }
    #modal-title.variant-error { color: red; }
    #modal-title.variant-warning { color: yellow; }
    #modal-title.variant-info { color: cyan; }
    
    #modal-message {
        margin-bottom: 1;
        color: $text;
        height: auto;
    }
    #ok-btn {
        width: 100%;
        margin-top: 1;
    }
    """

    def __init__(self, title: str, message: str, variant: str = "error", **kwargs) -> None:
        super().__init__(**kwargs)
        self.modal_title = title
        self.modal_message = message
        self.variant = variant.lower() if variant.lower() in ("error", "warning", "info") else "error"

    def compose(self) -> ComposeResult:
        icon_map = {"error": "⚠", "warning": "⚡", "info": "ℹ"}
        icon = icon_map.get(self.variant, "⚠")
        btn_variant_map = {"error": "error", "warning": "warning", "info": "primary"}
        btn_var = btn_variant_map.get(self.variant, "error")

        with Vertical(id="dialog", classes=f"variant-{self.variant}"):
            yield Label(f"{icon} {self.modal_title}", id="modal-title", classes=f"variant-{self.variant}")
            yield Label(self.modal_message, id="modal-message")
            yield Button("OK", variant=btn_var, id="ok-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()
