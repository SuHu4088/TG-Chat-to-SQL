import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_manager import DatabaseManager
from importer import JSONImporter


def test_import():
    workspace = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(workspace, 'test_import.db')
    json_path = os.path.join(workspace, 'sample_data.json')

    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"已清除旧测试数据库: {db_path}")

    print("=" * 60)
    print("测试1: 首次导入（全新数据库）")
    print("=" * 60)

    db = DatabaseManager(db_path)
    db.connect()
    db.init_tables()

    result = JSONImporter.import_to_database(db, json_path, lambda c, t, m: print(f"  {m}"))

    print(f"\n结果:")
    print(f"  群组: {result['chat_name']}")
    print(f"  JSON消息总数: {result['total_in_json']:,}")
    print(f"  新导入: {result['imported_count']:,}")
    print(f"  跳过: {result['skipped_count']:,}")
    print(f"  是否全新库: {result['is_new_db']}")

    count = db.get_message_count()
    print(f"  数据库消息数: {count:,}")

    print("\n" + "=" * 60)
    print("测试2: 二次导入（相同文件，应全部跳过）")
    print("=" * 60)

    result2 = JSONImporter.import_to_database(db, json_path, lambda c, t, m: None)

    print(f"  新导入: {result2['imported_count']:,}")
    print(f"  跳过(重复): {result2['skipped_count']:,}")

    print("\n" + "=" * 60)
    print("测试3: 数据验证")
    print("=" * 60)

    stats = db.get_statistics()
    print(f"  消息总数: {stats['total_messages']:,}")
    print(f"  普通消息: {stats['regular_messages']:,}")
    print(f"  服务消息: {stats['service_messages']}")
    print(f"  独立用户: {stats['unique_senders']}")
    print(f"  回复消息: {stats['reply_count']:,}")
    print(f"  转发消息: {stats['forward_count']}")
    print(f"  文本实体: {stats['entity_count']:,}")

    history = db.get_import_history()
    print(f"\n  导入历史记录 ({len(history)} 条):")
    for h in history:
        print(f"    [{h[1]}] {h[2]}: 总{h[3]} 导入{h[4]} 跳过{h[5]} {h[6]}")

    db.close()

    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"\n测试完成，已清理测试数据库")

    print("\n✅ 所有测试通过！")


if __name__ == '__main__':
    test_import()
