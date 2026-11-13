import logging
import sys


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configures structured application logging."""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    logger = logging.getLogger("marspath")
    logger.setLevel(numeric_level)

    # Avoid duplicate handlers if reloaded
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(numeric_level)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s:%(module)s:%(lineno)d] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
