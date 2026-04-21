import logging
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT= "%Y-%m-%d %H:%M:%S"

def configure_logging(log_level: str = "INFO") -> None:
    root_logger = logging.getLogger()

    if root_logger.handlers:
        root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT,datefmt=DATE_FORMAT))
    root_logger.addHandler(handler)

    root_logger.setLevel(log_level.upper())

    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.access").propagate = True


def get_logger(name:str) -> logging.Logger:
    return logging.getLogger(name)