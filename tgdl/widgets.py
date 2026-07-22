from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, ProgressBar
from textual.containers import Horizontal, Vertical
from tgdl.models import DownloadJob
from tgdl.utils.helpers import format_bytes, format_speed, format_eta

class DownloadProgressRow(Widget):
    """A custom widget displaying the progress of an active file download."""
    
    DEFAULT_CSS = """
    DownloadProgressRow {
        layout: vertical;
        background: $panel;
        border: tall $primary-muted;
        margin: 0 1 1 1;
        padding: 1;
        height: auto;
    }
    
    DownloadProgressRow .header {
        height: 1;
        margin-bottom: 0;
    }
    
    DownloadProgressRow .filename {
        text-style: bold;
        color: $text;
        width: 1fr;
    }
    
    DownloadProgressRow .status-badge {
        color: $accent;
        width: auto;
    }
    
    DownloadProgressRow ProgressBar {
        width: 100%;
        margin: 1 0;
        height: 1;
    }
    
    DownloadProgressRow .stats {
        height: 1;
        color: $text-muted;
        font-size: 85%;
    }
    """

    def __init__(self, job: DownloadJob, **kwargs) -> None:
        super().__init__(**kwargs)
        self.job = job

    def compose(self) -> ComposeResult:
        with Horizontal(classes="header"):
            yield Label(self.job.filename, classes="filename")
            yield Label(self.job.status.upper(), id="status-badge", classes="status-badge")
        yield ProgressBar(show_eta=False, show_percentage=True, id="progress-bar")
        yield Label("", id="stats-label", classes="stats")

    def on_mount(self) -> None:
        self.update_job(self.job)

    def update_job(self, job: DownloadJob) -> None:
        """Update the visual state of the progress row."""
        self.job = job
        
        # Update progress bar (0.0 to 100.0)
        try:
            pbar = self.query_one("#progress-bar", ProgressBar)
            pbar.progress = int(job.progress)
        except Exception:
            pass

        # Update status badge
        try:
            badge = self.query_one("#status-badge", Label)
            badge.update(job.status.upper())
            # Color active downloading accent, completed green, failed red
            if job.status == "completed":
                badge.styles.color = "green"
            elif job.status == "failed":
                badge.styles.color = "red"
            else:
                badge.styles.color = "$accent"
        except Exception:
            pass

        # Update stats text
        try:
            stats = self.query_one("#stats-label", Label)
            downloaded = format_bytes(job.downloaded_bytes)
            total = format_bytes(job.file_size)
            speed = format_speed(job.speed)
            eta = format_eta(job.eta)
            
            if job.status == "completed":
                text = f"Finished: {total}"
            elif job.status == "failed":
                text = "Download failed."
            elif job.status == "pending":
                text = f"Queued: {total}"
            else:
                text = f"{downloaded} / {total} | {speed} | ETA: {eta}"
            stats.update(text)
        except Exception:
            pass


class StatCard(Widget):
    """A simple widget to display a single metric in a styled block."""
    
    DEFAULT_CSS = """
    StatCard {
        background: $panel;
        border: solid $surface-lighten-2;
        padding: 1;
        height: 6;
        min-width: 15;
        margin: 0 1;
    }
    
    StatCard .title {
        color: $text-muted;
        font-size: 85%;
        text-style: uppercase;
        height: 1;
    }
    
    StatCard .value {
        color: $primary;
        text-style: bold;
        font-size: 130%;
        margin-top: 1;
        height: 2;
    }
    """

    def __init__(self, title: str, initial_value: str = "-", **kwargs) -> None:
        super().__init__(**kwargs)
        self.title = title
        self.val = initial_value

    def compose(self) -> ComposeResult:
        yield Label(self.title, classes="title")
        yield Label(self.val, id="stat-val", classes="value")

    def update_value(self, new_value: str) -> None:
        """Update the value displayed in the card."""
        self.val = new_value
        try:
            self.query_one("#stat-val", Label).update(new_value)
        except Exception:
            pass
