"""打印数据库概览，并执行去重/完整性校验。"""

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, 'importer_gui'))

from db_manager import DatabaseManager  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description='校验 TG-Chat-to-SQL 数据库')
    parser.add_argument('--db', default='telegram_chat.db', help='SQLite 数据库路径')
    args = parser.parse_args(argv)

    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        print(f'错误: 数据库不存在 {db_path}')
        return 1

    db = DatabaseManager(db_path)
    db.connect()

    print('=== 群组信息 ===')
    cursor = db.conn.cursor()
    cursor.execute('SELECT id, chat_name, chat_type, chat_id FROM chat_info')
    for row in cursor.fetchall():
        print(f'ID: {row[0]}, 名称: {row[1]}, 类型: {row[2]}, 群组ID: {row[3]}')

    print('\n=== 消息统计 ===')
    stats = db.get_statistics()
    for key, value in stats.items():
        print(f'  {key}: {value:,}')

    print('\n=== 去重校验 ===')
    integrity = db.verify_integrity()
    print(f'  schema 版本: {integrity["schema_version"]}')
    print(f'  消息总数: {integrity["total_messages"]:,}')
    print(f'  唯一去重键: {integrity["distinct_message_keys"]:,}')
    print(f'  重复键: {len(integrity["duplicate_keys"])}')
    print(f'  孤儿文本实体: {integrity["orphan_entities"]}')
    print(f'  结果: {"通过" if integrity["ok"] else "失败"}')

    cursor.execute('SELECT sender_name, COUNT(*) AS cnt FROM messages '
                   'WHERE sender_name IS NOT NULL GROUP BY sender_name ORDER BY cnt DESC LIMIT 10')
    print('\n=== 发送者 TOP10 ===')
    for row in cursor.fetchall():
        print(f'  {row[0]}: {row[1]} 条')

    db.close()
    return 0 if integrity['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
