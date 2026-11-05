"""流式增量导入：内存占用与消息总量无关。

Telegram 导出的 JSON 是一个大对象，`messages` 是数组。v1.1 用 `json.load`
一次性读入（232k 条时内存峰值 1.21 GiB）。V1.2 改为边读边解析：
- 前缀部分用正则取出 `name` / `type` / `id`；
- `messages` 数组用 `json.JSONDecoder.raw_decode` 逐个解码，攒够一批就写库；
- 内存峰值只与单批大小（默认 500 条）相关。
"""

import json
import os
import re
import time
from typing import Callable, Dict, Iterator, List, Optional

from .db import DatabaseManager
from .logging_setup import get_logger

log = get_logger("importer")

BATCH_SIZE = 500
_META_PATTERNS = {
    "name": re.compile(r'"name"\s*:\s*"((?:[^"\\]|\\.)*)"'),
    "type": re.compile(r'"type"\s*:\s*"((?:[^"\\]|\\.)*)"'),
    "id": re.compile(r'"id"\s*:\s*(\d+)'),
}


class StreamingImportError(Exception):
    pass


def _read_until_messages(fp, max_prefix_bytes: int = 4 * 1024 * 1024):
    """返回 (元数据字典, 剩余缓冲, 数组起始偏移)。"""
    buffer = ""
    while True:
        chunk = fp.read(1024 * 64)
        if not chunk:
            raise StreamingImportError("文件里没有找到 messages 数组")
        buffer += chunk
        marker = re.search(r'"messages"\s*:\s*\[', buffer)
        if marker:
            prefix = buffer[: marker.start()]
            meta = {}
            for key, pattern in _META_PATTERNS.items():
                match = pattern.search(prefix)
                if match:
                    meta[key] = match.group(1) if key != "id" else int(match.group(1))
            return meta, buffer[marker.end():]
        if len(buffer) > max_prefix_bytes:
            raise StreamingImportError("messages 数组前的内容异常，可能不是 Telegram 导出文件")


def iter_messages(path: str, chunk_size: int = 1024 * 128) -> Iterator[Dict]:
    """逐个产出消息对象，不把整个文件读进内存。"""
    decoder = json.JSONDecoder()
    with open(path, "r", encoding="utf-8") as fp:
        meta, buffer = _read_until_messages(fp)
        pending = buffer
        index = 0
        while True:
            # 跳过空白与逗号
            while index < len(pending) and pending[index] in " \t\r\n,":
                index += 1

            if index >= len(pending):
                chunk = fp.read(chunk_size)
                if not chunk:
                    return
                pending = pending[index:] + chunk
                index = 0
                continue

            if pending[index] == "]":
                return

            try:
                obj, end = decoder.raw_decode(pending, index)
            except json.JSONDecodeError:
                # 缓冲区不够，继续读
                chunk = fp.read(chunk_size)
                if not chunk:
                    raise StreamingImportError("JSON 在文件末尾提前结束，数据可能被截断")
                pending = pending[index:] + chunk
                index = 0
                continue

            index = end
            if isinstance(obj, dict):
                yield obj

            # 丢弃已消费部分，控制内存
            if index > chunk_size:
                pending = pending[index:]
                index = 0


def read_metadata(path: str) -> Dict:
    """只读取文件头的群信息，用于导入预览。"""
    with open(path, "r", encoding="utf-8") as fp:
        meta, _ = _read_until_messages(fp)
    return {
        "chat_name": meta.get("name", "Unknown"),
        "chat_type": meta.get("type", "unknown"),
        "chat_id": str(meta.get("id", "")),
    }


def count_messages_stream(path: str) -> int:
    return sum(1 for _ in iter_messages(path))


def import_streaming(
    db: DatabaseManager,
    json_path: str,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    chat_id_override: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict:
    """流式导入并写日志；返回导入结果字典。"""
    started = time.perf_counter()
    meta = read_metadata(json_path)
    chat_id = str(chat_id_override if chat_id_override is not None else meta["chat_id"])
    chat_name = meta["chat_name"]
    chat_type = meta["chat_type"]

    db.upsert_chat(chat_id, chat_name, chat_type)

    batch: List[Dict] = []
    seen_total = 0
    imported = 0

    try:
        for msg in iter_messages(json_path):
            batch.append(msg)
            if len(batch) >= batch_size:
                imported += db.insert_messages_batch(batch, chat_id)
                seen_total += len(batch)
                if progress_callback:
                    progress_callback(seen_total, 0, f"已处理 {seen_total:,} 条")
                batch = []

        if batch:
            imported += db.insert_messages_batch(batch, chat_id)
            seen_total += len(batch)
            if progress_callback:
                progress_callback(seen_total, seen_total, f"已处理 {seen_total:,} 条")

    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        db.log_import(
            os.path.basename(json_path), seen_total, imported, seen_total - imported,
            status="failed", chat_id=chat_id, duration_ms=duration_ms, error=str(exc),
        )
        log.error("导入失败 %s: %s", json_path, exc)
        raise

    duration_ms = int((time.perf_counter() - started) * 1000)
    skipped = seen_total - imported
    db.log_import(
        os.path.basename(json_path), seen_total, imported, skipped,
        status="success", chat_id=chat_id, duration_ms=duration_ms,
    )

    result = {
        "chat_name": chat_name,
        "chat_id": chat_id,
        "total_in_json": seen_total,
        "imported_count": imported,
        "skipped_count": skipped,
        "duration_ms": duration_ms,
        "dedupe_key": "chat_id:message_id",
    }
    log.info(
        "导入完成 chat=%s 共 %d 条，新增 %d，跳过 %d，耗时 %d ms",
        chat_id, seen_total, imported, skipped, duration_ms,
    )
    return result
