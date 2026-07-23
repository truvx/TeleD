"""Production download engine: uses a dedicated per-download thread+loop to avoid
blocking Textual's event loop with Telethon's async I/O operations."""
import asyncio
import os
import time
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional

import tgdl.config as config
import tgdl.database as db
from tgdl.models import DownloadJob
from tgdl.telegram_client import TelegramClientWrapper


class Downloader:
    """Download engine that runs each Telegram download in an isolated thread+event-loop
    to prevent Textual's coroutine scheduling from starving Telethon's MTProto receiver."""

    def __init__(self, client_wrapper: TelegramClientWrapper, concurrency: Optional[int] = None) -> None:
        self.client_wrapper = client_wrapper
        self.concurrency = concurrency or config.CONCURRENT_DOWNLOADS
        self._queue: List[int] = []
        self.active_jobs: Dict[int, DownloadJob] = {}
        self.workers: List[asyncio.Task] = []
        self._running = False
        self.is_paused = False
        self._queue_event: Optional[asyncio.Event] = None
        # Thread pool: one thread per concurrent download slot
        self._executor: Optional[ThreadPoolExecutor] = None

        self.on_progress: List[Callable[[DownloadJob], None]] = []
        self.on_completed: List[Callable[[int, str], None]] = []
        self.on_failed: List[Callable[[int, str], Optional[str]]] = []

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
        self._queue_event = asyncio.Event()
        self._executor = ThreadPoolExecutor(
            max_workers=self.concurrency,
            thread_name_prefix="teled_dl",
        )
        self.workers = [
            asyncio.ensure_future(self._worker())
            for _ in range(self.concurrency)
        ]

    async def stop(self) -> None:
        self._running = False
        if self._queue_event:
            self._queue_event.set()
        for worker in self.workers:
            worker.cancel()
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers = []
        if self._executor:
            self._executor.shutdown(wait=False)
            self._executor = None
        for msg_id, job in list(self.active_jobs.items()):
            try:
                await db.update_download_status(msg_id, "pending", job.downloaded_bytes)
            except Exception:
                pass
        self.active_jobs.clear()
        self._queue.clear()

    # ─────────────────────────────────────────────────────────────────────────
    # Queue management
    # ─────────────────────────────────────────────────────────────────────────

    async def add_to_queue(self, message_id: int) -> bool:
        """Add a file to the download queue. Returns True if added."""
        if message_id in self.active_jobs:
            return False
        msg_meta = await db.get_message(message_id)
        if not msg_meta:
            return False
        status = "paused" if self.is_paused else "queued"
        filename = msg_meta.filename
        if not filename:
            ext = msg_meta.extension or ".unknown"
            filename = f"media_{message_id}{ext}"
            
        job = DownloadJob(
            message_id=message_id,
            filename=filename,
            file_size=msg_meta.file_size,
            downloaded_bytes=0,
            status=status,
        )
        self.active_jobs[message_id] = job
        try:
            await db.update_download_status(message_id, status, 0)
        except Exception:
            pass
        if not self.is_paused:
            self._queue.append(message_id)
            if self._queue_event:
                self._queue_event.set()
        return True

    async def pause_queue(self) -> None:
        self.is_paused = True
        for msg_id, job in list(self.active_jobs.items()):
            if job.status not in ("downloading", "completed", "failed"):
                job.status = "paused"
                try:
                    await db.update_download_status(msg_id, "paused", job.downloaded_bytes)
                except Exception:
                    pass

    async def resume_queue(self) -> None:
        self.is_paused = False
        for msg_id, job in list(self.active_jobs.items()):
            if job.status == "paused":
                job.status = "queued"
                self._queue.append(msg_id)
                try:
                    await db.update_download_status(msg_id, "pending", job.downloaded_bytes)
                except Exception:
                    pass
        if self._queue_event:
            self._queue_event.set()

    async def cancel_queue(self) -> None:
        self._queue.clear()
        for msg_id in list(self.active_jobs.keys()):
            try:
                await db.update_download_status(msg_id, "cancelled", 0)
            except Exception:
                pass
        self.active_jobs.clear()

    async def retry_failed(self) -> None:
        all_cached = await db.get_cached_messages()
        for msg in all_cached:
            if msg.download_status == "failed":
                await self.add_to_queue(msg.message_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Worker loop (runs on Textual's event loop, delegates I/O to thread)
    # ─────────────────────────────────────────────────────────────────────────

    async def _worker(self) -> None:
        while self._running:
            try:
                msg_id = self._queue.pop(0) if self._queue else None

                if msg_id is None:
                    # Nothing to do — yield and wait for signal
                    await asyncio.sleep(0.2)
                    continue

                if self.is_paused:
                    self._queue.insert(0, msg_id)
                    await asyncio.sleep(0.3)
                    continue

                job = self.active_jobs.get(msg_id)
                if not job or job.status == "paused":
                    continue

                job.status = "downloading"
                success = False

                while job.retries <= job.max_retries and not success and not self.is_paused:
                    try:
                        await self._download_file(job)
                        success = True
                    except asyncio.CancelledError:
                        try:
                            await db.update_download_status(msg_id, "cancelled", job.downloaded_bytes)
                        except Exception:
                            pass
                        raise
                    except Exception as e:
                        await self._handle_error(job, e)

                if job.status in ("completed", "failed"):
                    await asyncio.sleep(3)

                self.active_jobs.pop(msg_id, None)

            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1)

    async def _handle_error(self, job: DownloadJob, exc: Exception) -> None:
        """Classify and handle a download error: retry or fail permanently."""
        from telethon.errors.rpcerrorlist import FloodWaitError
        from telethon.errors import (
            AuthKeyUnregisteredError, SessionRevokedError,
            UserDeactivatedError, AuthKeyInvalidError,
        )

        err_str = str(exc)

        if isinstance(exc, FloodWaitError):
            job.status = f"flood wait ({exc.seconds}s)"
            try:
                await db.update_download_status(job.message_id, "pending", job.downloaded_bytes)
            except Exception:
                pass
            await asyncio.sleep(exc.seconds + 1)
            return

        if isinstance(exc, (AuthKeyUnregisteredError, SessionRevokedError,
                            UserDeactivatedError, AuthKeyInvalidError)):
            job.status = "failed"
            job.error_msg = "Session expired — please re-authorize."
            try:
                await db.update_download_status(job.message_id, "failed", job.downloaded_bytes)
            except Exception:
                pass
            for cb in self.on_failed:
                try:
                    cb(job.message_id, job.error_msg)
                except Exception:
                    pass
            return

        if isinstance(exc, PermissionError):
            job.status = "failed"
            job.error_msg = "Permission denied: cannot write to download folder."
            try:
                await db.update_download_status(job.message_id, "failed", job.downloaded_bytes)
            except Exception:
                pass
            for cb in self.on_failed:
                try:
                    cb(job.message_id, job.error_msg)
                except Exception:
                    pass
            return

        if isinstance(exc, OSError) and (getattr(exc, "errno", 0) == 28 or "No space left" in err_str):
            job.status = "failed"
            job.error_msg = "Disk full."
            try:
                await db.update_download_status(job.message_id, "failed", job.downloaded_bytes)
            except Exception:
                pass
            for cb in self.on_failed:
                try:
                    cb(job.message_id, job.error_msg)
                except Exception:
                    pass
            return

        # Transient errors — retry with back-off
        job.retries += 1
        if job.retries <= job.max_retries:
            job.status = f"retry {job.retries}/{job.max_retries}"
            try:
                await db.update_download_status(job.message_id, "pending", job.downloaded_bytes)
            except Exception:
                pass
            await asyncio.sleep(min(2 ** job.retries, 30))
        else:
            job.status = "failed"
            job.error_msg = err_str[:120]
            try:
                await db.update_download_status(job.message_id, "failed", job.downloaded_bytes)
            except Exception:
                pass
            for cb in self.on_failed:
                try:
                    cb(job.message_id, job.error_msg)
                except Exception:
                    pass

    # ─────────────────────────────────────────────────────────────────────────
    # Core download — runs in a dedicated thread+event-loop
    # ─────────────────────────────────────────────────────────────────────────

    async def _download_file(self, job: DownloadJob) -> None:
        """Download one file.

        The actual Telegram I/O runs inside run_in_executor() so it has its own
        asyncio event loop and is completely isolated from Textual's loop.
        This prevents Textual's coroutine scheduler from starving Telethon's
        internal MTProto receive tasks (which caused the '0 Bytes' hang).
        """
        local_path = os.path.join(config.DOWNLOAD_DIR, job.filename)
        local_size = 0

        # ── Resume / skip logic ───────────────────────────────────────────
        if os.path.exists(local_path):
            local_size = os.path.getsize(local_path)
            if local_size >= job.file_size:
                if local_size == job.file_size:
                    # Already complete
                    job.status = "completed"
                    job.progress = 100.0
                    job.downloaded_bytes = job.file_size
                    try:
                        await db.update_download_status(
                            job.message_id, "completed", job.file_size, local_path
                        )
                        await db.record_download_history(
                            job.message_id, job.filename, job.file_size, local_path
                        )
                    except Exception:
                        pass
                    for cb in self.on_completed:
                        try:
                            cb(job.message_id, local_path)
                        except Exception:
                            pass
                    return
                else:
                    # File is larger than expected — corrupted, restart
                    local_size = 0
                    try:
                        os.remove(local_path)
                    except OSError:
                        pass
            else:
                # Partial download: align to 4 KB and resume
                local_size = (local_size // 4096) * 4096
                try:
                    with open(local_path, "r+b") as f:
                        f.truncate(local_size)
                except OSError:
                    local_size = 0

        job.status = "downloading"
        job.downloaded_bytes = local_size
        try:
            await db.update_download_status(job.message_id, "downloading", local_size)
        except Exception:
            pass

        # ── Run the actual download in a thread ───────────────────────────
        downloader = self  # closure reference
        start_time = time.monotonic()
        last_update = [start_time]

        def _thread_download() -> str:
            """Runs in ThreadPoolExecutor with its own asyncio event loop."""
            thread_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(thread_loop)
            exc_holder = [None]

            async def _async_body():
                from telethon import TelegramClient
                from telethon.sessions.string import StringSession

                # Extract the session credentials directly from the main loop's client.
                # This completely bypasses the SQLite session file on disk, avoiding
                # the dreaded 'database is locked' SQLite deadlock when using multiple threads.
                main_session = downloader.client_wrapper.client.session
                ss = StringSession()
                ss.set_dc(main_session.dc_id, main_session.server_address, main_session.port)
                ss.auth_key = main_session.auth_key

                # Fresh client in this thread's loop — completely isolated from UI,
                # and uses an in-memory session to prevent DB contention.
                client = TelegramClient(
                    ss,
                    config.API_ID,
                    config.API_HASH,
                    connection_retries=5,
                    retry_delay=2,
                    timeout=20,
                )
                await client.connect()

                try:
                    msgs = await client.get_messages("me", ids=[job.message_id])
                    if not msgs or not msgs[0] or not msgs[0].media:
                        raise ValueError(
                            f"Message #{job.message_id} not found or has no media."
                        )
                    msg = msgs[0]

                    mode = "ab" if local_size > 0 else "wb"
                    with open(local_path, mode) as f:
                        async for chunk in client.iter_download(
                            msg.media, offset=local_size
                        ):
                            # Check for external stop/cancel
                            if not downloader._running:
                                raise asyncio.CancelledError()

                            f.write(chunk)  # sync write — fine in a thread
                            job.downloaded_bytes += len(chunk)

                            now = time.monotonic()
                            elapsed = now - last_update[0]
                            if elapsed >= 0.2:
                                total_elapsed = now - start_time
                                bytes_since_start = job.downloaded_bytes - local_size
                                job.speed = bytes_since_start / total_elapsed if total_elapsed > 0 else 0.0
                                remaining = job.file_size - job.downloaded_bytes
                                job.eta = remaining / job.speed if job.speed > 0 else float("inf")
                                job.progress = (
                                    (job.downloaded_bytes / job.file_size * 100.0)
                                    if job.file_size > 0 else 0.0
                                )
                                last_update[0] = now
                                for cb in downloader.on_progress:
                                    try:
                                        cb(job)
                                    except Exception:
                                        pass
                        f.flush()

                finally:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass

            try:
                thread_loop.run_until_complete(_async_body())
            except Exception as e:
                exc_holder[0] = e
            finally:
                try:
                    thread_loop.close()
                except Exception:
                    pass
                asyncio.set_event_loop(None)

            if exc_holder[0] is not None:
                raise exc_holder[0]
            return local_path

        # Await the thread from Textual's loop (non-blocking for Textual)
        if not self._executor:
            raise RuntimeError("Downloader not started.")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, _thread_download)

        # ── Verify and finalize ───────────────────────────────────────────
        if not os.path.exists(local_path):
            raise ValueError("Download finished but file not found on disk.")

        actual_size = os.path.getsize(local_path)
        if actual_size != job.file_size:
            try:
                os.remove(local_path)
            except OSError:
                pass
            raise ValueError(
                f"File size mismatch: expected {job.file_size} bytes, got {actual_size}."
            )

        job.status = "completed"
        job.progress = 100.0
        job.downloaded_bytes = job.file_size
        job.speed = 0.0
        job.eta = 0.0

        try:
            await db.update_download_status(
                job.message_id, "completed", job.file_size, local_path
            )
            await db.record_download_history(
                job.message_id, job.filename, job.file_size, local_path
            )
        except Exception:
            pass

        for cb in self.on_progress:
            try:
                cb(job)
            except Exception:
                pass
        for cb in self.on_completed:
            try:
                cb(job.message_id, local_path)
            except Exception:
                pass
