"""应用数据与日志路径。"""

import os

APP_NAME = "TGChatToSQL"
APP_SUPPORT = os.path.join(
    os.path.expanduser("~/Library/Application Support"), APP_NAME
)


def data_dir() -> str:
    """应用数据目录；TGCHAT_DATA_DIR 可用于测试与便携模式。"""
    override = os.environ.get("TGCHAT_DATA_DIR")
    path = override or APP_SUPPORT
    os.makedirs(path, exist_ok=True)
    return path


def default_db_path() -> str:
    return os.path.join(data_dir(), "telegram_chat.db")


def backup_dir() -> str:
    path = os.path.join(data_dir(), "backups")
    os.makedirs(path, exist_ok=True)
    return path


def log_dir() -> str:
    path = os.path.join(data_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def config_path() -> str:
    return os.path.join(data_dir(), "config.json")
