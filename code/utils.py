import json
import redis
import random
import string
import hashlib
import settings

def cache_engine():
    return redis.Redis(host=settings.REDIS_HOSTNAME, port=settings.REDIS_PORT, db=settings.REDIS_DB)

def cache_get(key, default=None):
    r = cache_engine()
    value = r.get(key)
    if value is not None:
        value = json.loads(value.decode())
    else:
        value = default
    return value

def cache_set(key, value, expiration=None):
    r = cache_engine()
    value_json = json.dumps(value)
    if expiration is None:
        r.set(key, value_json)
    else:
        # expiration in seconds
        r.setex(key, expiration, value_json)

def cache_delete(key):
    r = cache_engine()
    r.delete(key)

def convert_size(size_bytes):
    if size_bytes == 0:
        return '0B'
    size_units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    i = 0
    while size_bytes >= 1024 and i < len(size_units) - 1:
        size_bytes /= 1024.0
        i += 1
    return f'{size_bytes:.2f} {size_units[i]}'

def short_hash(text):
    # Encode the text to bytes, then get the SHA-256 hash and take the first 16 characters
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]

def convert_seconds_to_hhmm(seconds):
    hours = int(seconds) // 3600
    minutes = (int(seconds) % 3600) // 60
    seconds = int(seconds) % 60
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'

class Page:
    def __init__(self, page, start_idx, end_idx, total_items, per_page):
        self.page = page
        self.start_idx = start_idx
        self.end_idx = end_idx
        self.total_items = total_items
        self.per_page = per_page

def get_page(request, total_items, per_page):
    try:
        page = int(request.args.get('page') or 1)
        assert page > 0
    except (TypeError, ValueError, AssertionError):
        page = 1
    page_start = (page - 1) * per_page
    page_end = page * per_page
    if page_end > total_items:
        page_end = total_items
    return Page(page, page_start, page_end, total_items, per_page)

def generate_key(s):
    key = hashlib.sha256(f'{s}:{settings.SECRET_KEY}'.encode()).hexdigest()
    return key

def generate_random_string(length):
    characters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def item_to_segments(item):
    segments = [(item.title, 0, 300)]
    if item.subheadline.strip():
        segments.append((item.subheadline.strip(), 0, 500))
    if item.author.strip():
        segments.append((f'By {item.author.strip()}', 0, 500))
    for idx, line in enumerate([x.strip() for x in item.content.splitlines() if x.strip()]):
        if line.startswith('# ') and line[2:].strip():
            segments.append((line[2:].strip(), 1400, 1000))
        else:
            segments.append((line, 0 if idx else 700, 200))
    return segments

def google_escale_ssml(s):
    for x, y in ((' & ', ' and '), ('&', ' and ')):
        s = s.replace(x, y)
    return escape_ssml(s)

def escape_ssml(s):
    for x, y in (('&', '&amp;'), ('"', '&quot;'), ('“', '&quot;'), ('”', '&quot;'), ("'", '&apos;'), ("’", '&apos;'), ("‘", '&apos;'), ('<', '&lt;'), ('>', '&gt;')):
        s = s.replace(x, y)
    return s

def item_to_ssml(item, provider=None):
    if provider == 'google-tts':
        return item_to_ssml_google(item)
    else:
        return item_to_ssml_normal(item)

def item_to_ssml_normal(item):
    e = escape_ssml
    segments = ['<speak>', e(item.title) + '<break time="500ms"/>']
    if item.subheadline.strip():
        segments.append(e(item.subheadline.strip()) + '<break time="500ms"/>')
    if item.author.strip():
        segments.append(e(f'By {item.author.strip()}') + '<break time="500ms"/>')
    segments.append('<break time="700ms"/>')
    for idx, line in enumerate([x.strip() for x in item.content.splitlines() if x.strip()]):
        if line.startswith('# ') and line[2:].strip():
            segments.append(f'<break time="1200ms"/><p>{e(line[2:].strip())}</p><break time="800ms"/>')
        else:
            segments.append(f'<p>{e(line)}</p>')
    segments.append('</speak>')
    return '\n'.join(segments)

def item_to_ssml_google(item):
    e = google_escale_ssml
    segments = ['<speak>', e(item.title) + '<break time="500ms"/>']
    if item.subheadline.strip():
        segments.append(e(item.subheadline.strip()) + '<break time="500ms"/>')
    if item.author.strip():
        segments.append(e(f'By {item.author.strip()}') + '<break time="500ms"/>')
    segments.append('<break time="700ms"/>')
    for idx, line in enumerate([x.strip() for x in item.content.splitlines() if x.strip()]):
        if line.startswith('# ') and line[2:].strip():
            segments.append(f'<break time="1200ms"/><p>{e(line[2:].strip())}</p><break time="800ms"/>')
        else:
            segments.append(f'<p>{e(line)}</p><break time="300ms"/>')
    segments.append('</speak>')
    return '\n'.join(segments)

def summarize_number(number):
    if number >= 1_000_000:
        return f"{number / 1_000_000:.4g}M"
    elif number >= 1_000:
        return f"{number / 1_000:.4g}K"
    else:
        return str(int(number))
