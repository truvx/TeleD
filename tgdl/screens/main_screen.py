import asyncio
import os
from typing import Dict, Set
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, DataTable, Input, Label
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.coordinate import Coordinate

from tgdl.browser import Browser
from tgdl.downloader import Downloader
from tgdl.widgets import DownloadProgressRow, StatCard
from tgdl.models import DownloadJob
from tgdl.utils.helpers import format_bytes, format_speed
import tgdl.database as db

class MainScreen(Screen):
    """The main dashboard screen displaying the file browser and download queue."""

    BINDINGS = [
        ("s", "toggle_selection", "Select/Deselect"),
        ("a", "toggle_select_all", "Select/Deselect All"),
        ("d", "download_selected", "Download Selected"),
        ("r", "sync_telegram", "Refresh Files"),
        ("o", "cycle_sorting", "Cycle Sort"),
        ("q", "quit", "Quit")
    ]

    DEFAULT_CSS = """
    MainScreen {
        background: $background;
    }
    
    #main-container {
        layout: horizontal;
        height: 1fr;
    }
    
    #left-pane {
        width: 60%;
        height: 100%;
        border-right: vline $primary-muted;
        padding: 1;
        layout: vertical;
    }
    
    #right-pane {
        width: 40%;
        height: 100%;
        padding: 1;
        layout: vertical;
    }
    
    #search-bar {
        margin-bottom: 1;
    }
    
    #sort-label {
        margin-bottom: 1;
        color: $accent;
        text-style: bold;
        height: 1;
    }
    
    #stats-row {
        layout: horizontal;
        height: 6;
        margin-bottom: 1;
    }
    
    #downloads-list {
        border: tall $primary-muted;
        background: $background-lighten-1;
        height: 1fr;
        overflow-y: scroll;
    }
    """

    def __init__(self, browser: Browser, downloader: Downloader, **kwargs) -> None:
        super().__init__(**kwargs)
        self.browser = browser
        self.downloader = downloader
        self.selected_ids: Set[int] = set()
        self.progress_widgets: Dict[int, DownloadProgressRow] = {}
        
        # Sorting state
        self.sort_by = "message_id"
        self.sort_desc = True
        self.sort_fields = ["message_id", "filename", "file_size", "upload_date"]
        self.sort_names = {"message_id": "ID", "filename": "Name", "file_size": "Size", "upload_date": "Date"}

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            with Vertical(id="left-pane"):
                yield Input(placeholder="Search by filename or mime...", id="search-bar")
                yield Label("Sorting: ID (Desc)", id="sort-label")
                yield DataTable(id="files-table")
            with Vertical(id="right-pane"):
                with Horizontal(id="stats-row"):
                    yield StatCard("Queue Size", "0", id="stat-queue")
                    yield StatCard("Total Speed", "0 B/s", id="stat-speed")
                with VerticalScroll(id="downloads-list"):
                    pass
        yield Footer()

    async def on_mount(self) -> None:
        table = self.query_one("#files-table", DataTable)
        table.cursor_type = "row"
        
        # Setup table headers
        table.add_column("[ ]", key="select")
        table.add_column("ID", key="id")
        table.add_column("Filename", key="filename")
        table.add_column("Size", key="size")
        table.add_column("Status", key="status")
        table.add_column("Date", key="date")

        await self.reload_table()
        
        # Start downloader and periodic UI updates
        self.downloader.start()
        self.set_interval(0.5, self.update_stats_and_jobs)

    async def action_quit(self) -> None:
        """Gracefully stop background jobs and exit."""
        await self.downloader.stop()
        self.app.exit()

    async def reload_table(self) -> None:
        """Fetch and reload table items based on current search/sorting state."""
        try:
            search_bar = self.query_one("#search-bar", Input)
            query = search_bar.value.strip() or None
        except Exception:
            query = None

        messages = await self.browser.load_messages(
            search_query=query,
            sort_by=self.sort_by,
            sort_desc=self.sort_desc
        )

        table = self.query_one("#files-table", DataTable)
        table.clear()
        
        for msg in messages:
            sel_text = "[x]" if msg.message_id in self.selected_ids else "[ ]"
            table.add_row(
                sel_text,
                str(msg.message_id),
                msg.filename,
                format_bytes(msg.file_size),
                msg.download_status.capitalize(),
                msg.upload_date[:10] if msg.upload_date else "",
                key=str(msg.message_id)
            )

        # Update sort label description
        sort_name = self.sort_names.get(self.sort_by, "ID")
        direction = "Desc" if self.sort_desc else "Asc"
        try:
            self.query_one("#sort-label", Label).update(f"Sorting: {sort_name} ({direction}) | Count: {len(messages)}")
        except Exception:
            pass

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Triggered when the search query changes."""
        if event.input.id == "search-bar":
            await self.reload_table()

    def action_toggle_selection(self) -> None:
        """Toggle selection state for the currently focused row."""
        table = self.query_one("#files-table", DataTable)
        if table.row_count == 0 or table.cursor_coordinate is None:
            return
        
        row_idx = table.cursor_coordinate.row
        row_key = table.get_row_key_at_index(row_idx)
        msg_id = int(row_key.value)
        
        if msg_id in self.selected_ids:
            self.selected_ids.remove(msg_id)
            table.update_cell(row_key, "select", "[ ]")
        else:
            self.selected_ids.add(msg_id)
            table.update_cell(row_key, "select", "[x]")

    def action_toggle_select_all(self) -> None:
        """Toggle select-all or deselect-all for currently displayed files."""
        table = self.query_one("#files-table", DataTable)
        if table.row_count == 0:
            return
            
        all_row_keys = list(table.rows.keys())
        displayed_ids = {int(key.value) for key in all_row_keys}
        
        if displayed_ids.issubset(self.selected_ids):
            # Deselect all displayed
            for key in all_row_keys:
                msg_id = int(key.value)
                self.selected_ids.discard(msg_id)
                table.update_cell(key, "select", "[ ]")
        else:
            # Select all displayed
            for key in all_row_keys:
                msg_id = int(key.value)
                self.selected_ids.add(msg_id)
                table.update_cell(key, "select", "[x]")

    async def action_download_selected(self) -> None:
        """Add all selected messages to the downloader queue."""
        if not self.selected_ids:
            return
            
        for msg_id in list(self.selected_ids):
            await self.downloader.add_to_queue(msg_id)
            
        self.selected_ids.clear()
        await self.reload_table()

    async def action_sync_telegram(self) -> None:
        """Fetch and cache any new messages since the last sync."""
        sort_lbl = self.query_one("#sort-label", Label)
        sort_lbl.update("Syncing with Telegram...")
        
        new_count = await self.browser.sync_messages()
        await self.reload_table()
        
        # Reset notice
        sort_lbl.update(f"Sync complete. Found {new_count} new messages.")
        await asyncio.sleep(2)
        await self.reload_table()

    async def action_cycle_sorting(self) -> None:
        """Cycle through the sorting columns."""
        current_idx = self.sort_fields.index(self.sort_by)
        next_idx = (current_idx + 1) % len(self.sort_fields)
        self.sort_by = self.sort_fields[next_idx]
        
        # Toggle direction or keep DESC as default
        self.sort_desc = True if self.sort_by in ("message_id", "upload_date", "file_size") else False
        await self.reload_table()

    async def update_stats_and_jobs(self) -> None:
        """Refresh active download stats, queue cards, and update cells."""
        active_jobs = self.downloader.active_jobs
        table = self.query_one("#files-table", DataTable)
        
        # 1. Update active progress row widgets
        downloads_list = self.query_one("#downloads-list", VerticalScroll)
        
        # Mount new jobs and update active ones
        for msg_id, job in list(active_jobs.items()):
            if msg_id not in self.progress_widgets:
                widget = DownloadProgressRow(job)
                self.progress_widgets[msg_id] = widget
                downloads_list.mount(widget)
            else:
                self.progress_widgets[msg_id].update_job(job)
                
            # Update DataTable status column
            try:
                table.update_cell(str(msg_id), "status", f"Downloading ({int(job.progress)}%)")
            except Exception:
                pass

        # Handle finished jobs
        for msg_id, widget in list(self.progress_widgets.items()):
            if msg_id not in active_jobs:
                # Refresh status in table from SQLite
                msg_row = await db.get_message(msg_id)
                if msg_row:
                    try:
                        table.update_cell(str(msg_id), "status", msg_row.download_status.capitalize())
                    except Exception:
                        pass
                
                # Check if it transitioned to finished and schedule removal
                if widget.job.status == "downloading":
                    # Update widget one last time to complete state
                    if msg_row:
                        job_copy = DownloadJob(
                            message_id=msg_id,
                            filename=widget.job.filename,
                            file_size=widget.job.file_size,
                            downloaded_bytes=msg_row.file_size,
                            status=msg_row.download_status,
                            progress=100.0 if msg_row.download_status == "completed" else 0.0
                        )
                        widget.update_job(job_copy)

                    # Delayed removal helper
                    async def remove_widget(mid: int, w: DownloadProgressRow) -> None:
                        await asyncio.sleep(4)
                        try:
                            w.remove()
                            self.progress_widgets.pop(mid, None)
                        except Exception:
                            pass
                    asyncio.create_task(remove_widget(msg_id, widget))

        # 2. Update metrics
        total_speed = sum(job.speed for job in active_jobs.values())
        queue_count = self.downloader.queue.qsize() + len(self.downloader.queued_ids)
        
        try:
            self.query_one("#stat-queue", StatCard).update_value(str(queue_count))
            self.query_one("#stat-speed", StatCard).update_value(format_speed(total_speed))
        except Exception:
            pass
