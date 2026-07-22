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
    """TeleD Telegram Downloader — btop-style TUI."""

    TITLE = "TeleD - Telegram Downloader"
    CSS = """
    Screen { background: $background; }
    """

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
        # Connect silently — MainScreen handles offline/disconnected state gracefully
        try:
            await self.client_wrapper.connect()
        except Exception as e:
            logger.warning(f"Telegram connection on startup failed (offline mode): {e}")
        await self.push_screen(MainScreen(self.browser, self.downloader))

    async def on_unmount(self) -> None:
        await self.downloader.stop()
        await self.client_wrapper.disconnect()


def prompt_credentials() -> None:
    """Prompt user for API credentials and write to .env."""
    print("\n=== TeleD First-Time Setup ===")
    print("Get your API credentials from: https://my.telegram.org/")
    try:
        api_id = input("Enter API ID (integer): ").strip()
        api_hash = input("Enter API Hash (string): ").strip()
        if not api_id.isdigit():
            print("Error: API ID must be an integer. Exiting.")
            sys.exit(1)
        env_path = config.BASE_DIR / ".env"
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"TELEGRAM_API_ID={api_id}\n")
            f.write(f"TELEGRAM_API_HASH={api_hash}\n")
        print(f"Saved to {env_path}\n")
        config.reload_config()
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled.")
        sys.exit(0)


async def run_interactive_login() -> None:
    """Run phone/OTP login in terminal before launching TUI."""
    client = TelegramClientWrapper()
    try:
        is_auth = await client.connect()
        if not is_auth:
            print("Logging in to Telegram...")
            await client.authorize_interactive()
            print("Login successful!\n")
    except Exception as e:
        print(f"\nWarning: Could not connect to Telegram: {e}")
        print("TeleD will open in offline mode. Use Ctrl+R inside the app to sync when connected.\n")
    finally:
        await client.disconnect()


def main() -> None:
    # Step 1: Ensure credentials exist
    if not config.is_config_valid():
        prompt_credentials()
        if not config.is_config_valid():
            print("Error: Invalid configuration. Exiting.")
            sys.exit(1)

    # Step 2: Run login flow (non-fatal if network is down)
    asyncio.run(run_interactive_login())

    # Step 3: Launch TUI — always opens regardless of connection state
    app = TeleDApp()
    app.run()


if __name__ == "__main__":
    main()
