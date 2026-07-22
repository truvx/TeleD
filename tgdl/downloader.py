import asyncio
import os
import time
import socket
from typing import Callable, Dict, List, Optional
import aiofiles
from telethon.errors.rpcerrorlist import FloodWaitError
from telethon.errors import AuthKeyUnregisteredError, SessionRevokedError, UserDeactivatedError, AuthKeyInvalidError, RPCError

import tgdl.config as config
from tgdl.database import get_cached_messages, update_download_status, record_download_history
from tgdl.models import DownloadJob, MessageMetadata
from tgdl.telegram_client import TelegramClientWrapper

class Downloader:
    """Production download engine supporting streaming, resume, corruption checks, safety, and error handling."""

    def __init__(self, client_wrapper: TelegramClientWrapper, concurrency: Optional[int] = None) -> None:
        self.client_wrapper = client_wrapper
        self.concurrency = concurrency or config.CONCURRENT_DOWNLOADS
        self.queue: asyncio.Queue[int] = asyncio.Queue()
        self.queued_ids: set[int] = set()
        self.active_jobs: Dict[int, DownloadJob] = {}
        self.workers: List[asyncio.Task] = []
        self._running = False
        self.is_paused = False
        
        self.on_progress: List[Callable[[DownloadJob], None]] = []
        self.on_completed: List[Callable[[int, str], None]] = []
        self.on_failed: List[Callable[[int, str], Optional[str]]] = []

    def start(self) -> None:
        if self._running: return
        self._running = True
        os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
        asyncio.create_task(self.restore_queue_from_db())
        self.workers = [asyncio.create_task(self._worker()) for _ in range(self.concurrency)]

    async def stop(self) -> None:
        self._running = False
        for worker in self.workers: worker.cancel()
        if self.workers: await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers = []
        for msg_id, job in list(self.active_jobs.items()):
            await update_download_status(msg_id, "pending", job.downloaded_bytes)
        self.active_jobs.clear()

    async def restore_queue_from_db(self) -> None:
        all_cached = await get_cached_messages()
        for msg in all_cached:
            if msg.download_status in ("pending", "paused"): await self.add_to_queue(msg.message_id)

    async def add_to_queue(self, message_id: int) -> None:
        if message_id in self.queued_ids or message_id in self.active_jobs: return
        self.queued_ids.add(message_id)
        status = "paused" if self.is_paused else "pending"
        await update_download_status(message_id, status, 0)
        await self.queue.put(message_id)

    async def pause_queue(self) -> None:
        self.is_paused = True
        for msg_id, job in list(self.active_jobs.items()):
            job.status = "paused"
            await update_download_status(msg_id, "paused", job.downloaded_bytes)

    async def resume_queue(self) -> None:
        self.is_paused = False
        for msg_id, job in list(self.active_jobs.items()):
            if job.status == "paused":
                job.status = "pending"
                await update_download_status(msg_id, "pending", job.downloaded_bytes)

    async def cancel_queue(self) -> None:
        while not self.queue.empty():
            try:
                msg_id = self.queue.get_nowait()
                await update_download_status(msg_id, "cancelled", 0)
            except Exception: break
        self.queued_ids.clear()
        for msg_id in list(self.active_jobs.keys()):
            await update_download_status(msg_id, "cancelled", 0)
        self.active_jobs.clear()

    async def retry_failed(self) -> None:
        all_cached = await get_cached_messages()
        for msg in all_cached:
            if msg.download_status == "failed": await self.add_to_queue(msg.message_id)

    async def _worker(self) -> None:
        while self._running:
            try:
                if self.is_paused:
                    await asyncio.sleep(0.5)
                    continue

                msg_id = await self.queue.get()
                self.queued_ids.discard(msg_id)
                
                db_messages = await get_cached_messages(search_query=str(msg_id), sort_by="message_id")
                msg_meta = next((m for m in db_messages if m.message_id == msg_id), None)
                if not msg_meta:
                    self.queue.task_done()
                    continue
                
                job = DownloadJob(message_id=msg_id, filename=msg_meta.filename, file_size=msg_meta.file_size, downloaded_bytes=0, status="pending")
                self.active_jobs[msg_id] = job
                
                success = False
                while job.retries <= job.max_retries and not success and not self.is_paused:
                    try:
                        await self._download_file(job)
                        success = True
                    except asyncio.CancelledError:
                        await update_download_status(msg_id, "cancelled", job.downloaded_bytes)
                        raise
                    except FloodWaitError as e:
                        job.status = f"flood wait ({e.seconds}s)"
                        await update_download_status(msg_id, "pending", job.downloaded_bytes)
                        await asyncio.sleep(e.seconds + 1)
                    except PermissionError:
                        job.status, job.error_msg = "failed", "Permission Denied: Cannot write to download folder."
                        await update_download_status(msg_id, "failed", job.downloaded_bytes)
                        for cb in self.on_failed: cb(msg_id, job.error_msg)
                        break
                    except OSError as e:
                        if getattr(e, "errno", 0) == 28 or "No space left" in str(e):
                            job.status, job.error_msg = "failed", "Disk Full: No space left on target disk."
                            await update_download_status(msg_id, "failed", job.downloaded_bytes)
                            for cb in self.on_failed: cb(msg_id, job.error_msg)
                            break
                        else:
                            await self._handle_transient_error(job, str(e))
                    except (AuthKeyUnregisteredError, SessionRevokedError, UserDeactivatedError, AuthKeyInvalidError):
                        job.status, job.error_msg = "failed", "Session Expired: Please re-authorize your session."
                        await update_download_status(msg_id, "failed", job.downloaded_bytes)
                        for cb in self.on_failed: cb(msg_id, job.error_msg)
                        break
                    except (asyncio.TimeoutError, socket.error, ConnectionError) as e:
                        await self._handle_transient_error(job, f"Internet Disconnected / Timeout: {e}")
                    except ValueError as e:
                        if "File size mismatch" in str(e) or "corrupted" in str(e).lower():
                            await self._handle_transient_error(job, f"Corrupted Download: {e}")
                        else:
                            job.status, job.error_msg = "failed", str(e)
                            await update_download_status(msg_id, "failed", job.downloaded_bytes)
                            for cb in self.on_failed: cb(msg_id, str(e))
                            break
                    except Exception as e:
                        await self._handle_transient_error(job, str(e))
                
                self.active_jobs.pop(msg_id, None)
                self.queue.task_done()
            except asyncio.CancelledError: break
            except Exception: await asyncio.sleep(1)

    async def _handle_transient_error(self, job: DownloadJob, err_text: str) -> None:
        job.retries += 1
        if job.retries <= job.max_retries:
            job.status = f"retry {job.retries}/{job.max_retries}"
            await update_download_status(job.message_id, "pending", job.downloaded_bytes)
            await asyncio.sleep(2 ** job.retries)
        else:
            job.status, job.error_msg = "failed", err_text
            await update_download_status(job.message_id, "failed", job.downloaded_bytes)
            for cb in self.on_failed: cb(job.message_id, err_text)

    async def _download_file(self, job: DownloadJob) -> None:
        if not self.client_wrapper.client: raise RuntimeError("Telegram client not connected.")
        msgs = await self.client_wrapper.client.get_messages("me", ids=[job.message_id])
        if not msgs or not msgs[0] or not msgs[0].media: raise ValueError("Telegram message or media no longer available.")
        msg = msgs[0]

        local_path = os.path.join(config.DOWNLOAD_DIR, job.filename)
        local_size = 0

        if os.path.exists(local_path):
            local_size = os.path.getsize(local_path)
            if local_size >= job.file_size:
                if local_size == job.file_size:
                    job.status, job.progress, job.downloaded_bytes = "completed", 100.0, job.file_size
                    await update_download_status(job.message_id, "completed", job.file_size, local_path)
                    await record_download_history(job.message_id, job.filename, job.file_size, local_path)
                    for cb in self.on_completed: cb(job.message_id, local_path)
                    return
                else:
                    local_size = 0
                    try: os.remove(local_path)
                    except OSError: pass
            else:
                local_size = (local_size // 4096) * 4096
                with open(local_path, "r+b") as f: f.truncate(local_size)

        job.status, job.downloaded_bytes = "downloading", local_size
        await update_download_status(job.message_id, "downloading", local_size)

        mode = "ab" if local_size > 0 else "wb"
        start_time = time.time()
        last_time, last_bytes = start_time, local_size

        try:
            async with aiofiles.open(local_path, mode) as f:
                async for chunk in self.client_wrapper.client.iter_download(msg.media, offset=local_size):
                    if self.is_paused:
                        job.status = "paused"
                        await update_download_status(job.message_id, "paused", job.downloaded_bytes)
                        return

                    await f.write(chunk)
                    job.downloaded_bytes += len(chunk)
                    
                    now = time.time()
                    elapsed = now - last_time
                    if elapsed >= 0.1:
                        bytes_diff = job.downloaded_bytes - last_bytes
                        current_speed = bytes_diff / elapsed
                        job.speed = current_speed
                        job.avg_speed = current_speed if job.avg_speed == 0.0 else (0.8 * job.avg_speed + 0.2 * current_speed)
                        
                        remaining = job.file_size - job.downloaded_bytes
                        job.eta = remaining / job.avg_speed if job.avg_speed > 0 else float("inf")
                        job.progress = (job.downloaded_bytes / job.file_size) * 100.0 if job.file_size > 0 else 0.0
                        
                        last_time, last_bytes = now, job.downloaded_bytes
                        await update_download_status(job.message_id, "downloading", job.downloaded_bytes)
                        for cb in self.on_progress: cb(job)
                await f.flush()
        except asyncio.CancelledError:
            await update_download_status(job.message_id, "cancelled", job.downloaded_bytes)
            if os.path.exists(local_path) and os.path.getsize(local_path) == 0:
                try: os.remove(local_path)
                except OSError: pass
            raise

        actual_size = os.path.getsize(local_path)
        if actual_size != job.file_size:
            try: os.remove(local_path)
            except OSError: pass
            raise ValueError(f"Corrupted Download: expected {job.file_size} bytes, received {actual_size} bytes.")

        job.status, job.progress, job.speed, job.eta = "completed", 100.0, 0.0, 0.0
        await update_download_status(job.message_id, "completed", job.file_size, local_path)
        await record_download_history(job.message_id, job.filename, job.file_size, local_path)
        
        for cb in self.on_progress: cb(job)
        for cb in self.on_completed: cb(job.message_id, local_path)
