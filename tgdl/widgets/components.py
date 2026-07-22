from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label
from textual.containers import Horizontal
from tgdl.models import DownloadJob
from tgdl.utils.helpers import format_bytes, format_speed, format_eta

def make_ascii_bar(percentage: float, width: int = 20) -> str:
    p = max(0.0, min(100.0, percentage))
    filled = int(width * (p / 100.0))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)

class DownloadProgressRow(Widget):
    """A custom widget displaying the progress of an active file download."""
    
    DEFAULT_CSS = """
    DownloadProgressRow {
        layout: vertical;
        background: $surface;
        border: round $primary;
        margin: 0 0 1 0;
        padding: 0 1;
        height: auto;
    }
    
    DownloadProgressRow:hover {
        border: round $accent;
    }

    DownloadProgressRow .header {
        height: 1;
        margin-top: 0;
        margin-bottom: 0;
    }
    
    DownloadProgressRow .filename {
        text-style: bold;
        color: $text;
        width: 1fr;
    }
    
    DownloadProgressRow .status-badge {
        color: $accent;
        text-style: bold;
        width: auto;
    }

    DownloadProgressRow .progress-text {
        height: 1;
        color: $accent-lighten-2;
        text-style: bold;
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
        yield Label("", id="progress-text-label", classes="progress-text")
        yield Label("", id="stats-label", classes="stats")

    def on_mount(self) -> None:
        self.update_job(self.job)

    def update_job(self, job: DownloadJob) -> None:
        self.job = job
        
        try:
            badge = self.query_one("#status-badge", Label)
            badge.update(job.status.upper())
            if job.status == "completed":
                badge.styles.color = "green"
            elif "failed" in job.status:
                badge.styles.color = "red"
            else:
                badge.styles.color = "$accent"
        except Exception:
            pass

        try:
            p_label = self.query_one("#progress-text-label", Label)
            bar = make_ascii_bar(job.progress, width=22)
            pct = int(job.progress)
            downloaded = format_bytes(job.downloaded_bytes)
            total = format_bytes(job.file_size)
            speed = format_speed(job.speed)
            eta = format_eta(job.eta)
            
            p_text = f"{bar}  {pct}%  │  {downloaded} / {total}  │  {speed}  │  ETA {eta}"
            p_label.update(p_text)
        except Exception:
            pass

        try:
            stats = self.query_one("#stats-label", Label)
            if job.status == "completed":
                text = f"✓ Completed: {format_bytes(job.file_size)}"
            elif "failed" in job.status:
                text = f"✗ Failed: {job.error_msg or 'Max retries exceeded'}"
            elif "retry" in job.status:
                text = f"⚠ Retrying download... ({job.status})"
            elif job.status == "pending":
                text = f"⏳ Queued: {format_bytes(job.file_size)}"
            else:
                text = f"Bytes: {job.downloaded_bytes} / {job.file_size}"
            stats.update(text)
        except Exception:
            pass


class StatCard(Widget):
    """A metric card with clean LazyGit borders."""
    
    DEFAULT_CSS = """
    StatCard {
        background: $panel;
        border: round $primary-muted;
        padding: 0 1;
        height: 4;
        min-width: 14;
        margin: 0 1;
    }
    
    StatCard:hover {
        border: round $accent;
    }

    StatCard .title {
        color: $text-muted;
        font-size: 80%;
        text-style: uppercase;
        height: 1;
    }
    
    StatCard .value {
        color: $accent;
        text-style: bold;
        font-size: 110%;
        height: 1;
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
        self.val = new_value
        try:
            self.query_one("#stat-val", Label).update(new_value)
        except Exception:
            pass


class CounterBar(Widget):
    """Bottom status bar displaying selection count, selected size, downloaded, and queue counts."""

    DEFAULT_CSS = """
    CounterBar {
        layout: horizontal;
        background: $surface;
        border-top: solid $primary-muted;
        height: 1;
        padding: 0 1;
        color: $text;
    }
    
    CounterBar .item {
        margin-right: 2;
        text-style: bold;
    }
    """

    def __init__(self, selected: int = 0, selected_bytes: int = 0, downloaded: int = 0, queue: int = 0, **kwargs) -> None:
        super().__init__(**kwargs)
        self.selected = selected
        self.selected_bytes = selected_bytes
        self.downloaded = downloaded
        self.queue = queue

    def compose(self) -> ComposeResult:
        yield Label(f"Selected: {self.selected} ({format_bytes(self.selected_bytes)})", id="cnt-selected", classes="item")
        yield Label(f"Downloaded: {self.downloaded}", id="cnt-downloaded", classes="item")
        yield Label(f"Queue: {self.queue}", id="cnt-queue", classes="item")

    def update_counts(self, selected: int, selected_bytes: int, downloaded: int, queue: int) -> None:
        self.selected = selected
        self.selected_bytes = selected_bytes
        self.downloaded = downloaded
        self.queue = queue
        try:
            sz_str = format_bytes(selected_bytes)
            self.query_one("#cnt-selected", Label).update(f"Selected: [bold cyan]{selected}[/] ({sz_str})")
            self.query_one("#cnt-downloaded", Label).update(f"Downloaded: [bold green]{downloaded}[/]")
            self.query_one("#cnt-queue", Label).update(f"Queue: [bold yellow]{queue}[/]")
        except Exception:
            pass
