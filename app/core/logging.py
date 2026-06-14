"""日志配置。

该文件负责配置应用日志格式和输出位置。生产环境通过 Docker stdout
收集日志，并由 docker-compose.prod.yml 中的 json-file 策略做日志滚动。
"""

import logging
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT= "%Y-%m-%d %H:%M:%S"

def configure_logging(log_level: str = "INFO") -> None:
    """配置根日志器。

    应用日志输出到 stdout，方便本地终端、Docker logs 和 GitHub Actions
    统一查看。uvicorn.access 的日志交给统一格式处理。
    """

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
    """按名称获取 logger，供中间件、Service 和任务模块记录日志。"""

    return logging.getLogger(name)
