import asyncio
import time
from typing import Dict, Set, Optional
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, DataTable, Input, LoadingIndicator, ProgressBar
from textual.containers import Horizontal, Vertical, VerticalScroll

from tgdl.browser import Browser
from tgdl.downloader import Downloader
from tgdl.widgets import DownloadProgressRow, StatCard, CounterBar
from tgdl.models import DownloadJob
from tgdl.utils.helpers import format_bytes, get_colored_file_badge, highlight_text
from tgdl.screens.error_modal import ErrorModal
from tgdl.screens.settings_screen import SettingsScreen
from tgdl.screens.selection_mixin import SelectionMixin
import tgdl.database as db


class MainScreen(SelectionMixin, Screen):
    """btop/LazyGit styled TeleD dashboard with 100k+ pagination and full error handling."""

    BINDINGS = [
        ("enter", "download_selected", "Download"),
        ("d", "download_selected", "Download"),
        ("space", "toggle_selection", "Select"),
        ("a", "toggle_select_all", "Select All"),
        ("u", "toggle_pause_queue", "Pause/Resume"),
        ("x", "cancel_queue", "Cancel Queue"),
        ("c", "cycle_category", "Category"),
        ("ctrl+p", "focus_search", "Search"),
        ("ctrl+r", "sync_telegram", "Sync"),
        ("escape", "clear_search", "Back"),
        ("right", "next_page", "→ Page"),
        ("left", "prev_page", "← Page"),
        ("q", "quit", "Quit"),
    ]

    DEFAULT_CSS = """
    MainScreen { background: $background; layout: vertical; }
    #main-container { layout: horizontal; height: 1fr; }
    #left-pane { width: 64%; height: 100%; border: round $primary; padding: 0 1; layout: vertical; }
    #left-pane:focus-within { border: round $accent; }
    #right-pane { width: 36%; height: 100%; border: round $primary; padding: 0 1; layout: vertical; }
    #right-pane:focus-within { border: round $accent; }
    #search-bar { margin: 0 0 1 0; height: 3; }
    #sync-progress-bar { height: 1; margin-bottom: 1; display: none; }
    #sync-spinner { height: 1; margin-bottom: 1; display: none; }
    #files-table { height: 1fr; }
    #stats-row { layout: horizontal; height: 4; margin-bottom: 1; }
    #downloads-list { background: $surface; border: round $primary-muted; height: 1fr; overflow-y: scroll; padding: 1; }
    """

    def __init__(self, browser: Browser, downloader: Downloader, **kwargs) -> None:
        super().__init__(**kwargs)
        self.browser, self.downloader = browser, downloader
        self.selected_ids: Set[int] = set()
        self.progress_widgets: Dict[int, DownloadProgressRow] = {}
        self.sort_by, self.sort_desc = "message_id", True
        self.sort_fields = ["filename", "size", "date", "extension", "downloaded", "message_id"]
        self.categories = [None, "videos", "images", "pdf", "documents", "archives", "audio"]
        self.current_category_idx = 0
        self.page, self.page_size, self.total_count = 1, 250, 0
        self._dl_count: int = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-container"):
            with Vertical(id="left-pane"):
                yield Input(placeholder="🔍 Search... (Ctrl+R to sync, ESC to clear, Ctrl+P to focus)", id="search-bar")
                yield ProgressBar(total=100, show_percentage=True, id="sync-progress-bar")
                yield LoadingIndicator(id="sync-spinner")
                yield DataTable(id="files-table")
            with Vertical(id="right-pane"):
                with Horizontal(id="stats-row"):
                    yield StatCard("Filtered Size", "0 B", id="stat-speed")
                    yield StatCard("Active Jobs", "0", id="stat-active")
                with VerticalScroll(id="downloads-list"):
                    pass
        yield CounterBar(id="counter-bar")
        yield Footer()

    def set_subtitle(self, text: str) -> None:
        self.sub_title = text
        try: self.app.sub_title = text
        except Exception: pass

    async def on_mount(self) -> None:
        table = self.query_one("#files-table", DataTable)
        table.cursor_type = "row"
        for title, key in [
            ("✔", "select"), ("Filename", "filename"), ("Size", "size"),
            ("Type", "type"), ("Date", "date"), ("Downloaded", "downloaded"), ("Status", "status")
        ]:
            table.add_column(title, key=key)

        def handle_fail(mid: int, reason: str) -> None:
            var = "warning" if "Session" in reason or "Flood" in reason else "error"
            self.app.push_screen(ErrorModal("Download Failure", f"#{mid}: {reason}", variant=var))

        self.downloader.on_failed.append(handle_fail)
        self.downloader.start()
        self.set_interval(0.1, self.update_stats_and_jobs)
        asyncio.create_task(self._init_async())

    async def _init_async(self) -> None:
        """Load settings, connect, auto-sync if empty — all in background after TUI renders."""
        try:
            self.sort_by = await db.get_setting("sort_by", "message_id")
            self.sort_desc = (await db.get_setting("sort_desc", "true")) == "true"
            self.app.theme = await db.get_setting("theme", "textual-dark")
        except Exception: pass

        try:
            await self.browser.client_wrapper.connect()
            me = await self.browser.client_wrapper.get_me()
            uname = me.get("username") or f"User_{me.get('id', 0)}"
            self.set_subtitle(f"Connected as: @{uname}")
        except Exception:
            self.set_subtitle("Offline — press Ctrl+R to sync when connected")

        count, _ = await db.get_filtered_totals()
        if count == 0:
            await self._do_sync(auto=True)
        await self.reload_table()

    # ── Actions ───────────────────────────────────────────────────────────

    def on_resize(self) -> None: self.refresh()
    async def action_quit(self) -> None: await self.downloader.stop(); self.app.exit()
    async def action_focus_search(self) -> None: self.query_one("#search-bar", Input).focus()
    async def action_focus_queue(self) -> None: self.query_one("#downloads-list", VerticalScroll).focus()
    async def action_toggle_theme(self) -> None:
        self.app.theme = "textual-light" if getattr(self.app, "theme", "textual-dark") == "textual-dark" else "textual-dark"
        await db.set_setting("theme", self.app.theme)
    async def action_open_settings(self) -> None:
        self.app.push_screen(SettingsScreen(), lambda s: asyncio.create_task(self.reload_table()) if s else None)
    async def action_cycle_category(self) -> None:
        self.current_category_idx = (self.current_category_idx + 1) % len(self.categories)
        self.page = 1; await self.reload_table()
    async def action_next_page(self) -> None:
        mp = max(1, (self.total_count + self.page_size - 1) // self.page_size)
        if self.page < mp: self.page += 1; await self.reload_table()
    async def action_prev_page(self) -> None:
        if self.page > 1: self.page -= 1; await self.reload_table()

    async def action_clear_search(self) -> None:
        self.query_one("#search-bar", Input).value = ""
        self.page = 1
        self.query_one("#files-table", DataTable).focus()
        await self.reload_table()

    async def _do_sync(self, auto: bool = False) -> None:
        pbar = self.query_one("#sync-progress-bar", ProgressBar)
        pbar.display = True
        pbar.progress = 0
        prev = self.sub_title or ""
        self.set_subtitle(prev + " — Syncing…")
        last_update = [0.0]

        async def on_sync_progress(scanned: int, total: int, found_media: int) -> None:
            now = time.time()
            if now - last_update[0] >= 0.25 or scanned == total:
                last_update[0] = now
                if total > 0:
                    pbar.update(total=total, progress=scanned)
                st = f"Syncing {scanned}/{total} messages ({found_media} media items found)..."
                self.set_subtitle(st)

        try:
            n = await self.browser.sync_messages(progress_callback=on_sync_progress)
            self.set_subtitle(prev)
            await self.reload_table()
        except Exception as e:
            self.set_subtitle(prev)
            self.app.push_screen(ErrorModal("Sync Notice", str(e), variant="warning"))
        finally:
            pbar.display = False

    async def action_sync_telegram(self) -> None:
        asyncio.create_task(self._do_sync())

    async def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        col_map = {"filename": "filename", "type": "extension", "size": "size", "date": "date", "downloaded": "downloaded"}
        target = col_map.get(str(event.column_key.value), "message_id")
        self.sort_desc = not self.sort_desc if self.sort_by == target else True
        self.sort_by = target
        await db.set_setting("sort_by", self.sort_by)
        await db.set_setting("sort_desc", str(self.sort_desc).lower())
        await self.reload_table()

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-bar":
            self.page = 1
            await self.reload_table()

    async def reload_table(self) -> None:
        try:
            search_bar = self.query_one("#search-bar", Input)
            query = search_bar.value.strip() or None
        except Exception:
            search_bar, query = None, None

        cat = self.categories[self.current_category_idx]
        self.total_count, total_bytes = await db.get_filtered_totals(search_query=query, category_filter=cat)
        max_pages = max(1, (self.total_count + self.page_size - 1) // self.page_size)
        if self.page > max_pages: self.page = max_pages

        offset = (self.page - 1) * self.page_size
        messages = await self.browser.load_messages(
            search_query=query, sort_by=self.sort_by, sort_desc=self.sort_desc,
            category_filter=cat, limit=self.page_size, offset=offset
        )
        table = self.query_one("#files-table", DataTable)
        table.clear()

        cat_label = f"[{cat.upper()}] " if cat else ""
        paused_str = " (PAUSED)" if self.downloader.is_paused else ""
        if search_bar:
            search_bar.placeholder = f"🔍 {cat_label}Search (Page {self.page}/{max_pages}, {self.total_count} items, {format_bytes(total_bytes)}){paused_str}…"

        st_map = {"completed": "[green]Done[/]", "failed": "[red]Failed[/]",
                  "downloading": "[yellow]DL…[/]", "paused": "[yellow]Paused[/]", "cancelled": "[dim]Cancelled[/]"}
        self._dl_count = 0
        for msg in messages:
            if msg.download_status == "completed": self._dl_count += 1
            table.add_row(
                "✔" if msg.message_id in self.selected_ids else " ",
                highlight_text(msg.filename, query) if query else msg.filename,
                format_bytes(msg.file_size),
                get_colored_file_badge(msg.filename, msg.mime_type, msg.extension),
                msg.upload_date[:10] if msg.upload_date else "",
                "[green]Yes[/]" if msg.download_status == "completed" else "[dim]No[/]",
                st_map.get(msg.download_status, f"[cyan]{msg.download_status.title()}[/]"),
                key=str(msg.message_id)
            )
        try: self.query_one("#stat-speed", StatCard).update_value(format_bytes(total_bytes))
        except Exception: pass
        await self._update_counters()

    async def update_stats_and_jobs(self) -> None:
        active_jobs = self.downloader.active_jobs
        try: downloads_list = self.query_one("#downloads-list", VerticalScroll)
        except Exception: return

        for msg_id, job in list(active_jobs.items()):
            if msg_id not in self.progress_widgets:
                widget = DownloadProgressRow(job)
                self.progress_widgets[msg_id] = widget
                await downloads_list.mount(widget)
            else:
                self.progress_widgets[msg_id].update_job(job)

        for msg_id, widget in list(self.progress_widgets.items()):
            if msg_id not in active_jobs:
                async def _rm(target_id: int, w: DownloadProgressRow) -> None:
                    await asyncio.sleep(3)
                    try: w.remove(); self.progress_widgets.pop(target_id, None)
                    except Exception: pass
                asyncio.create_task(_rm(msg_id, widget))

        try: self.query_one("#stat-active", StatCard).update_value(str(len(active_jobs)))
        except Exception: pass
        await self._update_counters()
