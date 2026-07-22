import logging
import os
from typing import Optional
from tgdl.constants import DEFAULT_LOG_PATH

_logger: Optional[logging.Logger] = None

def setup_logger(log_level: int = logging.INFO, log_file: Optional[str] = None) -> logging.Logger:
    """Initialize and return the central TeleD logger instance."""
    global _logger
    if _logger is not None:
        return _logger
        
    _logger = logging.getLogger("TeleD")
    _logger.setLevel(log_level)
    _logger.propagate = False
    
    # Avoid duplicate handlers
    if _logger.handlers:
        return _logger
        
    target_log = log_file or DEFAULT_LOG_PATH
    log_dir = os.path.dirname(target_log)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # File Handler
    file_handler = logging.FileHandler(target_log, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)
    _logger.addHandler(file_handler)
    
    return _logger

def get_logger() -> logging.Logger:
    """Retrieve the global TeleD logger instance."""
    if _logger is None:
        return setup_logger()
    return _logger
