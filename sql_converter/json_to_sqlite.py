import json
import sqlite3
import os
from datetime import datetime


def create_database(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_name TEXT NOT NULL,
            chat_type TEXT NOT NULL,
            chat_id TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY,
            chat_id TEXT NOT NULL,
            message_type TEXT NOT NULL,
            date TEXT,
            date_unixtime INTEGER,
            sender_name TEXT,
            sender_id TEXT,
            text_content TEXT,
            reply_to_message_id INTEGER,
            forwarded_from TEXT,
            media_type TEXT,
            raw_json TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS text_entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            entity_type TEXT NOT NULL,
            entity_text TEXT,
            FOREIGN KEY (message_id) REFERENCES messages(id)
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_sender_id ON messages(sender_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(date_unixtime)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_entities_message_id ON text_entities(message_id)')

    conn.commit()
    return conn


def load_json(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def insert_chat_info(conn, data):
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM chat_info LIMIT 1')
    existing = cursor.fetchone()
    if existing is None:
        cursor.execute('''
            INSERT INTO chat_info (chat_name, chat_type, chat_id)
            VALUES (?, ?, ?)
        ''', (data['name'], data['type'], str(data['id'])))
    else:
        cursor.execute('''
            UPDATE chat_info
            SET chat_name = ?, chat_type = ?, chat_id = ?
            WHERE id = ?
        ''', (data['name'], data['type'], str(data['id']), existing[0]))
    conn.commit()


def extract_sender_info(message):
    if 'from' in message:
        return message.get('from'), message.get('from_id')
    elif 'actor' in message:
        return message.get('actor'), message.get('actor_id')
    return None, None


def insert_messages(conn, messages):
    cursor = conn.cursor()
    inserted = 0

    for msg in messages:
        sender_name, sender_id = extract_sender_info(msg)

        cursor.execute('''
            INSERT OR REPLACE INTO messages 
            (id, chat_id, message_type, date, date_unixtime, sender_name, sender_id,
             text_content, reply_to_message_id, forwarded_from, media_type, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            msg['id'],
            str(msg.get('from_id') or msg.get('actor_id', '')),
            msg['type'],
            msg.get('date'),
            int(msg.get('date_unixtime', 0)),
            sender_name,
            sender_id,
            msg.get('text', '') if isinstance(msg.get('text'), str) else '',
            msg.get('reply_to_message_id'),
            msg.get('forwarded_from'),
            msg.get('media_type'),
            json.dumps(msg, ensure_ascii=False)
        ))

        entities = msg.get('text_entities', [])
        if entities:
            for entity in entities:
                cursor.execute('''
                    INSERT INTO text_entities (message_id, entity_type, entity_text)
                    VALUES (?, ?, ?)
                ''', (msg['id'], entity.get('type', ''), entity.get('text', '')))

        inserted += 1
        if inserted % 1000 == 0:
            conn.commit()
            print(f'已处理 {inserted} 条消息...')

    conn.commit()
    return inserted


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(script_dir, 'result.json')
    db_path = os.path.join(script_dir, 'telegram_chat.db')

    if not os.path.exists(json_path):
        print(f'错误: 找不到JSON文件 {json_path}')
        return

    print(f'正在读取JSON文件: {json_path}')
    data = load_json(json_path)

    print(f'群组名称: {data["name"]}')
    print(f'群组类型: {data["type"]}')
    print(f'群组ID: {data["id"]}')
    print(f'消息总数: {len(data["messages"])}')

    conn = create_database(db_path)
    print(f'数据库已创建: {db_path}')

    insert_chat_info(conn, data)
    print('群组信息已保存')

    print('正在导入消息...')
    count = insert_messages(conn, data['messages'])
    print(f'完成! 共导入 {count} 条消息')

    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM text_entities')
    entity_count = cursor.fetchone()[0]
    print(f'文本实体数: {entity_count}')

    conn.close()
    print(f'\n数据库文件: {db_path}')
    print('转换完成!')


if __name__ == '__main__':
    main()
