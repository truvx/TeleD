"""Selection and download action methods for MainScreen."""
import asyncio
from typing import Optional
from textual.widgets import DataTable
import tgdl.database as db
from tgdl.screens.error_modal import ErrorModal
from tgdl.widgets import StatCard, CounterBar
from tgdl.utils.helpers import format_bytes


class SelectionMixin:
    """Mixin providing file selection, download queue, and counter logic for MainScreen."""

    def _get_cursor_row_key(self, table: DataTable):
        if table.row_count > 0 and table.cursor_coordinate is not None:
            try:
                return table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            except Exception:
                return None
        return None

    def action_toggle_selection(self) -> None:
        table = self.query_one("#files-table", DataTable)
        row_key = self._get_cursor_row_key(table)
        if row_key is not None:
            msg_id = int(row_key.value)
            if msg_id in self.selected_ids:
                self.selected_ids.remove(msg_id)
                table.update_cell(row_key, "select", " ")
            else:
                self.selected_ids.add(msg_id)
                table.update_cell(row_key, "select", "✔")
            asyncio.create_task(self._update_counters())

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        await self.action_download_selected()

    async def action_toggle_select_all(self) -> None:
        table = self.query_one("#files-table", DataTable)
        all_keys = list(table.rows.keys())
        if len(self.selected_ids) >= len(all_keys) and len(all_keys) > 0:
            await self.action_clear_selection()
        else:
            await self.action_select_all()

    async def action_select_all(self) -> None:
        table = self.query_one("#files-table", DataTable)
        for key in list(table.rows.keys()):
            self.selected_ids.add(int(key.value))
            table.update_cell(key, "select", "✔")
        await self._update_counters()

    async def action_clear_selection(self) -> None:
        table = self.query_one("#files-table", DataTable)
        for key in list(table.rows.keys()):
            self.selected_ids.discard(int(key.value))
            table.update_cell(key, "select", " ")
        self.selected_ids.clear()
        await self._update_counters()

    async def action_download_selected(self) -> None:
        table = self.query_one("#files-table", DataTable)
        target_ids = set(self.selected_ids)
        if not target_ids:
            row_key = self._get_cursor_row_key(table)
            if row_key is not None:
                target_ids.add(int(row_key.value))
        if not target_ids:
            return
        for msg_id in target_ids:
            await self.downloader.add_to_queue(msg_id)
        self.selected_ids.clear()
        try: self.notify(f"🚀 Queued {len(target_ids)} file(s) for download!", timeout=3)
        except Exception: pass
        await self.reload_table()

    async def action_toggle_pause_queue(self) -> None:
        await (self.downloader.resume_queue() if self.downloader.is_paused else self.downloader.pause_queue())
        await self.reload_table()

    async def action_cancel_queue(self) -> None:
        await self.downloader.cancel_queue()
        await self.reload_table()

    async def action_retry_failed(self) -> None:
        await self.downloader.retry_failed()
        await self.reload_table()

    async def _update_counters(self) -> None:
        q_cnt = len(self.downloader.active_jobs)
        sel_bytes = sum(
            j.file_size for j in self.downloader.active_jobs.values()
            if j.message_id in self.selected_ids
        )
        q_dl = sum(j.downloaded_bytes for j in self.downloader.active_jobs.values())
        q_tot = sum(j.file_size for j in self.downloader.active_jobs.values())
        try:
            self.query_one("#counter-bar", CounterBar).update_counts(
                selected=len(self.selected_ids), selected_bytes=sel_bytes,
                downloaded=self._dl_count, queue=q_cnt,
                queue_downloaded=q_dl, queue_total=q_tot
            )
        except Exception:
            pass
