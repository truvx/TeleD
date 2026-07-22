from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, Static, ProgressBar
from textual.containers import Horizontal, Vertical
from tgdl.models import DownloadJob
from tgdl.utils.helpers import format_bytes, format_speed, format_eta

class StatCard(Widget):
    """Compact telemetry card for metrics."""

    DEFAULT_CSS = """
    StatCard {
        background: $surface;
        border: round $primary-muted;
        padding: 0 1;
        height: 3;
        min-width: 16;
    }
    StatCard Label.title {
        color: $text-muted;
        text-style: bold;
        height: 1;
    }
    StatCard Label.value {
        color: $accent;
        text-style: bold;
        height: 1;
    }
    """

    def __init__(self, title: str, initial_value: str = "0", **kwargs) -> None:
        super().__init__(**kwargs)
        self.title_text = title
        self.val_text = initial_value

    def compose(self) -> ComposeResult:
        yield Label(self.title_text, classes="title")
        yield Label(self.val_text, classes="value")

    def update_value(self, new_value: str) -> None:
        self.val_text = new_value
        try:
            self.query_one("Label.value", Label).update(new_value)
        except Exception:
            pass

class DownloadProgressRow(Widget):
    """Detailed live download progress card with Rich styling."""

    DEFAULT_CSS = """
    DownloadProgressRow {
        background: $panel;
        border: round $primary;
        padding: 1;
        margin-bottom: 1;
        height: auto;
    }
    .fn-label {
        color: $text;
        text-style: bold;
    }
    .status-label {
        color: $accent;
        text-style: bold;
    }
    .metrics-label {
        color: $text-muted;
    }
    .speed-label {
        color: $success;
        text-style: bold;
    }
    """

    def __init__(self, job: DownloadJob, **kwargs) -> None:
        super().__init__(**kwargs)
        self.job = job

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal():
                yield Label(f"📄 {self.job.filename}", classes="fn-label")
                yield Label(f" [{self.job.status.upper()}]", classes="status-label")
            yield ProgressBar(total=100, show_percentage=True, id=f"pb-{self.job.message_id}")
            with Horizontal():
                yield Label(self._format_bytes_info(), classes="metrics-label", id=f"mb-{self.job.message_id}")
                yield Label(self._format_speed_info(), classes="speed-label", id=f"sb-{self.job.message_id}")

    def update_job(self, job: DownloadJob) -> None:
        self.job = job
        try:
            pb = self.query_one(f"#pb-{self.job.message_id}", ProgressBar)
            pb.progress = min(max(job.progress, 0.0), 100.0)
            
            mb = self.query_one(f"#mb-{self.job.message_id}", Label)
            mb.update(self._format_bytes_info())
            
            sb = self.query_one(f"#sb-{self.job.message_id}", Label)
            sb.update(self._format_speed_info())
        except Exception:
            pass

    def _format_bytes_info(self) -> str:
        dl_str = format_bytes(self.job.downloaded_bytes)
        tot_str = format_bytes(self.job.file_size)
        return f"{dl_str} / {tot_str} ({self.job.progress:.1f}%)"

    def _format_speed_info(self) -> str:
        if self.job.status == "completed":
            return "✔ Finished"
        elif self.job.status == "failed":
            return "✖ Failed"
        elif self.job.status == "paused":
            return "⏸ Paused"
            
        cur_spd = format_speed(self.job.speed)
        avg_spd = format_speed(self.job.avg_speed)
        eta_str = format_eta(self.job.eta)
        return f"⚡ {cur_spd} (Avg: {avg_spd}) | ETA: {eta_str}"

class CounterBar(Static):
    """Bottom status counter displaying selection, overall queue progress, and download metrics."""

    DEFAULT_CSS = """
    CounterBar {
        background: $primary-background;
        color: $text;
        height: 1;
        padding: 0 1;
        text-style: bold;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("Selected: 0 files (0 B) | Downloaded: 0 | Queue: 0", **kwargs)

    def update_counts(self, selected: int, selected_bytes: int = 0, downloaded: int = 0, queue: int = 0, queue_downloaded: int = 0, queue_total: int = 0) -> None:
        sel_size_str = format_bytes(selected_bytes)
        q_pct_str = ""
        if queue_total > 0:
            pct = (queue_downloaded / queue_total) * 100.0
            q_pct_str = f" ({pct:.1f}% of {format_bytes(queue_total)})"
            
        text = f"Selected: [bold yellow]{selected}[/] files ({sel_size_str}) | Downloaded: [bold green]{downloaded}[/] | Queue: [bold cyan]{queue}[/]{q_pct_str}"
        self.update(text)
