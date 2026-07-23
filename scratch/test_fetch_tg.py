import asyncio
import sys
import tgdl.config as config
from tgdl.telegram_client import TelegramClientWrapper

async def test_fetch():
    print("Connecting wrapper...")
    client = TelegramClientWrapper()
    try:
        is_auth = await client.connect()
        print(f"Is authorized: {is_auth}")
        if not is_auth:
            print("Not authorized!")
            return
        me = await client.get_me()
        print(f"User: {me}")
        print("Fetching media messages from Saved Messages ('me')...")
        msgs = await client.fetch_media_messages(min_id=0)
        print(f"Found {len(msgs)} media messages!")
        for m in msgs[:5]:
            print(f" - #{m.message_id}: {m.filename} ({m.file_size} bytes)")
    except Exception as e:
        print(f"Error fetching: {type(e).__name__}: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(test_fetch())
