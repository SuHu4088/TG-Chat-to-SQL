#!/usr/bin/env python3
"""生成完全虚构的 Telegram 导出 JSON，用于演示、截图与性能测试。

警告：本脚本生成的所有昵称、消息、群名均为随机虚构内容，不含任何真实聊天数据。
"""

import argparse
import json
import random
from datetime import datetime, timedelta

USERS = [
    ('阿岚', 'user_alan'), ('小北', 'user_beibei'), ('木木', 'user_mumu'),
    ('七喜', 'user_qixi'), ('老陈', 'user_laochen'), ('团子', 'user_tuanzi'),
    ('阿橘', 'user_aju'), ('青柠', 'user_qingning'), ('大麦', 'user_damai'),
    ('小鱼', 'user_xiaoyu'), ('山竹', 'user_shanzhu'), ('松果', 'user_songguo'),
]

TEXT_TEMPLATES = [
    '今天的构建又挂了，日志里全是 warning。',
    '我把 SQLite 的索引加上了，查询从 800ms 降到 40ms。',
    '这个热力图颜色有点糊，能不能把色阶拉开一点？',
    '文档我补完了，README 首屏记得放真实截图。',
    '周末有人一起看线上监控吗？',
    '刚发版，灰度 10%，先观察半小时。',
    'React 那个列表滚动还是卡，我准备换虚拟滚动。',
    '缓存命中率只有 62%，有点低。',
    '需求评审改到明天下午三点。',
    '这个 Bug 我复现了，是时区导致的日期错位。',
    '咖啡续命，今天第四杯了。',
    '数据导出的 CSV 用 Excel 打开会乱码，要加 BOM。',
    'Parquet 真的香，压缩比 CSV 小太多了。',
    '我加了一个增量导入的去重键，重复跑不会脏数据。',
    '性能压测结果：5 万条消息，首屏 120ms。',
    '这个接口超时是代理的问题，不是服务端。',
    '今晚复盘放在 21:00，腾讯会议链接我发群里。',
    '文档里的版本号要和 CHANGELOG 对上。',
    'SQL 写完了，等 DBA  review。',
    '新的监控面板上线了，错误率能实时看。',
    '别急，先回滚，再定位。',
    '这个月活跃度明显上升了。',
    '热力图里周三晚上是高峰，和我们发版节奏一致。',
    '测试用例还差边界条件，我补一下。',
    '本地跑没问题，CI 上就挂，玄学。',
    '依赖下载又超时，走代理吧。',
    '我把 Telegram 导出的 JSON 脱敏后放进 examples 了。',
    '求一个可以把时间轴缩放做得顺滑的方案。',
    '虚拟滚动要处理动态高度，不然会跳。',
    '分页 + 虚拟滚动，两个都要，用户会来回翻。',
    '晚安，明天继续。',
]

SERVICE_ACTIONS = [
    {'action': 'join_by_link', 'actor': '松果'},
    {'action': 'invite_members', 'actor': '老陈'},
    {'action': 'set_title', 'actor': '阿岚', 'title': '深夜代码俱乐部 · 演示'},
    {'action': 'leave_chat', 'actor': '七喜'},
]

STICKER_EMOJI = ['😀', '🚀', '🐛', '☕️', '🔥', '🎉', '📦', '🧪', '🛠️', '📊']


def build_text_entities(text, rng):
    """按关键词做简单富文本标记，符合 Telegram text_entities 结构。"""
    keywords = ['SQLite', 'Parquet', 'React', 'SQL', 'CSV', 'Bug', 'README', 'CHANGELOG']
    entities = []
    rest = text
    for kw in keywords:
        if kw in rest and len(entities) < 3:
            idx = rest.find(kw)
            before = rest[:idx]
            if before:
                entities.append({'type': 'plain', 'text': before})
            entities.append({'type': 'bold', 'text': kw})
            rest = rest[idx + len(kw):]
    if rest:
        entities.append({'type': 'plain', 'text': rest})
    if not entities:
        entities.append({'type': 'plain', 'text': text})
    return entities


