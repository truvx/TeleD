from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Label, Button
from textual.containers import Vertical

class ErrorModal(ModalScreen):
    """A styled modal popup dialog for presenting errors gracefully to the user."""
    
    DEFAULT_CSS = """
    ErrorModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    
    #dialog {
        padding: 1 2;
        width: 60;
        height: auto;
        border: round red;
        background: $panel;
        layout: vertical;
    }
    
    #error-title {
        text-style: bold;
        color: red;
        margin-bottom: 1;
        height: 1;
    }
    
    #error-message {
        margin-bottom: 1;
        color: $text;
        height: auto;
    }
    
    #ok-btn {
        width: 100%;
        margin-top: 1;
    }
    """

    def __init__(self, title: str, message: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.error_title = title
        self.error_message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"⚠ {self.error_title}", id="error-title")
            yield Label(self.error_message, id="error-message")
            yield Button("OK", variant="error", id="ok-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()
