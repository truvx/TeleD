from setuptools import setup, find_packages

setup(
    name="teled",
    version="1.0.0",
    description="A modern LazyGit-inspired TUI downloader for Telegram Saved Messages",
    author="TeleD Developers",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "telethon>=1.34.0",
        "textual>=0.50.0",
        "rich>=13.7.0",
        "rapidfuzz>=3.6.0",
        "aiofiles>=23.2.0",
        "python-dotenv>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "teled=tgdl.app:main",
        ],
    },
    python_requires=">=3.9",
)
