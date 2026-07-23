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

    def _get_active_table(self) -> DataTable:
        from textual.widgets import TabbedContent
        try:
            tabs = self.query_one("#right-tabs", TabbedContent)
            if tabs.active == "downloaded-table-pane":
                return self.query_one("#downloaded-table", DataTable)
        except Exception:
            pass
        return self.query_one("#files-table", DataTable)

    def _get_cursor_row_key(self, table: DataTable):
        if table.row_count > 0 and table.cursor_coordinate is not None:
            try:
                return table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            except Exception:
                return None
        return None

    def action_toggle_selection(self) -> None:
        table = self._get_active_table()
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
        """Fires when user presses Enter on a DataTable row."""
        await self.action_download_selected()

    async def action_toggle_select_all(self) -> None:
        table = self._get_active_table()
        all_keys = list(table.rows.keys())
        if len(self.selected_ids) >= len(all_keys) and len(all_keys) > 0:
            await self.action_clear_selection()
        else:
            await self.action_select_all()

    async def action_select_all(self) -> None:
        table = self._get_active_table()
        for key in list(table.rows.keys()):
            self.selected_ids.add(int(key.value))
            table.update_cell(key, "select", "✔")
        await self._update_counters()

    async def action_clear_selection(self) -> None:
        table = self._get_active_table()
        for key in list(table.rows.keys()):
            self.selected_ids.discard(int(key.value))
            table.update_cell(key, "select", " ")
        self.selected_ids.clear()
        await self._update_counters()

    async def action_download_selected(self) -> None:
        """Queue selected file(s) for download; if none selected, queue file under cursor."""
        table = self._get_active_table()
        target_ids = set(self.selected_ids)

        if not target_ids:
            row_key = self._get_cursor_row_key(table)
            if row_key is not None:
                target_ids.add(int(row_key.value))

        if not target_ids:
            return

        added = 0
        skipped = 0
        for msg_id in target_ids:
            result = await self.downloader.add_to_queue(msg_id)
            if result:
                added += 1
            else:
                skipped += 1

        self.selected_ids.clear()

        if added > 0:
            skip_note = f" ({skipped} already queued)" if skipped > 0 else ""
            try:
                self.notify(f"🚀 Queued {added} file(s) for download!{skip_note}", timeout=3)
            except Exception:
                pass
        elif skipped > 0:
            try:
                self.notify(f"⚠️ File(s) already in queue.", timeout=2)
            except Exception:
                pass

        await self.reload_table()

    async def action_toggle_pause_queue(self) -> None:
        if self.downloader.is_paused:
            await self.downloader.resume_queue()
            try:
                self.notify("▶ Queue resumed.", timeout=2)
            except Exception:
                pass
        else:
            await self.downloader.pause_queue()
            try:
                self.notify("⏸ Queue paused.", timeout=2)
            except Exception:
                pass
        await self.reload_table()

    async def action_cancel_queue(self) -> None:
        await self.downloader.cancel_queue()
        try:
            self.notify("✖ Queue cancelled.", timeout=2)
        except Exception:
            pass
        await self.reload_table()

    async def action_retry_failed(self) -> None:
        await self.downloader.retry_failed()
        await self.reload_table()

    async def _update_counters(self) -> None:
        active_jobs = self.downloader.active_jobs
        q_cnt = len(active_jobs)
        sel_bytes = sum(
            j.file_size for j in active_jobs.values()
            if j.message_id in self.selected_ids
        )
        q_dl = sum(j.downloaded_bytes for j in active_jobs.values())
        q_tot = sum(j.file_size for j in active_jobs.values())
        try:
            self.query_one("#counter-bar", CounterBar).update_counts(
                selected=len(self.selected_ids),
                selected_bytes=sel_bytes,
                downloaded=self._dl_count,
                queue=q_cnt,
                queue_downloaded=q_dl,
                queue_total=q_tot,
            )
        except Exception:
            pass
