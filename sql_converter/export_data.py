"""命令行：从 SQLite 导出消息为 CSV / Parquet。

示例：
    python export_data.py --format csv --output messages.csv
    python export_data.py --format parquet --output messages.parquet --start 2026-01-01 --end 2026-02-01
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import Dict, Iterator, List, Optional

COLUMNS = [
    'message_key', 'chat_id', 'message_id', 'message_type', 'date', 'date_unixtime',
    'sender_name', 'sender_id', 'text_content', 'reply_to_message_id',
    'forwarded_from', 'media_type', 'text_entities',
]


def parse_day(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        raise argparse.ArgumentTypeError(f'日期格式应为 YYYY-MM-DD: {value}')


def build_query(chat_id: Optional[str], start: Optional[str], end: Optional[str]):
    clauses = []
    params: List = []
    if chat_id:
        clauses.append('m.chat_id = ?')
        params.append(str(chat_id))
    start_dt = parse_day(start)
    end_dt = parse_day(end)
    if start_dt:
        clauses.append('m.date_unixtime >= ?')
        params.append(int(start_dt.timestamp()))
    if end_dt:
        clauses.append('m.date_unixtime < ?')
        params.append(int((end_dt + timedelta(days=1)).timestamp()))

    where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    message_sql = f'''
        SELECT m.message_key, m.chat_id, m.id, m.message_type, m.date, m.date_unixtime,
               m.sender_name, m.sender_id, m.text_content, m.reply_to_message_id,
               m.forwarded_from, m.media_type
        FROM messages m
        {where}
        ORDER BY m.date_unixtime, m.id
    '''
    entity_sql = f'''
        SELECT e.message_key, e.entity_type, e.entity_text
        FROM text_entities e
        JOIN messages m ON m.message_key = e.message_key
        {where}
        ORDER BY e.id
    '''
    return message_sql, entity_sql, params


def load_entity_map(conn: sqlite3.Connection, entity_sql: str, params: List) -> Dict[str, List[Dict]]:
    mapping: Dict[str, List[Dict]] = {}
    for message_key, entity_type, entity_text in conn.execute(entity_sql, params):
        mapping.setdefault(message_key, []).append({'type': entity_type, 'text': entity_text})
    return mapping


def iter_rows(conn: sqlite3.Connection, chat_id=None, start=None, end=None) -> Iterator[Dict]:
    message_sql, entity_sql, params = build_query(chat_id, start, end)
    entities = load_entity_map(conn, entity_sql, params)
    for row in conn.execute(message_sql, params):
        entities_json = json.dumps(entities.get(row[0], []), ensure_ascii=False)
        yield {
            'message_key': row[0],
            'chat_id': row[1],
            'message_id': row[2],
            'message_type': row[3],
            'date': row[4],
            'date_unixtime': row[5],
            'sender_name': row[6],
            'sender_id': row[7],
            'text_content': row[8],
            'reply_to_message_id': row[9],
            'forwarded_from': row[10],
            'media_type': row[11],
            'text_entities': entities_json,
        }


def export_csv(conn, output_path: str, chat_id=None, start=None, end=None) -> int:
    count = 0
    with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for row in iter_rows(conn, chat_id, start, end):
            writer.writerow(row)
            count += 1
            if count % 10000 == 0:
                print(f'  已导出 {count:,} 行...')
    return count


def export_parquet(conn, output_path: str, chat_id=None, start=None, end=None) -> int:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        raise RuntimeError('Parquet 导出需要 pyarrow，请先执行: pip install pyarrow')

    rows = list(iter_rows(conn, chat_id, start, end))
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, output_path, compression='snappy')
    return len(rows)


def build_parser():
    parser = argparse.ArgumentParser(description='从 TG-Chat-to-SQL 数据库导出 CSV / Parquet')
    parser.add_argument('--db', default='telegram_chat.db', help='SQLite 数据库路径')
    parser.add_argument('--format', choices=['csv', 'parquet'], default='csv', help='导出格式')
    parser.add_argument('--output', default=None, help='输出文件路径')
    parser.add_argument('--chat-id', default=None, help='只导出指定群组 ID')
    parser.add_argument('--start', default=None, help='起始日期 YYYY-MM-DD（含）')
    parser.add_argument('--end', default=None, help='结束日期 YYYY-MM-DD（含）')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        print(f'错误: 数据库不存在 {db_path}')
        return 1

    if args.output:
        output_path = os.path.abspath(args.output)
    else:
        suffix = 'csv' if args.format == 'csv' else 'parquet'
        output_path = os.path.join(
            os.path.dirname(db_path),
            f'export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.{suffix}',
        )

    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    try:
        if args.format == 'csv':
            count = export_csv(conn, output_path, args.chat_id, args.start, args.end)
        else:
            count = export_parquet(conn, output_path, args.chat_id, args.start, args.end)
    except (RuntimeError, sqlite3.DatabaseError) as e:
        print(f'导出失败: {e}')
        return 3
    finally:
        conn.close()

    size = os.path.getsize(output_path)
    print(f'导出完成: {output_path}')
    print(f'  行数: {count:,}')
    print(f'  大小: {size / 1024 / 1024:.2f} MB')
    return 0


if __name__ == '__main__':
    sys.exit(main())