def generate(target_messages: int, days: int, seed: int):
    rng = random.Random(seed)
    end_date = datetime(2026, 11, 4, 23, 0, 0)
    start_date = end_date - timedelta(days=days - 1)

    messages = []
    message_id = 1
    last_text_by_user = {}

    per_day = max(1, target_messages // days)
    for day_index in range(days):
        current_day = start_date + timedelta(days=day_index)
        weekday = current_day.weekday()
        day_count = int(per_day * (1.35 if weekday >= 5 else 1.0))
        day_count += rng.randint(-max(1, per_day // 3), max(1, per_day // 2))
        day_count = max(3, day_count)

        # 一天的活跃时段：午休、晚间高峰
        hours_pool = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 20, 21, 21, 22, 22, 23]
        for _ in range(day_count):
            hour = rng.choice(hours_pool)
            if rng.random() < 0.07:
                hour = rng.choice([0, 1, 2, 3])
            minute = rng.randint(0, 59)
            second = rng.randint(0, 59)
            dt = current_day.replace(hour=hour, minute=minute, second=second)

            roll = rng.random()
            if roll < 0.045:
                template = rng.choice(SERVICE_ACTIONS)
                msg = {
                    'id': message_id,
                    'type': 'service',
                    'date': dt.isoformat(),
                    'date_unixtime': str(int(dt.timestamp())),
                    **template,
                }
                messages.append(msg)
                message_id += 1
                continue

            name, user_id = rng.choice(USERS)
            roll = rng.random()
            if roll < 0.06:
                msg = {
                    'id': message_id,
                    'type': 'message',
                    'date': dt.isoformat(),
                    'date_unixtime': str(int(dt.timestamp())),
                    'from': name,
                    'from_id': user_id,
                    'media_type': 'sticker',
                    'sticker_emoji': rng.choice(STICKER_EMOJI),
                    'file_name': 'sticker.webp',
                    'text': '',
                }
            else:
                base = rng.choice(TEXT_TEMPLATES)
                if rng.random() < 0.35:
                    base += ' ' + rng.choice([
                        '大家怎么看？', '我先试试。', '已记录到待办。',
                        '有复现步骤吗？', '这个优先级 P1。', '收到。'
                    ])
                entities = build_text_entities(base, rng)
                msg = {
                    'id': message_id,
                    'type': 'message',
                    'date': dt.isoformat(),
                    'date_unixtime': str(int(dt.timestamp())),
                    'from': name,
                    'from_id': user_id,
                    'text': base,
                    'text_entities': entities,
                }

                if rng.random() < 0.2:
                    candidates = [m for m in messages[-40:] if m.get('type') == 'message' and m.get('from') != name]
                    if candidates:
                        reply = rng.choice(candidates)
                        msg['reply_to_message_id'] = reply['id']
                        msg['reply_to_peer_id'] = 'user_alan'

                if rng.random() < 0.025:
                    msg['forwarded_from'] = rng.choice(['产品周报', '运维告警', '开源日报'])
                    msg['forwarded_from_id'] = 'channel_demo'

                if rng.random() < 0.12:
                    msg['reactions'] = [
                        {'emoji': rng.choice(['👍', '🔥', '🎉', '👀']), 'count': rng.randint(1, 6), 'recent': []}
                    ]

                if rng.random() < 0.05:
                    msg['edited'] = True

            messages.append(msg)
            message_id += 1

    # 按时间正序输出，方便查看器按自然时间线展示
    messages.sort(key=lambda m: (m['date'], m['id']))

    return {
        'name': '深夜代码俱乐部 · 演示',
        'type': 'private_group',
        'id': 1234567890,
        'messages': messages,
    }


def main():
    parser = argparse.ArgumentParser(description='生成虚构的 Telegram 导出 JSON（仅用于演示）')
    parser.add_argument('--messages', type=int, default=400, help='目标消息数量')
    parser.add_argument('--days', type=int, default=60, help='覆盖天数')
    parser.add_argument('--seed', type=int, default=20261105, help='随机种子')
    parser.add_argument('--out', default='examples/demo_chat.json', help='输出路径')
    args = parser.parse_args()

    data = generate(args.messages, args.days, args.seed)

    import os
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f'已生成 {len(data["messages"]):,} 条虚构消息 -> {args.out}')


if __name__ == '__main__':
    main()
