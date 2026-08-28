import sqlite3

conn = sqlite3.connect('telegram_chat.db')
cursor = conn.cursor()

print('=== 群组信息 ===')
cursor.execute('SELECT * FROM chat_info')
for row in cursor.fetchall():
    print(f'ID: {row[0]}, 名称: {row[1]}, 类型: {row[2]}, 群组ID: {row[3]}')

print('\n=== 消息统计 ===')
cursor.execute('SELECT COUNT(*) FROM messages')
print(f'消息总数: {cursor.fetchone()[0]}')

cursor.execute('SELECT COUNT(*) FROM text_entities')
print(f'文本实体总数: {cursor.fetchone()[0]}')

cursor.execute('SELECT message_type, COUNT(*) FROM messages GROUP BY message_type')
print('\n按类型统计:')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1]}')

cursor.execute('SELECT media_type, COUNT(*) FROM messages WHERE media_type IS NOT NULL')
print('\n按媒体类型统计:')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1]}')

cursor.execute('SELECT COUNT(*) FROM messages WHERE reply_to_message_id IS NOT NULL')
print(f'\n有回复的消息数: {cursor.fetchone()[0]}')

cursor.execute('SELECT COUNT(*) FROM messages WHERE forwarded_from IS NOT NULL')
print(f'转发的消息数: {cursor.fetchone()[0]}')

print('\n=== 前10条消息示例 ===')
cursor.execute('SELECT id, message_type, date, sender_name, text_content FROM messages ORDER BY id LIMIT 10')
for row in cursor.fetchall():
    text = row[4][:50] if row[4] else '(空)'
    print(f'[{row[0]}] {row[1]} | {row[2]} | {row[3]}: {text}')

print('\n=== 发送者消息数TOP10 ===')
cursor.execute('SELECT sender_name, COUNT(*) as cnt FROM messages WHERE sender_name IS NOT NULL GROUP BY sender_name ORDER BY cnt DESC LIMIT 10')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1]}条')

conn.close()
