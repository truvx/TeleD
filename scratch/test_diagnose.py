import asyncio
import sys
from tgdl.telegram_client import TelegramClientWrapper
from tgdl.browser import Browser
from tgdl.downloader import Downloader

async def diagnose():
    print("1. Creating TelegramClientWrapper...")
    wrapper = TelegramClientWrapper()
    print("2. Calling connect()...")
    try:
        is_auth = await wrapper.connect()
        print(f"   connect() result: is_auth={is_auth}")
        me = await wrapper.get_me()
        print(f"   get_me() result: {me}")
    except Exception as e:
        print(f"   connect() FAILED: {type(e).__name__}: {e}")
        return

    print("3. Testing get_messages('me')...")
    try:
        msgs = await wrapper.client.get_messages("me", limit=5)
        print(f"   Fetched {len(msgs)} messages from 'me'. Total={msgs.total}")
        for m in msgs:
            if m.media:
                print(f"   - Message #{m.id}: filename={m.file.name if m.file else None}, size={m.file.size if m.file else None}")
    except Exception as e:
        print(f"   get_messages FAILED: {type(e).__name__}: {e}")

    print("4. Testing downloader download on message #70778...")
    dl = Downloader(wrapper)
    dl.start()
    await dl.add_to_queue(70778)
    for i in range(5):
        await asyncio.sleep(1)
        job = dl.active_jobs.get(70778)
        if job:
            print(f"   Job status: status={job.status}, progress={job.progress:.1f}%, speed={job.speed}")
        else:
            print(f"   Job completed or removed.")
    await dl.stop()
    await wrapper.disconnect()
    print("Diagnose complete.")

if __name__ == "__main__":
    asyncio.run(diagnose())
