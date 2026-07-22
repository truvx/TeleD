import asyncio
from typing import Dict, Set
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, DataTable, Input, Label, LoadingIndicator
from textual.containers import Horizontal, Vertical, VerticalScroll

from tgdl.browser import Browser
from tgdl.downloader import Downloader
from tgdl.widgets import DownloadProgressRow, StatCard, CounterBar
from tgdl.models import DownloadJob
from tgdl.utils.helpers import format_bytes, format_speed, get_colored_file_badge
from tgdl.screens.error_modal import ErrorModal
import tgdl.database as db

class MainScreen(Screen):
    """Modern btop/LazyGit styled dashboard screen for TeleD."""

    BINDINGS = [
        ("f", "focus_search", "Search"),
        ("space", "toggle_selection", "Select"),
        ("ctrl+a", "select_all", "Select All"),
        ("ctrl+d", "clear_selection", "Clear Select"),
        ("enter", "download_selected", "Download"),
        ("delete,backspace", "remove_cache_entry", "Delete Cache"),
        ("escape", "clear_search", "Esc/Clear"),
        ("o", "cycle_sorting", "Sort"),
        ("r", "sync_telegram", "Refresh"),
        ("t", "toggle_theme", "Theme"),
        ("q", "quit", "Quit"),
    ]

    DEFAULT_CSS = """
    MainScreen { background: $background; layout: vertical; }
    #main-container { layout: horizontal; height: 1fr; }
    #left-pane { width: 62%; height: 100%; border: round $primary; padding: 0 1; layout: vertical; }
    #left-pane:focus-within { border: round $accent; }
    #right-pane { width: 38%; height: 100%; border: round $primary; padding: 0 1; layout: vertical; }
    #right-pane:focus-within { border: round $accent; }
    #search-bar { margin: 0 0 1 0; height: 3; border: round $primary-muted; }
    #search-bar:focus { border: round $accent; }
    #sync-spinner { height: 1; margin-bottom: 1; display: none; }
    #files-table { height: 1fr; }
    #stats-row { layout: horizontal; height: 4; margin-bottom: 1; }
    #downloads-list { background: $surface; border: round $primary-muted; height: 1fr; overflow-y: scroll; padding: 1; }
    """

    def __init__(self, browser: Browser, downloader: Downloader, **kwargs) -> None:
        super().__init__(**kwargs)
        self.browser = browser
        self.downloader = downloader
        self.selected_ids: Set[int] = set()
        self.progress_widgets: Dict[int, DownloadProgressRow] = {}
        self.sort_by = "message_id"
        self.sort_desc = True
        self.sort_fields = ["filename", "file_size", "upload_date", "extension", "message_id"]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-container"):
            with Vertical(id="left-pane"):
                yield Input(placeholder="🔍 Type to search... (ESC clear, TAB focus)", id="search-bar")
                yield LoadingIndicator(id="sync-spinner")
                yield DataTable(id="files-table")
            with Vertical(id="right-pane"):
                with Horizontal(id="stats-row"):
                    yield StatCard("Active Speed", "0 B/s", id="stat-speed")
                    yield StatCard("Active Jobs", "0", id="stat-active")
                with VerticalScroll(id="downloads-list"):
                    pass
        yield CounterBar(id="counter-bar")
        yield Footer()

    async def on_mount(self) -> None:
        table = self.query_one("#files-table", DataTable)
        table.cursor_type = "row"
        table.add_column("✔", key="select")
        table.add_column("ID", key="id")
        table.add_column("Filename", key="filename")
        table.add_column("Ext", key="ext")
        table.add_column("Size", key="size")
        table.add_column("Date", key="date")
        
        # Display Connected User Username in Header Subtitle
        try:
            me = await self.browser.client_wrapper.get_me()
            username = me.get("username") or f"User_{me.get('id', 0)}"
            self.sub_title = f"Connected as: @{username}"
        except Exception:
            self.sub_title = "Connected as: @TelegramUser"

        # Restore saved state settings
        self.sort_by = await db.get_setting("sort_by", "message_id")
        self.sort_desc = (await db.get_setting("sort_desc", "true")) == "true"
        saved_search = await db.get_setting("search_query", "")
        if saved_search:
            self.query_one("#search-bar", Input).value = saved_search

        saved_theme = await db.get_setting("theme", "textual-dark")
        self.app.theme = saved_theme

        def handle_download_error(msg_id: int, reason: str) -> None:
            self.app.push_screen(ErrorModal("Download Error", f"Message #{msg_id} failed: {reason}"))
            
        self.downloader.on_failed.append(handle_download_error)
        await self.reload_table()
        self.downloader.start()
        self.set_interval(0.5, self.update_stats_and_jobs)

    def on_resize(self) -> None:
        self.refresh()

    async def action_quit(self) -> None:
        await self.downloader.stop()
        self.app.exit()

    async def action_focus_search(self) -> None:
        self.query_one("#search-bar", Input).focus()

    async def action_clear_search(self) -> None:
        search_bar = self.query_one("#search-bar", Input)
        search_bar.value = ""
        await db.set_setting("search_query", "")
        self.query_one("#files-table", DataTable).focus()
        await self.reload_table()

    async def action_toggle_theme(self) -> None:
        current = getattr(self.app, "theme", "textual-dark")
        next_theme = "textual-light" if current == "textual-dark" else "textual-dark"
        self.app.theme = next_theme
        await db.set_setting("theme", next_theme)

    async def action_cycle_sorting(self) -> None:
        idx = (self.sort_fields.index(self.sort_by) + 1) % len(self.sort_fields)
        self.sort_by = self.sort_fields[idx]
        await db.set_setting("sort_by", self.sort_by)
        await db.set_setting("sort_desc", str(self.sort_desc).lower())
        await self.reload_table()

    async def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        col_key = str(event.column_key.value)
        key_map = {"filename": "filename", "ext": "extension", "size": "file_size", "date": "upload_date", "id": "message_id"}
        target = key_map.get(col_key, "message_id")
        if self.sort_by == target:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_by = target
            self.sort_desc = True
        await db.set_setting("sort_by", self.sort_by)
        await db.set_setting("sort_desc", str(self.sort_desc).lower())
        await self.reload_table()

    async def reload_table(self) -> None:
        try:
            search_bar = self.query_one("#search-bar", Input)
            query = search_bar.value.strip() or None
        except Exception:
            query = None

        messages = await self.browser.load_messages(search_query=query, sort_by=self.sort_by, sort_desc=self.sort_desc)
        table = self.query_one("#files-table", DataTable)
        table.clear()
        
        for msg in messages:
            sel_text = "✔" if msg.message_id in self.selected_ids else " "
            badge = get_colored_file_badge(msg.filename, msg.mime_type, msg.extension)
            table.add_row(sel_text, str(msg.message_id), msg.filename, badge, format_bytes(msg.file_size), msg.upload_date[:10] if msg.upload_date else "", key=str(msg.message_id))
            
        await self._update_counters()

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-bar":
            await db.set_setting("search_query", event.input.value)
            await self.reload_table()

    def action_toggle_selection(self) -> None:
        table = self.query_one("#files-table", DataTable)
        if table.row_count == 0 or table.cursor_coordinate is None:
            return
        row_key = table.get_row_key_at_index(table.cursor_coordinate.row)
        msg_id = int(row_key.value)
        if msg_id in self.selected_ids:
            self.selected_ids.remove(msg_id)
            table.update_cell(row_key, "select", " ")
        else:
            self.selected_ids.add(msg_id)
            table.update_cell(row_key, "select", "✔")
        asyncio.create_task(self._update_counters())

    async def action_select_all(self) -> None:
        table = self.query_one("#files-table", DataTable)
        if table.row_count == 0:
            return
        all_row_keys = list(table.rows.keys())
        for key in all_row_keys:
            msg_id = int(key.value)
            self.selected_ids.add(msg_id)
            table.update_cell(key, "select", "✔")
        await self._update_counters()

    async def action_clear_selection(self) -> None:
        table = self.query_one("#files-table", DataTable)
        if table.row_count == 0:
            return
        all_row_keys = list(table.rows.keys())
        for key in all_row_keys:
            msg_id = int(key.value)
            self.selected_ids.discard(msg_id)
            table.update_cell(key, "select", " ")
        self.selected_ids.clear()
        await self._update_counters()

    async def action_remove_cache_entry(self) -> None:
        table = self.query_one("#files-table", DataTable)
        if table.row_count == 0 or table.cursor_coordinate is None:
            return
        row_key = table.get_row_key_at_index(table.cursor_coordinate.row)
        msg_id = int(row_key.value)
        await db.delete_cached_message(msg_id)
        self.selected_ids.discard(msg_id)
        await self.reload_table()

    async def action_download_selected(self) -> None:
        table = self.query_one("#files-table", DataTable)
        target_ids = set(self.selected_ids)
        if not target_ids and table.row_count > 0 and table.cursor_coordinate is not None:
            row_key = table.get_row_key_at_index(table.cursor_coordinate.row)
            target_ids.add(int(row_key.value))
        if not target_ids:
            return
        for msg_id in target_ids:
            await self.downloader.add_to_queue(msg_id)
        self.selected_ids.clear()
        await self.reload_table()

    async def action_sync_telegram(self) -> None:
        spinner = self.query_one("#sync-spinner", LoadingIndicator)
        spinner.display = True
        try:
            await self.browser.sync_messages()
            await self.reload_table()
        except Exception as e:
            self.app.push_screen(ErrorModal("Sync Failure", str(e)))
        finally:
            spinner.display = False

    async def _update_counters(self) -> None:
        all_msgs = await db.get_cached_messages()
        downloaded_count = sum(1 for m in all_msgs if m.download_status == "completed")
        queue_count = self.downloader.queue.qsize() + len(self.downloader.queued_ids)
        try:
            cbar = self.query_one("#counter-bar", CounterBar)
            cbar.update_counts(selected=len(self.selected_ids), downloaded=downloaded_count, queue=queue_count)
        except Exception:
            pass

    async def update_stats_and_jobs(self) -> None:
        active_jobs = self.downloader.active_jobs
        downloads_list = self.query_one("#downloads-list", VerticalScroll)
        for msg_id, job in list(active_jobs.items()):
            if msg_id not in self.progress_widgets:
                widget = DownloadProgressRow(job)
                self.progress_widgets[msg_id] = widget
                downloads_list.mount(widget)
            else:
                self.progress_widgets[msg_id].update_job(job)

        for msg_id, widget in list(self.progress_widgets.items()):
            if msg_id not in active_jobs:
                msg_row = await db.get_message(msg_id)
                if widget.job.status == "downloading":
                    if msg_row:
                        job_copy = DownloadJob(message_id=msg_id, filename=widget.job.filename, file_size=widget.job.file_size, downloaded_bytes=msg_row.file_size, status=msg_row.download_status, progress=100.0 if msg_row.download_status == "completed" else 0.0)
                        widget.update_job(job_copy)
                    async def remove_widget(mid: int, w: DownloadProgressRow) -> None:
                        await asyncio.sleep(3)
                        try:
                            w.remove()
                            self.progress_widgets.pop(mid, None)
                        except Exception:
                            pass
                    asyncio.create_task(remove_widget(msg_id, widget))

        total_speed = sum(job.speed for job in active_jobs.values())
        try:
            self.query_one("#stat-speed", StatCard).update_value(format_speed(total_speed))
            self.query_one("#stat-active", StatCard).update_value(str(len(active_jobs)))
        except Exception:
            pass
        await self._update_counters()
