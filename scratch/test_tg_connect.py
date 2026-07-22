import asyncio
import os
import tgdl.config as config
from telethon import TelegramClient
from telethon.network.connection import ConnectionTcpObfuscated, ConnectionTcpFull, ConnectionTcpIntermediate

async def test_connect():
    print(f"Testing Telegram connection with API_ID={config.API_ID}...")
    session_file = config.TGDL_DIR / "session" / "test_conn.session"
    
    # Mode 1: Default
    print("\n[Mode 1] Testing Default Connection...")
    client1 = TelegramClient(str(session_file), config.API_ID, config.API_HASH, connection_retries=2, timeout=5)
    try:
        await client1.connect()
        print("✓ Mode 1 Connected successfully!")
        await client1.disconnect()
        return
    except Exception as e:
        print(f"✗ Mode 1 Failed: {e}")
        
    # Mode 2: Obfuscated TCP (Bypasses ISP/Firewall packet blocking)
    print("\n[Mode 2] Testing ConnectionTcpObfuscated...")
    client2 = TelegramClient(str(session_file), config.API_ID, config.API_HASH, connection=ConnectionTcpObfuscated, connection_retries=2, timeout=5)
    try:
        await client2.connect()
        print("✓ Mode 2 Connected successfully!")
        await client2.disconnect()
        return
    except Exception as e:
        print(f"✗ Mode 2 Failed: {e}")

    # Mode 3: ConnectionTcpIntermediate
    print("\n[Mode 3] Testing ConnectionTcpIntermediate...")
    client3 = TelegramClient(str(session_file), config.API_ID, config.API_HASH, connection=ConnectionTcpIntermediate, connection_retries=2, timeout=5)
    try:
        await client3.connect()
        print("✓ Mode 3 Connected successfully!")
        await client3.disconnect()
        return
    except Exception as e:
        print(f"✗ Mode 3 Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_connect())
