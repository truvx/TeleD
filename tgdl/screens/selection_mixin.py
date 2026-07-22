"""Selection and download action methods for MainScreen."""
import asyncio
from textual.widgets import DataTable
import tgdl.database as db
from tgdl.screens.error_modal import ErrorModal
from tgdl.widgets import StatCard, CounterBar
from tgdl.utils.helpers import format_bytes


class SelectionMixin:
    """Mixin providing file selection, download queue, and counter logic for MainScreen."""

    def action_toggle_selection(self) -> None:
        table = self.query_one("#files-table", DataTable)
        if table.row_count > 0 and table.cursor_coordinate is not None:
            row_key = table.get_row_key_at_index(table.cursor_coordinate.row)
            msg_id = int(row_key.value)
            if msg_id in self.selected_ids:
                self.selected_ids.remove(msg_id)
                table.update_cell(row_key, "select", " ")
            else:
                self.selected_ids.add(msg_id)
                table.update_cell(row_key, "select", "✔")
            asyncio.create_task(self._update_counters())

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        msg_id = int(event.row_key.value)
        table = self.query_one("#files-table", DataTable)
        if msg_id in self.selected_ids:
            self.selected_ids.remove(msg_id)
            table.update_cell(event.row_key, "select", " ")
        else:
            self.selected_ids.add(msg_id)
            table.update_cell(event.row_key, "select", "✔")
        asyncio.create_task(self._update_counters())

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
        if not target_ids and table.row_count > 0 and table.cursor_coordinate is not None:
            target_ids.add(int(table.get_row_key_at_index(table.cursor_coordinate.row).value))
        if not target_ids:
            return
        for msg_id in target_ids:
            await self.downloader.add_to_queue(msg_id)
        self.selected_ids.clear()
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
        q_cnt = self.downloader.queue.qsize() + len(self.downloader.queued_ids)
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
