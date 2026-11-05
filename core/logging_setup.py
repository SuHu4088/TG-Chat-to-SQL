"""轮转日志：每一步操作都写入文件，便于调试与维护。"""

import logging
import os
from logging.handlers import RotatingFileHandler

from . import paths

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger("tgchat")
    if _CONFIGURED:
        return logger

    logger.setLevel(level)
    logger.propagate = False
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = RotatingFileHandler(
        os.path.join(paths.log_dir(), "app.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(fmt)
    logger.addHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    _CONFIGURED = True
    logger.info("日志系统已启动，目录：%s", paths.log_dir())
    return logger


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger("tgchat." + name)
