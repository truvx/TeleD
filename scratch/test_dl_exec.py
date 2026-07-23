import asyncio
import sys
from tgdl.telegram_client import TelegramClientWrapper
from tgdl.downloader import Downloader

async def test_dl():
    client = TelegramClientWrapper()
    print("Connecting client...")
    await client.connect()
    print("Creating downloader...")
    dl = Downloader(client)
    dl.start()
    msg_id = 70778 # One Piece (Dub) - 105
    print(f"Adding message #{msg_id} to queue...")
    await dl.add_to_queue(msg_id)
    print("Waiting 10s to observe download progress...")
    for i in range(10):
        await asyncio.sleep(1)
        job = dl.active_jobs.get(msg_id)
        if job:
            print(f"Sec {i+1}: status={job.status}, progress={job.progress:.1f}%, bytes={job.downloaded_bytes}, speed={job.speed}")
        else:
            print(f"Sec {i+1}: Job finished or removed from active_jobs")

    await dl.stop()
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(test_dl())
