import json
import os
import re
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

try:
    import jieba
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_JSON = os.path.join(SCRIPT_DIR, 'result.json')
OUTPUT_JSON = os.path.join(SCRIPT_DIR, 'processed_data.json')


def load_data(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def extract_text(msg):
    if msg.get('type') != 'message':
        return ''
    text = msg.get('text', '')
    if isinstance(text, list):
        parts = []
        for entity in text:
            if isinstance(entity, dict) and 'text' in entity:
                parts.append(entity['text'])
            elif isinstance(entity, str):
                parts.append(entity)
        return ''.join(parts)
    return str(text) if text else ''


def parse_datetime(date_str):
    try:
        dt = datetime.fromisoformat(date_str)
        return dt
    except:
        return None


def get_day_of_week(dt):
    days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    return days[dt.weekday()]


def get_day_of_week_index(dt):
    return dt.weekday()


def get_hour(dt):
    return dt.hour


def simple_tokenize(text):
    if not text:
        return []
    text = re.sub(r'[^\u4e00-\u9fff\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    tokens = []

    if JIEBA_AVAILABLE:
        words = jieba.lcut(text)
        for word in words:
            word = word.strip()
            if len(word) >= 2 and any('\u4e00' <= c <= '\u9fff' for c in word):
                tokens.append(word)
            elif word.isalpha() and len(word) >= 2:
                tokens.append(word.lower())
    else:
        chinese_chars = re.findall(r'[\u4e00-\u9fff]+', text)
        for segment in chinese_chars:
            if len(segment) >= 2:
                for i in range(len(segment) - 1):
                    tokens.append(segment[i:i+2])
                tokens.append(segment)
            else:
                tokens.append(segment)
        english_words = re.findall(r'[a-zA-Z]+', text)
        for word in english_words:
            if len(word) >= 2:
                tokens.append(word.lower())

    return tokens


STOP_WORDS = {
    '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
    '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
    '自己', '这', '那', '啊', '吧', '呢', '吗', '哦', '哈', '嗯', '呀', '诶',
    'the', 'is', 'to', 'a', 'in', 'it', 'you', 'that', 'for', 'on', 'with',
    'this', 'i', 'be', 'are', 'was', 'not', 'but', 'we', 'my', 'your', 'so',
    '什么', '怎么', '这样', '那样', '这个', '那个', '这些', '那些',
    '一下', '一下下', '哈', '哈哈', '哈哈哈', '嗯嗯', '哦哦', '嘿嘿',
    '不是', '现在', '知道', '可以', '看看', '但是', '因为', '所以', '如果',
    '什么', '怎么', '为什么', '哪里', '怎么样', '好吧', '真的', '还是',
    '已经', '应该', '可能', '大家', '他们', '我们', '你们', '她们',
    '然后', '之后', '之前', '现在', '开始', '最后', '一直', '一起',
    '东西', '事情', '问题', '感觉', '时候', '地方', '方面', '一下',
    '取件', '标签', 'bot', '文件', '件码', '暂元', '乐狗',
}

NOISE_WORDS = {
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
    '11', '12', '13', '14', '15', '16', '17', '18', '19', '20',
    '123', '456', '789', '100', '200', '300', '520',
}


def filter_tokens(tokens):
    return [t for t in tokens 
            if t.lower() not in STOP_WORDS 
            and t not in NOISE_WORDS
            and len(t) >= 2]


def build_activity_heatmap(messages):
    heatmap = {}
    for day_idx in range(7):
        for hour in range(24):
            heatmap[f"{day_idx}_{hour}"] = 0

    for msg in messages:
        dt = parse_datetime(msg.get('date', ''))
        if dt is None:
            continue
        day_idx = get_day_of_week_index(dt)
        hour = get_hour(dt)
        key = f"{day_idx}_{hour}"
        heatmap[key] = heatmap.get(key, 0) + 1

    return heatmap


def build_topic_heatmap(messages):
    topic_data = {}
    for day_idx in range(7):
        for hour in range(24):
            topic_data[f"{day_idx}_{hour}"] = Counter()

    for msg in messages:
        dt = parse_datetime(msg.get('date', ''))
        if dt is None:
            continue
        text = extract_text(msg)
        if not text:
            continue
        tokens = simple_tokenize(text)
        tokens = filter_tokens(tokens)
        if not tokens:
            continue
        day_idx = get_day_of_week_index(dt)
        hour = get_hour(dt)
        key = f"{day_idx}_{hour}"
        topic_data[key].update(tokens)

    result = {}
    for key, counter in topic_data.items():
        result[key] = counter.most_common(5)

    return result


def build_daily_summary(messages):
    daily = {}
    for msg in messages:
        dt = parse_datetime(msg.get('date', ''))
        if dt is None:
            continue
        date_key = dt.strftime('%Y-%m-%d')
        if date_key not in daily:
            daily[date_key] = {
                'count': 0,
                'users': set(),
                'first_msg': None,
                'last_msg': None,
                'hour_counts': defaultdict(int)
            }
        daily[date_key]['count'] += 1
        sender = msg.get('from') or msg.get('actor') or '未知'
        daily[date_key]['users'].add(sender)
        hour = dt.strftime('%H:%M')
        if daily[date_key]['first_msg'] is None or hour < daily[date_key]['first_msg']:
            daily[date_key]['first_msg'] = hour
        if daily[date_key]['last_msg'] is None or hour > daily[date_key]['last_msg']:
            daily[date_key]['last_msg'] = hour
        hour_idx = dt.hour
        daily[date_key]['hour_counts'][hour_idx] += 1

    result = {}
    for date_key, info in sorted(daily.items()):
        result[date_key] = {
            'count': info['count'],
            'user_count': len(info['users']),
            'active_users': list(info['users'])[:20],
            'first_msg': info['first_msg'],
            'last_msg': info['last_msg'],
            'peak_hour': max(info['hour_counts'], key=info['hour_counts'].get) if info['hour_counts'] else 0,
            'peak_count': max(info['hour_counts'].values()) if info['hour_counts'] else 0
        }

    return result


def build_top_users(messages, top_n=20):
    user_counter = Counter()
    for msg in messages:
        sender = msg.get('from') or msg.get('actor')
        if sender:
            user_counter[sender] += 1
    return user_counter.most_common(top_n)


def build_daily_details(messages):
    daily = {}
    for msg in messages:
        dt = parse_datetime(msg.get('date', ''))
        if dt is None:
            continue
        date_key = dt.strftime('%Y-%m-%d')
        if date_key not in daily:
            daily[date_key] = {
                'hour_counts': [0] * 24,
                'keywords': Counter(),
                'message_count': 0,
                'users': set()
            }
        hour_idx = dt.hour
        daily[date_key]['hour_counts'][hour_idx] += 1
        daily[date_key]['message_count'] += 1
        sender = msg.get('from') or msg.get('actor') or '未知'
        daily[date_key]['users'].add(sender)
        text = extract_text(msg)
        if text:
            tokens = simple_tokenize(text)
            tokens = filter_tokens(tokens)
            if tokens:
                daily[date_key]['keywords'].update(tokens)

    result = {}
    for date_key in sorted(daily.keys()):
        info = daily[date_key]
        result[date_key] = {
            'hour_counts': info['hour_counts'],
            'keywords': dict(info['keywords'].most_common(50)),
            'message_count': info['message_count'],
            'user_count': len(info['users']),
            'users': sorted(info['users'])
        }

    return result


def build_time_period_stats(messages):
    periods = {
        '凌晨 (0-6点)': [],
        '上午 (6-12点)': [],
        '下午 (12-18点)': [],
        '晚上 (18-24点)': []
    }

    for msg in messages:
        dt = parse_datetime(msg.get('date', ''))
        if dt is None:
            continue
        hour = dt.hour
        text = extract_text(msg)
        if 0 <= hour < 6:
            period = '凌晨 (0-6点)'
        elif 6 <= hour < 12:
            period = '上午 (6-12点)'
        elif 12 <= hour < 18:
            period = '下午 (12-18点)'
        else:
            period = '晚上 (18-24点)'
        if text:
            periods[period].append(text)

    stats = {}
    for period, texts in periods.items():
        all_tokens = []
        for text in texts:
            tokens = simple_tokenize(text)
            tokens = filter_tokens(tokens)
            all_tokens.extend(tokens)
        counter = Counter(all_tokens)
        stats[period] = {
            'message_count': len(texts),
            'top_keywords': counter.most_common(15)
        }

    return stats


def main():
    print(f"读取JSON文件: {INPUT_JSON}")
    data = load_data(INPUT_JSON)

    messages = data.get('messages', [])
    print(f"消息总数: {len(messages)}")
    print(f"群组名称: {data.get('name', '未知')}")

    print("\n正在构建活跃度热力图...")
    activity_heatmap = build_activity_heatmap(messages)

    print("正在构建话题热力图...")
    topic_heatmap = build_topic_heatmap(messages)

    print("正在构建每日汇总...")
    daily_summary = build_daily_summary(messages)

    print("正在构建每日详情...")
    daily_details = build_daily_details(messages)

    print("正在统计活跃用户...")
    top_users = build_top_users(messages)

    print("正在统计时段特征...")
    time_stats = build_time_period_stats(messages)

    result = {
        'meta': {
            'chat_name': data.get('name', ''),
            'chat_type': data.get('type', ''),
            'chat_id': data.get('id', ''),
            'total_messages': len(messages),
            'generated_at': datetime.now().isoformat()
        },
        'activity_heatmap': activity_heatmap,
        'topic_heatmap': topic_heatmap,
        'daily_summary': daily_summary,
        'daily_details': daily_details,
        'top_users': top_users,
        'time_period_stats': time_stats
    }

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n数据处理完成!")
    print(f"输出文件: {OUTPUT_JSON}")

    total_active = sum(1 for v in activity_heatmap.values() if v > 0)
    max_activity = max(activity_heatmap.values()) if activity_heatmap else 0
    print(f"\n热力图统计:")
    print(f"  活跃时段数: {total_active}")
    print(f"  单时段最高消息数: {max_activity}")
    print(f"  统计天数: {len(daily_summary)}天")
    print(f"  活跃用户数: {len(top_users)}+")

    print("\n最活跃用户 TOP 10:")
    for i, (user, count) in enumerate(top_users[:10], 1):
        print(f"  {i}. {user}: {count}条消息")

    print("\n各时段消息量:")
    for period, info in time_stats.items():
        print(f"  {period}: {info['message_count']}条消息")
        if info['top_keywords']:
            keywords = ', '.join([f'{w}({c})' for w, c in info['top_keywords'][:5]])
            print(f"    热门词: {keywords}")


if __name__ == '__main__':
    main()
