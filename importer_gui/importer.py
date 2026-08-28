import json
import os
import shutil
from typing import Dict, List, Tuple, Optional, Callable


class JSONImporter:
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
            'message_ids': [m['id'] for m in messages[:5]],
            'has_more': len(messages) > 5
        }

    @staticmethod
    def filter_new_messages(messages: List[Dict], existing_ids: set) -> Tuple[List[Dict], int]:
        new_messages = []
        skipped = 0

        for msg in messages:
            if msg['id'] in existing_ids:
                skipped += 1
            else:
                new_messages.append(msg)

        return new_messages, skipped

    @staticmethod
    def import_to_database(
        db_manager,
        json_path: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict:
        data = JSONImporter.load_json(json_path)

        chat_name = data.get('name', 'Unknown')
        chat_type = data.get('type', 'unknown')
        chat_id = str(data.get('id', ''))
        messages = data.get('messages', [])

        db_manager.insert_chat_info(chat_name, chat_type, chat_id)

        existing_ids = db_manager.get_existing_message_ids()
        new_messages, skipped = JSONImporter.filter_new_messages(messages, existing_ids)

        imported = 0
        total = len(new_messages)

        batch_size = 500
        for i in range(0, total, batch_size):
            batch = new_messages[i:i + batch_size]
            count = db_manager.insert_messages_batch(batch)
            imported += count

            if progress_callback:
                progress_callback(min(i + batch_size, total), total, f'正在导入 {min(i + batch_size, total)}/{total}')

        db_manager.log_import(
            json_file=os.path.basename(json_path),
            total=len(messages),
            imported=imported,
            skipped=skipped
        )

        return {
            'chat_name': chat_name,
            'total_in_json': len(messages),
            'imported_count': imported,
            'skipped_count': skipped,
            'is_new_db': len(existing_ids) == 0
        }
