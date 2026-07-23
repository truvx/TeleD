"""Production download engine: streaming, resume, corruption checks, and robust error handling."""
import asyncio
import os
import time
import socket
import sqlite3
from typing import Callable, Dict, List, Optional
import aiofiles
from telethon.errors.rpcerrorlist import FloodWaitError
from telethon.errors import (
    AuthKeyUnregisteredError, SessionRevokedError, UserDeactivatedError,
    AuthKeyInvalidError, RPCError
)

import tgdl.config as config
import tgdl.database as db
from tgdl.models import DownloadJob, MessageMetadata
from tgdl.telegram_client import TelegramClientWrapper


class Downloader:
    """Production download engine supporting streaming, resume, corruption checks, and error handling."""

    def __init__(self, client_wrapper: TelegramClientWrapper, concurrency: Optional[int] = None) -> None:
        self.client_wrapper = client_wrapper
        self.concurrency = concurrency or config.CONCURRENT_DOWNLOADS
        self.queue: asyncio.Queue[int] = asyncio.Queue()
        self.active_jobs: Dict[int, DownloadJob] = {}
        self.workers: List[asyncio.Task] = []
        self._running = False
        self.is_paused = False

        self.on_progress: List[Callable[[DownloadJob], None]] = []
        self.on_completed: List[Callable[[int, str], None]] = []
        self.on_failed: List[Callable[[int, str], Optional[str]]] = []

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
        self.workers = [asyncio.create_task(self._worker()) for _ in range(self.concurrency)]

    async def stop(self) -> None:
        self._running = False
        for worker in self.workers:
            worker.cancel()
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers = []
        for msg_id, job in list(self.active_jobs.items()):
            await db.update_download_status(msg_id, "pending", job.downloaded_bytes)
        self.active_jobs.clear()

    async def add_to_queue(self, message_id: int) -> bool:
        """Add a file to the download queue. Returns True if added, False if already queued/downloading."""
        if message_id in self.active_jobs:
            return False  # Already queued or downloading

        msg_meta = await db.get_message(message_id)
        if not msg_meta:
            return False

        status = "paused" if self.is_paused else "queued"
        job = DownloadJob(
            message_id=message_id,
            filename=msg_meta.filename,
            file_size=msg_meta.file_size,
            downloaded_bytes=0,
            status=status,
        )
        self.active_jobs[message_id] = job
        await db.update_download_status(message_id, status, 0)

        if not self.is_paused:
            await self.queue.put(message_id)
        return True

    async def pause_queue(self) -> None:
        self.is_paused = True
        for msg_id, job in list(self.active_jobs.items()):
            if job.status not in ("downloading", "completed", "failed"):
                job.status = "paused"
                await db.update_download_status(msg_id, "paused", job.downloaded_bytes)

    async def resume_queue(self) -> None:
        self.is_paused = False
        for msg_id, job in list(self.active_jobs.items()):
            if job.status == "paused":
                job.status = "queued"
                await db.update_download_status(msg_id, "pending", job.downloaded_bytes)
                await self.queue.put(msg_id)

    async def cancel_queue(self) -> None:
        # Drain the async queue
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except Exception:
                break

        # Cancel all active jobs
        for msg_id in list(self.active_jobs.keys()):
            await db.update_download_status(msg_id, "cancelled", 0)
        self.active_jobs.clear()

    async def retry_failed(self) -> None:
        all_cached = await db.get_cached_messages()
        for msg in all_cached:
            if msg.download_status == "failed":
                await self.add_to_queue(msg.message_id)

    async def _worker(self) -> None:
        while self._running:
            try:
                if self.is_paused:
                    await asyncio.sleep(0.3)
                    continue

                try:
                    msg_id = await asyncio.wait_for(self.queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                job = self.active_jobs.get(msg_id)
                if not job:
                    # Job was cancelled before worker picked it up
                    try:
                        self.queue.task_done()
                    except Exception:
                        pass
                    continue

                # Skip if paused while waiting
                if self.is_paused:
                    job.status = "paused"
                    try:
                        self.queue.task_done()
                    except Exception:
                        pass
                    continue

                job.status = "downloading"
                success = False
                while job.retries <= job.max_retries and not success and not self.is_paused:
                    try:
                        await self._download_file(job)
                        success = True
                    except asyncio.CancelledError:
                        await db.update_download_status(msg_id, "cancelled", job.downloaded_bytes)
                        raise
                    except FloodWaitError as e:
                        job.status = f"flood wait ({e.seconds}s)"
                        await db.update_download_status(msg_id, "pending", job.downloaded_bytes)
                        await asyncio.sleep(e.seconds + 1)
                    except PermissionError:
                        job.status = "failed"
                        job.error_msg = "Permission Denied: Cannot write to download folder."
                        await db.update_download_status(msg_id, "failed", job.downloaded_bytes)
                        for cb in self.on_failed:
                            cb(msg_id, job.error_msg)
                        break
                    except OSError as e:
                        if getattr(e, "errno", 0) == 28 or "No space left" in str(e):
                            job.status = "failed"
                            job.error_msg = "Disk Full: No space left on target disk."
                            await db.update_download_status(msg_id, "failed", job.downloaded_bytes)
                            for cb in self.on_failed:
                                cb(msg_id, job.error_msg)
                            break
                        else:
                            await self._handle_transient_error(job, str(e))
                    except (AuthKeyUnregisteredError, SessionRevokedError, UserDeactivatedError, AuthKeyInvalidError):
                        job.status = "failed"
                        job.error_msg = "Session Expired: Please re-authorize your session."
                        await db.update_download_status(msg_id, "failed", job.downloaded_bytes)
                        for cb in self.on_failed:
                            cb(msg_id, job.error_msg)
                        break
                    except (asyncio.TimeoutError, socket.error, ConnectionError) as e:
                        await self._handle_transient_error(job, f"Network Error: {e}")
                    except ValueError as e:
                        if "File size mismatch" in str(e) or "corrupted" in str(e).lower():
                            await self._handle_transient_error(job, f"Corrupted Download: {e}")
                        else:
                            job.status = "failed"
                            job.error_msg = str(e)
                            await db.update_download_status(msg_id, "failed", job.downloaded_bytes)
                            for cb in self.on_failed:
                                cb(msg_id, str(e))
                            break
                    except Exception as e:
                        await self._handle_transient_error(job, str(e))

                # Grace period — keep card visible for 3s after completion/failure
                if job.status in ("completed", "failed"):
                    await asyncio.sleep(3)

                self.active_jobs.pop(msg_id, None)
                try:
                    self.queue.task_done()
                except Exception:
                    pass

            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1)

    async def _handle_transient_error(self, job: DownloadJob, err_text: str) -> None:
        job.retries += 1
        if job.retries <= job.max_retries:
            job.status = f"retry {job.retries}/{job.max_retries}"
            await db.update_download_status(job.message_id, "pending", job.downloaded_bytes)
            await asyncio.sleep(min(2 ** job.retries, 30))
        else:
            job.status = "failed"
            job.error_msg = err_text
            await db.update_download_status(job.message_id, "failed", job.downloaded_bytes)
            for cb in self.on_failed:
                cb(job.message_id, err_text)

    async def _download_file(self, job: DownloadJob) -> None:
        # Ensure client is connected
        if not self.client_wrapper.client or not self.client_wrapper.client.is_connected():
            await self.client_wrapper.connect()

        client = self.client_wrapper.client

        # Fetch the message from Telegram (Saved Messages)
        msgs = await client.get_messages("me", ids=[job.message_id])
        if not msgs or not msgs[0] or not msgs[0].media:
            raise ValueError(f"Telegram message #{job.message_id} not found or has no media.")
        msg = msgs[0]

        local_path = os.path.join(config.DOWNLOAD_DIR, job.filename)
        local_size = 0

        if os.path.exists(local_path):
            local_size = os.path.getsize(local_path)
            if local_size >= job.file_size:
                if local_size == job.file_size:
                    # Already fully downloaded
                    job.status = "completed"
                    job.progress = 100.0
                    job.downloaded_bytes = job.file_size
                    await db.update_download_status(job.message_id, "completed", job.file_size, local_path)
                    await db.record_download_history(job.message_id, job.filename, job.file_size, local_path)
                    for cb in self.on_completed:
                        cb(job.message_id, local_path)
                    return
                else:
                    # Larger than expected → corrupted, delete and restart
                    local_size = 0
                    try:
                        os.remove(local_path)
                    except OSError:
                        pass
            else:
                # Partial download → align to 4KB block and resume
                local_size = (local_size // 4096) * 4096
                with open(local_path, "r+b") as f:
                    f.truncate(local_size)

        job.status = "downloading"
        job.downloaded_bytes = local_size
        await db.update_download_status(job.message_id, "downloading", local_size)

        mode = "ab" if local_size > 0 else "wb"
        start_time = time.time()
        last_time, last_bytes = start_time, local_size

        try:
            async with aiofiles.open(local_path, mode) as f:
                async for chunk in client.iter_download(msg.media, offset=local_size):
                    if self.is_paused:
                        job.status = "paused"
                        await db.update_download_status(job.message_id, "paused", job.downloaded_bytes)
                        return

                    if not self._running:
                        raise asyncio.CancelledError()

                    await f.write(chunk)
                    job.downloaded_bytes += len(chunk)

                    now = time.time()
                    elapsed = now - last_time
                    if elapsed >= 0.1:
                        bytes_diff = job.downloaded_bytes - last_bytes
                        current_speed = bytes_diff / elapsed
                        job.speed = current_speed
                        job.avg_speed = (
                            current_speed if job.avg_speed == 0.0
                            else (0.8 * job.avg_speed + 0.2 * current_speed)
                        )
                        remaining = job.file_size - job.downloaded_bytes
                        job.eta = remaining / job.avg_speed if job.avg_speed > 0 else float("inf")
                        job.progress = (
                            (job.downloaded_bytes / job.file_size) * 100.0
                            if job.file_size > 0 else 0.0
                        )
                        last_time = now
                        last_bytes = job.downloaded_bytes
                        await db.update_download_status(job.message_id, "downloading", job.downloaded_bytes)
                        for cb in self.on_progress:
                            cb(job)
                await f.flush()

        except asyncio.CancelledError:
            await db.update_download_status(job.message_id, "cancelled", job.downloaded_bytes)
            if os.path.exists(local_path) and os.path.getsize(local_path) == 0:
                try:
                    os.remove(local_path)
                except OSError:
                    pass
            raise

        # Verify file integrity
        actual_size = os.path.getsize(local_path)
        if actual_size != job.file_size:
            try:
                os.remove(local_path)
            except OSError:
                pass
            raise ValueError(
                f"Corrupted Download: expected {job.file_size} bytes, received {actual_size} bytes."
            )

        job.status = "completed"
        job.progress = 100.0
        job.speed = 0.0
        job.eta = 0.0
        await db.update_download_status(job.message_id, "completed", job.file_size, local_path)
        await db.record_download_history(job.message_id, job.filename, job.file_size, local_path)

        for cb in self.on_progress:
            cb(job)
        for cb in self.on_completed:
            cb(job.message_id, local_path)
