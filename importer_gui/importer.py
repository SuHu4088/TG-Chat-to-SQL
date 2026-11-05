import json
import os
import shutil
from typing import Callable, Dict, List, Optional, Tuple


class JSONImporter:
    """Telegram 导出 JSON 的增量导入器。

    去重键为 DatabaseManager.make_message_key(chat_id, message_id)，
    即 "chat_id:message_id"。重复导入时，SQLite 的 UNIQUE 索引会忽略旧消息。
    """

    def __init__(self):
        self.last_result = None

    @staticmethod
    def load_json(file_path: str) -> Dict:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def copy_to_workspace(file_path: str, workspace_dir: str) -> str:
        os.makedirs(workspace_dir, exist_ok=True)
        filename = os.path.basename(file_path)
        dest = os.path.join(workspace_dir, filename)
        shutil.copy2(file_path, dest)
        return dest

    @staticmethod
    def analyze_json(data: Dict) -> Dict:
        messages = data.get('messages', [])
        return {
            'chat_name': data.get('name', 'Unknown'),
            'chat_type': data.get('type', 'unknown'),
            'chat_id': str(data.get('id', '')),
            'total_messages': len(messages),
            'message_ids': [m.get('id') for m in messages[:5]],
            'has_more': len(messages) > 5
        }

    @staticmethod
    def filter_new_messages(
        messages: List[Dict],
        existing_keys: set,
        chat_id: str
    ) -> Tuple[List[Dict], int]:
        new_messages = []
        skipped = 0
        for msg in messages:
            key = f"{chat_id}:{msg.get('id')}"
            if key in existing_keys:
                skipped += 1
            else:
                new_messages.append(msg)
        return new_messages, skipped

    @staticmethod
    def import_to_database(
        db_manager,
        json_path: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        chat_id_override: Optional[str] = None,
    ) -> Dict:
        data = JSONImporter.load_json(json_path)

        chat_name = data.get('name', 'Unknown')
        chat_type = data.get('type', 'unknown')
        chat_id = str(chat_id_override if chat_id_override is not None else data.get('id', ''))
        messages = data.get('messages', [])

        db_manager.insert_chat_info(chat_name, chat_type, chat_id)

        existing_keys = db_manager.get_existing_message_keys(chat_id)
        new_messages, skipped_existing = JSONImporter.filter_new_messages(
            messages, existing_keys, chat_id
        )

        imported = 0
        total = len(new_messages)

        batch_size = 500
        for i in range(0, total, batch_size):
            batch = new_messages[i:i + batch_size]
            imported += db_manager.insert_messages_batch(batch, chat_id)

            if progress_callback:
                current = min(i + batch_size, total)
                progress_callback(current, total, f'正在导入 {current}/{total}')

        # 以数据库真实新增数为准：即使同一批次内出现重复 key，也不会多算。
        skipped = len(messages) - imported

        db_manager.log_import(
            json_file=os.path.basename(json_path),
            total=len(messages),
            imported=imported,
            skipped=skipped
        )

        result = {
            'chat_name': chat_name,
            'chat_id': chat_id,
            'total_in_json': len(messages),
            'imported_count': imported,
            'skipped_count': skipped,
            'skipped_before_insert': skipped_existing,
            'is_new_db': len(existing_keys) == 0,
            'dedupe_key': 'chat_id:message_id',
        }
        JSONImporter.last_result = result
        return result
