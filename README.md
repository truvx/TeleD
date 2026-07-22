# TeleD - Telegram Downloader

**TeleD** is a production-quality, asynchronous terminal interface (TUI) for browsing and downloading media files from Telegram **Saved Messages** (`me`).

Designed with a modern terminal aesthetic inspired by **LazyGit**, **Lazydocker**, and **btop**.

---

## Features

- **Saved Messages Browser**: Scans and caches downloadable media (Videos, PDFs, ZIP/RAR, Images, Audio, Documents).
- **Instant Real-Time Search**: Search by filename, extension (`*.mkv`, `*.pdf`, `*.zip`, `*.iso`), date, or type on every keystroke.
- **Header & Column Sorting**: Click column headers (`Filename`, `Ext`, `Size`, `Date`, `ID`) or press `O` to flip sort order instantly.
- **Advanced Download Engine**:
  - Resumes partial downloads automatically with 4KB chunk boundary alignment.
  - Skips already existing files matching total size.
  - Multi-item download queue with EWMA speed and ETA calculation.
  - Automatic retry mechanism (max 5 retries) with FloodWait handling.
- **Keyboard & Mouse Controls**:
  - `F`: Focus Search Bar
  - `Space`: Toggle row selection
  - `Ctrl+A`: Select all visible files
  - `Ctrl+D`: Clear selection
  - `Enter`: Download selected files
  - `Delete` / `Backspace`: Remove entry from cache
  - `Esc`: Clear search filter & refocus table
  - `R`: Sync/Refresh files from Telegram
  - `T`: Toggle Dark / Light theme
  - `Q`: Quit application
  - Mouse wheel scrolling & row selection enabled out of the box.
- **High Performance & Zero Freeze Guarantee**:
  - SQLite WAL mode and multi-column indexes for 50,000+ files.
  - Non-blocking async IO everywhere using `asyncio.to_thread` and `aiofiles`.

---

## Installation & Setup

1. **Install Dependencies**:
```bash
python3 -m pip install -r tgdl/requirements.txt
```

2. **Launch Application**:
```bash
python3 -m tgdl.app
```
If `.env` is missing, TeleD will prompt for your `API_ID` and `API_HASH` on first run and save them automatically.

---

## Architecture Overview

```
tgdl/
├── app.py              # Application entry point & TeleDApp class
├── config.py           # Configuration parser & path resolution
├── constants.py        # System constants & defaults
├── settings.py         # Persistent settings manager
├── logger.py           # Centralized logging setup
├── database.py         # SQLite WAL schema & indexed queries
├── telegram_client.py  # Telethon client wrapper & auth
├── downloader.py       # Async download queue & resume engine
├── cache.py            # Memory & SQLite cache provider
├── models.py           # Domain dataclasses (MessageMetadata, DownloadJob)
├── search.py           # SearchEngine interface & query parser
├── utils.py            # Facade for utility helpers
├── widgets/            # UI widgets (DownloadProgressRow, StatCard, CounterBar)
├── screens/            # UI screens (MainScreen, ErrorModal)
├── services/           # Dependency Injection & BaseService
├── repositories/       # MessageRepository data access layer
└── requirements.txt    # Project dependencies
```

---

## License
MIT License
