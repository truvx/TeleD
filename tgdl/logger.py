import logging
import os
from typing import Optional
from tgdl.constants import DEFAULT_LOG_PATH

_logger: Optional[logging.Logger] = None

def setup_logger(log_level: Optional[int] = None, log_file: Optional[str] = None) -> logging.Logger:
    """Initialize and return the central TeleD logger instance with level overrides."""
    global _logger
    if _logger is not None:
        return _logger
        
    env_level_str = os.getenv("TELED_LOG_LEVEL", "INFO").upper()
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
    resolved_level = log_level or level_map.get(env_level_str, logging.INFO)

    _logger = logging.getLogger("TeleD")
    _logger.setLevel(resolved_level)
    _logger.propagate = False
    
    if _logger.handlers:
        return _logger
        
    target_log = log_file or DEFAULT_LOG_PATH
    log_dir = os.path.dirname(target_log)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    file_handler = logging.FileHandler(target_log, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(resolved_level)
    _logger.addHandler(file_handler)
    
    return _logger

def get_logger() -> logging.Logger:
    """Retrieve the global TeleD logger instance."""
    if _logger is None:
        return setup_logger()
    return _logger
