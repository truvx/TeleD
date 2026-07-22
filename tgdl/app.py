import asyncio
import os
import sys
from typing import Optional
from textual.app import App

import tgdl.config as config
from tgdl.telegram_client import TelegramClientWrapper
from tgdl.database import init_db
from tgdl.browser import Browser
from tgdl.downloader import Downloader
from tgdl.screens.main_screen import MainScreen
from tgdl.services.container import container
from tgdl.logger import get_logger

logger = get_logger()

class TeleDApp(App):
    """The main Textual application class for TeleD orchestrating DI services."""
    TITLE = "TeleD - Telegram Downloader"
    theme = "textual-dark"
    
    def __init__(self, client_wrapper: Optional[TelegramClientWrapper] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.client_wrapper = client_wrapper or TelegramClientWrapper()
        self.browser = Browser(self.client_wrapper)
        self.downloader = Downloader(self.client_wrapper)
        
        container.register(TelegramClientWrapper, self.client_wrapper)
        container.register(Browser, self.browser)
        container.register(Downloader, self.downloader)
        
    async def on_mount(self) -> None:
        logger.info("Initializing database schema...")
        await init_db()
        logger.info("Connecting Telegram client...")
        await self.client_wrapper.connect()
        logger.info("Launching MainScreen TUI dashboard...")
        await self.push_screen(MainScreen(self.browser, self.downloader))

    async def on_unmount(self) -> None:
        logger.info("Shutting down TeleD services gracefully...")
        await self.downloader.stop()
        await self.client_wrapper.disconnect()

def prompt_credentials() -> None:
    """Prompt the user for API ID and Hash if not present, and save to .env."""
    print("=== TeleD Configuration Setup ===")
    print("Please generate your Telegram API credentials at: https://my.telegram.org/")
    try:
        api_id = input("Enter API ID (integer): ").strip()
        api_hash = input("Enter API Hash (string): ").strip()
        if not api_id.isdigit():
            print("Error: API ID must be an integer.")
            sys.exit(1)
        
        env_path = config.BASE_DIR / ".env"
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"TELEGRAM_API_ID={api_id}\n")
            f.write(f"TELEGRAM_API_HASH={api_hash}\n")
        print(f"Credentials successfully saved to {env_path}!\n")
        config.reload_config()
    except (KeyboardInterrupt, SystemExit):
        print("\nSetup cancelled.")
        sys.exit(1)

async def check_and_login() -> None:
    """Verify session authorization and execute console login if needed."""
    client_wrapper = TelegramClientWrapper()
    try:
        is_auth = await client_wrapper.connect()
        if not is_auth:
            await client_wrapper.authorize_interactive()
    except Exception as e:
        logger.error(f"Error during Telegram login: {e}")
        print(f"Error during Telegram login: {e}")
        sys.exit(1)
    finally:
        await client_wrapper.disconnect()

def main() -> None:
    if not config.is_config_valid():
        prompt_credentials()
        config.reload_config()
        if not config.is_config_valid():
            print("Configuration invalid. Exiting.")
            sys.exit(1)
            
    asyncio.run(check_and_login())
    app = TeleDApp()
    app.run()

if __name__ == "__main__":
    main()
