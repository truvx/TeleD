import asyncio
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
    """TeleD — btop-style Telegram file manager TUI."""

    TITLE = "TeleD - Telegram Downloader"

    def __init__(self, client_wrapper: Optional[TelegramClientWrapper] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.client_wrapper = client_wrapper or TelegramClientWrapper()
        self.browser = Browser(self.client_wrapper)
        self.downloader = Downloader(self.client_wrapper)
        container.register(TelegramClientWrapper, self.client_wrapper)
        container.register(Browser, self.browser)
        container.register(Downloader, self.downloader)

    async def on_mount(self) -> None:
        await init_db()
        await self.push_screen(MainScreen(self.browser, self.downloader))

    async def on_unmount(self) -> None:
        await self.downloader.stop()
        await self.client_wrapper.disconnect()


def prompt_credentials() -> None:
    print("\n=== TeleD First-Time Setup ===")
    print("Get your API credentials at: https://my.telegram.org/")
    try:
        api_id = input("Enter API ID (integer): ").strip()
        api_hash = input("Enter API Hash (string): ").strip()
        if not api_id.isdigit():
            print("Error: API ID must be a number.")
            sys.exit(1)
        env_path = config.BASE_DIR / ".env"
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"TELEGRAM_API_ID={api_id}\n")
            f.write(f"TELEGRAM_API_HASH={api_hash}\n")
        print(f"Saved to {env_path}\n")
        config.reload_config()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        sys.exit(0)


async def run_login() -> None:
    """Run interactive Telegram login in terminal before TUI opens."""
    client = TelegramClientWrapper()
    try:
        is_auth = await client.connect()
        if not is_auth:
            print("Logging in to Telegram (enter phone number when prompted)...")
            await client.authorize_interactive()
            print("Login successful!\n")
        else:
            print("Session found, loading TeleD...\n")
    except Exception as e:
        print(f"Warning: {e}")
        print("Opening TeleD in offline mode. Press Ctrl+R inside to sync when connected.\n")
    finally:
        try:
            await client.disconnect()
            await asyncio.sleep(0.1)
        except Exception:
            pass


def main() -> None:
    if not config.is_config_valid():
        prompt_credentials()
        if not config.is_config_valid():
            print("Invalid configuration. Exiting.")
            sys.exit(1)

    asyncio.run(run_login())
    TeleDApp().run()


if __name__ == "__main__":
    main()
