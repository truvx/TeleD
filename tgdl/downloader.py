import asyncio
import os
import time
from typing import Callable, Dict, List, Optional
import aiofiles
from tgdl.config import DOWNLOAD_DIR, CONCURRENT_DOWNLOADS
from tgdl.database import get_cached_messages, update_download_status, get_message
from tgdl.models import DownloadJob, MessageMetadata
from tgdl.telegram_client import TelegramClientWrapper

class Downloader:
    def __init__(self, client_wrapper: TelegramClientWrapper, concurrency: int = CONCURRENT_DOWNLOADS) -> None:
        self.client_wrapper = client_wrapper
        self.concurrency = concurrency
        self.queue: asyncio.Queue[int] = asyncio.Queue()
        self.queued_ids: set[int] = set()
        self.active_jobs: Dict[int, DownloadJob] = {}
        self.workers: List[asyncio.Task] = []
        self._running = False
        
        self.on_progress: List[Callable[[DownloadJob], None]] = []
        self.on_completed: List[Callable[[int, str], None]] = []  # msg_id, path
        self.on_failed: List[Callable[[int, str], None]] = []     # msg_id, reason

    def start(self) -> None:
        """Start the background download workers."""
        if self._running:
            return
        self._running = True
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        self.workers = [asyncio.create_task(self._worker()) for _ in range(self.concurrency)]

    async def stop(self) -> None:
        """Cancel and stop all download workers."""
        self._running = False
        for worker in self.workers:
            worker.cancel()
        
        # Wait for workers to shut down
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers = []
        
        # Mark all active jobs as pending in the database so they can resume next time
        for msg_id, job in list(self.active_jobs.items()):
            await update_download_status(msg_id, "pending", job.downloaded_bytes)
        self.active_jobs.clear()

    async def add_to_queue(self, message_id: int) -> None:
        """Add a message ID to the download queue."""
        if message_id in self.queued_ids or message_id in self.active_jobs:
            return
        self.queued_ids.add(message_id)
        await update_download_status(message_id, "pending", 0)
        await self.queue.put(message_id)

    async def _worker(self) -> None:
        """Background worker thread processing downloads."""
        while self._running:
            try:
                msg_id = await self.queue.get()
                self.queued_ids.discard(msg_id)
                
                # Fetch fresh metadata from database
                db_messages = await get_cached_messages(search_query=str(msg_id), sort_by="message_id")
                # Filter down to the exact message ID
                msg_meta = next((m for m in db_messages if m.message_id == msg_id), None)
                
                if not msg_meta:
                    self.queue.task_done()
                    continue
                
                # Create download job state
                job = DownloadJob(
                    message_id=msg_id,
                    filename=msg_meta.filename,
                    file_size=msg_meta.file_size,
                    downloaded_bytes=0,
                    status="pending"
                )
                self.active_jobs[msg_id] = job
                
                try:
                    await self._download_file(job)
                except asyncio.CancelledError:
                    # Update status in db on termination
                    await update_download_status(msg_id, "pending", job.downloaded_bytes)
                    raise
                except Exception as e:
                    job.status = "failed"
                    await update_download_status(msg_id, "failed", job.downloaded_bytes)
                    for cb in self.on_failed:
                        cb(msg_id, str(e))
                finally:
                    self.active_jobs.pop(msg_id, None)
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1)

    async def _download_file(self, job: DownloadJob) -> None:
        """Downloads a single file from Telegram with resume support."""
        if not self.client_wrapper.client:
            raise RuntimeError("Telegram client not connected.")

        # Get actual Telegram message
        msgs = await self.client_wrapper.client.get_messages("me", ids=[job.message_id])
        if not msgs or not msgs[0] or not msgs[0].media:
            raise ValueError("Telegram message or media no longer available.")
        msg = msgs[0]

        local_path = os.path.join(DOWNLOAD_DIR, job.filename)
        local_size = 0

        # Implement Resume: Align offset to nearest 4KB (4096 bytes)
        if os.path.exists(local_path):
            local_size = os.path.getsize(local_path)
            if local_size >= job.file_size:
                if local_size == job.file_size:
                    # File already matches total size, skip download
                    job.status = "completed"
                    job.progress = 100.0
                    job.downloaded_bytes = job.file_size
                    await update_download_status(job.message_id, "completed", job.file_size, local_path)
                    for cb in self.on_completed:
                        cb(job.message_id, local_path)
                    return
                else:
                    # Overwrite file if local file is inexplicably larger
                    local_size = 0
                    try:
                        os.remove(local_path)
                    except OSError:
                        pass
            else:
                # Align offset to lower 4096-byte boundary to satisfy Telegram API requirements
                local_size = (local_size // 4096) * 4096
                with open(local_path, "r+b") as f:
                    f.truncate(local_size)

        job.status = "downloading"
        job.downloaded_bytes = local_size
        await update_download_status(job.message_id, "downloading", local_size)

        # Notify UI of status transition
        for cb in self.on_progress:
            cb(job)

        mode = "ab" if local_size > 0 else "wb"
        start_time = time.time()
        last_time = start_time
        last_bytes = local_size

        async with aiofiles.open(local_path, mode) as f:
            # Download file in chunks using client.iter_download
            async for chunk in self.client_wrapper.client.iter_download(msg.media, offset=local_size):
                await f.write(chunk)
                job.downloaded_bytes += len(chunk)
                
                # Smooth speed estimation and ETA calculation
                now = time.time()
                elapsed = now - last_time
                if elapsed >= 0.5:
                    bytes_diff = job.downloaded_bytes - last_bytes
                    current_speed = bytes_diff / elapsed
                    
                    if job.speed == 0.0:
                        job.speed = current_speed
                    else:
                        job.speed = 0.7 * job.speed + 0.3 * current_speed
                        
                    remaining = job.file_size - job.downloaded_bytes
                    job.eta = remaining / job.speed if job.speed > 0 else float("inf")
                    job.progress = (job.downloaded_bytes / job.file_size) * 100.0 if job.file_size > 0 else 0.0
                    
                    last_time = now
                    last_bytes = job.downloaded_bytes
                    
                    # Update DB (avoid excessive DB writes, update status/bytes)
                    await update_download_status(job.message_id, "downloading", job.downloaded_bytes)
                    
                    for cb in self.on_progress:
                        cb(job)

        # Success completion
        job.status = "completed"
        job.progress = 100.0
        job.speed = 0.0
        job.eta = 0.0
        await update_download_status(job.message_id, "completed", job.file_size, local_path)
        
        for cb in self.on_progress:
            cb(job)
        for cb in self.on_completed:
            cb(job.message_id, local_path)
