"""命令行：Telegram 导出 JSON → SQLite（复用 GUI 的数据库与增量导入逻辑）。"""

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, 'importer_gui'))

from db_manager import DatabaseManager  # noqa: E402
from importer import JSONImporter  # noqa: E402


def build_parser():
    parser = argparse.ArgumentParser(
        description='将 Telegram 导出的 result.json 增量导入 SQLite，重复导入不会产生重复数据。'
    )
    parser.add_argument('--json', default='result.json', help='Telegram 导出的 JSON 文件（默认 result.json）')
    parser.add_argument('--db', default='telegram_chat.db', help='目标 SQLite 数据库（默认 telegram_chat.db）')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    json_path = os.path.abspath(args.json)
    db_path = os.path.abspath(args.db)

    if not os.path.exists(json_path):
        print(f'错误: 找不到 JSON 文件 {json_path}')
        return 1

    db = DatabaseManager(db_path)
    db.connect()
    db.init_tables()

    print(f'JSON 文件: {json_path}')
    print(f'数据库:   {db_path}')
    print(f'Schema:   v{db.get_schema_version()}')

    result = JSONImporter.import_to_database(db, json_path, lambda c, t, m: print(f'  {m}'))

    print('\n导入结果:')
    print(f'  群组名称:   {result["chat_name"]}')
    print(f'  群组 ID:    {result["chat_id"]}')
    print(f'  去重键:     {result["dedupe_key"]}')
    print(f'  JSON 总数:  {result["total_in_json"]:,}')
    print(f'  新增:       {result["imported_count"]:,}')
    print(f'  跳过重复:   {result["skipped_count"]:,}')
    print(f'  数据库总计: {db.get_message_count():,}')

    integrity = db.verify_integrity()
    print('\n完整性校验:')
    print(f'  schema 版本:       v{integrity["schema_version"]}')
    print(f'  消息总数:          {integrity["total_messages"]:,}')
    print(f'  唯一去重键数量:    {integrity["distinct_message_keys"]:,}')
    print(f'  重复键数量:        {len(integrity["duplicate_keys"])}')
    print(f'  孤儿文本实体:      {integrity["orphan_entities"]}')
    print(f'  校验结果:          {"通过" if integrity["ok"] else "失败"}')

    db.close()
    return 0 if integrity['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
