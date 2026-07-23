import asyncio
import traceback
from tgdl.telegram_client import TelegramClientWrapper
from tgdl.downloader import Downloader
from tgdl.database import init_db

async def debug_dl():
    print("=== TESTING PENDING DOWNLOAD FOR MSG #41903 ===")
    await init_db()
    wrapper = TelegramClientWrapper()
    is_auth = await wrapper.connect()
    print(f"1. Connected: is_auth={is_auth}")
    
    dl = Downloader(wrapper)
    dl.start()
    
    msg_id = 41903
    print(f"2. Adding message #{msg_id} to queue...")
    await dl.add_to_queue(msg_id)
    
    for i in range(10):
        await asyncio.sleep(1)
        j = dl.active_jobs.get(msg_id)
        if j:
            print(f"   Sec {i+1}: status='{j.status}', bytes={j.downloaded_bytes}/{j.file_size}, err='{j.error_msg}'")
        else:
            print(f"   Sec {i+1}: Job finished or removed from active_jobs")

    await dl.stop()
    await wrapper.disconnect()
    print("=== DEBUG END ===")

if __name__ == "__main__":
    asyncio.run(debug_dl())
