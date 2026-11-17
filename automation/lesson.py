"""Daily lesson orchestration. Standard library only; no model calls for indexing/rendering."""
import argparse
import base64
from datetime import datetime, timezone, timedelta
import html
import json
import os
from pathlib import Path
import re
import shutil
from string import Template
import subprocess
import time
import unicodedata
import urllib.parse
import urllib.request

CATEGORIES = {'spoken': '口语', 'writing': '写作', 'reading': '阅读'}
BRANCH = 'ai/daily-html-backup'
PROXY = 'http://127.0.0.1:7890'


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.partial')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def load_json(path, default):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def lessons(root):
    result = []
    for p in root.glob('Day*.html'):
        n = re.match(r'Day\s*(\d+)', p.name)
        date = re.search(r'\d{4}-\d{2}-\d{2}', p.name)
        if n and date:
            result.append((int(n[1]), date[0], p))
    return sorted(result)


def refresh_index(root):
    path = root / 'data/expressions.json'
    old = load_json(path, {'version': 1, 'files': []})
    cached = {x['file']: x for x in old['files']}
    entries = []
    for number, date, p in lessons(root):
        stat = p.stat()
        entry = cached.get(p.name)
        if not entry or entry.get('size') != stat.st_size or entry.get('mtime_ns') != stat.st_mtime_ns:
            text = p.read_text(encoding='utf-8-sig')
            expressions = [html.unescape(re.sub(r'<[^>]*>', '', x)).strip()
                           for x in re.findall(r'<h2\b[^>]*>(.*?)</h2>', text, re.I | re.S)]
            if len(expressions) != 3:
                raise ValueError(f'Expected 3 expression headings in {p.name}')
            entry = dict(file=p.name, number=number, date=date, size=stat.st_size,
                         mtime_ns=stat.st_mtime_ns, expressions=expressions)
        entries.append(entry)
    index = {'version': 1, 'files': entries}
    if index != old or not path.exists():
        save_json(path, index)
    history_path = root / 'data/used-expressions.json'
    history = load_json(history_path, [])
    known = {normalize(x) for x in history}
    for entry in entries:
        for expression in entry['expressions']:
            key = normalize(expression)
            if key not in known:
                history.append(expression)
                known.add(key)
    if history != load_json(history_path, None):
        save_json(history_path, history)
    return index


class DuplicateExpressionError(ValueError):
    pass


def normalize(text):
    text = unicodedata.normalize('NFKC', html.unescape(text)).casefold()
    text = re.sub(r'<[^>]*>', '', text)
    # Historical headings can include Chinese translations or category labels.
    text = re.split(r'[\u3400-\u9fff]', text, maxsplit=1)[0]
    text = text.translate(str.maketrans({'’': "'", '‘': "'", 'ʼ': "'"}))
    text = text.replace("'", '')
    return ' '.join(re.findall(r"[a-z0-9]+", text))


def text_field(obj, key):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'Missing text: {key}')
    return value.strip()


def https_url(value):
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Expected public HTTPS URL')
    host = parsed.hostname.lower()
    if host == 'localhost' or host.endswith(('.local', '.localhost')):
        raise ValueError('Local image host is not allowed')
    import ipaddress
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError('Private address is not allowed')
    except ValueError as exc:
        if str(exc) == 'Private address is not allowed':
            raise
    return value


def validate(payload, previous):
    items = payload.get('expressions')
    if not isinstance(items, list) or len(items) != 3:
        raise ValueError('Exactly 3 expressions are required')
    if {x.get('category') for x in items} != set(CATEGORIES):
        raise ValueError('One spoken, writing, reading expression required')
    seen = {normalize(x) for x in previous}
    quotes = {}
    for item in items:
        for key in ['expression', 'meaning', 'register', 'collocations', 'context', 'misuse', 'comparison']:
            text_field(item, key)
        expression = normalize(item['expression'])
        if not expression:
            raise ValueError('Expression must contain English text')
        if expression in seen:
            raise DuplicateExpressionError('Repeated expression: ' + item['expression'])
        seen.add(expression)
        examples = item.get('examples')
        if not isinstance(examples, list) or len(examples) != 2:
            raise ValueError('Exactly 2 bilingual original examples required')
        for example in examples:
            text_field(example, 'en')
            text_field(example, 'zh')
        source = item['source']
        for key in ['url', 'title', 'quote', 'locator', 'verification']:
            text_field(source, key)
        url = https_url(source['url'])
        quotes[url] = quotes.get(url, 0) + len(source['quote'].split())
        if quotes[url] > 25:
            raise ValueError('Quotes from a single URL exceed 25 words')
        image = item.get('image')
        if image is not None:
            https_url(text_field(image, 'url'))
            https_url(text_field(image, 'source_url'))
            text_field(image, 'caption')
        else:
            text_field(item, 'missing_image_reason')
    return items


def download_image(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({'https': PROXY}))
    request = urllib.request.Request(https_url(url), headers={'User-Agent': 'EnglishLearning/1.0'})
    with opener.open(request, timeout=30) as response:
        https_url(response.url)
        mime = response.headers.get_content_type()
        data = response.read(10_000_001)
    signatures = {'image/jpeg': data.startswith(b'\xff\xd8\xff'),
                  'image/png': data.startswith(b'\x89PNG\r\n\x1a\n'),
                  'image/gif': data.startswith((b'GIF87a', b'GIF89a')),
                  'image/webp': data[:4] == b'RIFF' and data[8:12] == b'WEBP'}
    if not signatures.get(mime) or len(data) > 10_000_000:
        raise ValueError('Unsupported image content or size')
    return f'data:{mime};base64,' + base64.b64encode(data).decode('ascii')


def render(root, payload, previous, number, date, fetch=download_image):
    items = validate(payload, previous)
    sections = []
    e = lambda value: html.escape(str(value), quote=True)
    for item in sorted(items, key=lambda x: list(CATEGORIES).index(x['category'])):
        source = item['source']
        parts = [f'<section class="expression"><span class="tag">{CATEGORIES[item["category"]]}</span>',
                 f'<h2>{e(item["expression"])}</h2>']
        for key, title in [('meaning', '核心含义'), ('register', '语气与语域'), ('collocations', '常见搭配'),
                           ('context', '适用场合'), ('misuse', '常见误用'), ('comparison', '近义表达辨析')]:
            parts.append(f'<h3>{title}</h3><p>{e(item[key])}</p>')
        parts += ['<h3>真实出处</h3>', f'<p class="quote">{e(source["quote"])}</p>',
                  f'<p><a href="{e(source["url"])}">{e(source["title"])}</a> · {e(source.get("author", ""))}</p>',
                  f'<p class="note">定位：{e(source["locator"])}。核验记录：{e(source["verification"])}</p>',
                  '<h3>原创例句（非原文引文）</h3><ol>']
        for example in item['examples']:
            parts.append(f'<li><p lang="en">{e(example["en"])}</p><p>{e(example["zh"])}</p></li>')
        parts.append('</ol>')
        image = item.get('image')
        if image:
            try:
                data_uri = fetch(image['url'])
                parts.append(f'<figure><img src="{data_uri}" alt="{e(image["caption"])}"><figcaption>{e(image["caption"])} · <a href="{e(image["source_url"])}">原图出处</a></figcaption></figure>')
            except Exception as exc:
                parts.append('<p class="note">缺图说明：已提供原图链接，但脚本下载或格式校验失败；本条暂缺离线图片。</p>')
                print(f'Image unavailable: {type(exc).__name__}', flush=True)
        else:
            parts.append(f'<p class="note">缺图说明：{e(item["missing_image_reason"])}</p>')
        sections.append('\n'.join(parts) + '</section>')
    template = Template((root / 'templates/lesson.html').read_text(encoding='utf-8-sig'))
    return template.substitute(title=f'进阶英语 · Day {number:03d}', date=date, sections='\n'.join(sections))


def run(root, preview=False, index_only=False):
    root = root.resolve()
    index = refresh_index(root)
    if index_only:
        state_path = root / 'data/state.json'
        if not state_path.exists():
            latest = max(index['files'], key=lambda x: x['number'], default={})
            save_json(state_path, {'version': 1, 'timezone': 'Asia/Shanghai',
                      'date': latest.get('date'), 'number': latest.get('number'),
                      'file': latest.get('file'), 'generation': 'existing_unmodified',
                      'push': {'status': 'not_checked', 'branch': BRANCH}})
        print(f'Indexed {len(index["files"])} lessons; no model call.')
        return
    now = datetime.now(timezone(timedelta(hours=8)))
    date = now.date().isoformat()
    existing = [x for x in lessons(root) if x[1] == date]
    state_path = root / 'data/state.json'
    state = load_json(state_path, {'version': 1})
    state.update(date=date, timezone='Asia/Shanghai')
    if existing and not preview:
        if len(existing) != 1:
            raise ValueError('Multiple lessons exist today; refusing ambiguous update')
        number, _, output = existing[0]
        print('Already exists; skip model: ' + str(output))
    else:
        number = max((x[0] for x in lessons(root)), default=0) + 1
        output = root / ('Preview.html' if preview else f'Day{number:03d}_{date}.html')
        previous = load_json(root / 'data/used-expressions.json', [])
        prompt = (root / 'automation/prompt.txt').read_text(encoding='utf-8-sig')
        prompt += '\n' + json.dumps({'beijing_date': date, 'avoid_expressions': previous}, ensure_ascii=False)
        result_path = root / 'logs/lesson-response.json.partial'
        result_path.parent.mkdir(exist_ok=True)
        result_path.unlink(missing_ok=True)
        if not preview:
            state.update(number=number, file=output.name, generation='running',
                         push={'status': 'not_started', 'branch': BRANCH})
            save_json(state_path, state)
        executable = shutil.which('codex.cmd') or shutil.which('codex')
        if not executable:
            raise RuntimeError('Codex CLI not found; no lesson generated')
        env = dict(os.environ, HTTPS_PROXY=PROXY, HTTP_PROXY=PROXY, NO_PROXY='localhost,127.0.0.1')
        # Keep existing account/model/reasoning defaults; do not silently lower quality.
        command = [executable, 'exec', '--sandbox', 'read-only', '-c', 'web_search="live"',
                   '-C', str(root), '--skip-git-repo-check', '--color', 'never', '-o', str(result_path), '-']
        deadline = time.monotonic() + 2400
        for attempt in range(1, 4):
            result_path.unlink(missing_ok=True)
            with (root / f'logs/run-{now:%Y%m%d-%H%M%S}-{attempt}.log').open('w', encoding='utf-8') as log:
                subprocess.run(command, input=prompt, text=True, encoding='utf-8', stdout=log,
                               stderr=subprocess.STDOUT, env=env, check=True,
                               timeout=max(1, deadline - time.monotonic()))
            payload = load_json(result_path, {})
            try:
                doc = render(root, payload, previous, number, date)
                break
            except DuplicateExpressionError as exc:
                print(f'Attempt {attempt}: {exc}', flush=True)
                if attempt == 3 or time.monotonic() >= deadline:
                    raise
                rejected = [item.get('expression', '') for item in payload.get('expressions', [])]
                prompt += '\n' + json.dumps({
                    'retry_reason': str(exc),
                    'replace_rejected_expressions': rejected,
                    'instruction': 'Return a complete new lesson. Avoid historical expressions and all rejected expressions, including punctuation/case/translation variants.'
                }, ensure_ascii=False)
        partial = output.with_name(output.name + '.partial')
        partial.write_text(doc, encoding='utf-8')
        # Exclusive creation avoids overwriting a lesson created by another entry point.
        # Windows rename is atomic and refuses to replace an existing destination.
        os.rename(partial, output)
        result_path.unlink()
        print('Saved: ' + str(output))
    if preview:
        return
    refresh_index(root)
    progress = root / 'PROGRESS.md'
    if progress.exists():
        content = progress.read_text(encoding='utf-8-sig')
        summary = ('<!-- daily-status:start -->\n'
                   f'最近课程：{output.name}。本地文件存在；当天重跑不调用模型。\n'
                   '生成时检查结构、重复表达及来源字段；历史文件未重新核验出处。推送结果见本机 data/state.json。\n'
                   '<!-- daily-status:end -->')
        pattern = r'<!-- daily-status:start -->.*?<!-- daily-status:end -->'
        content = re.sub(pattern, lambda _: summary, content, flags=re.S) if re.search(pattern, content, re.S) else content.rstrip() + '\n\n' + summary + '\n'
        progress.write_text(content, encoding='utf-8')
    state.update(number=number, file=output.name, generation='complete')
    state['push'] = {'status': 'pending', 'branch': BRANCH}
    save_json(state_path, state)
    try:
        subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                        str(root / 'automation/sync-github.ps1'), '-LessonName', output.name], check=True)
        state['push'] = {'status': 'success', 'branch': BRANCH, 'checked_at': now.isoformat()}
    except Exception:
        state['push'] = {'status': 'failed', 'branch': BRANCH, 'retry': 'Run automation/run.ps1 again; lesson will not regenerate.'}
        save_json(state_path, state)
        raise
    save_json(state_path, state)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--refresh-index', action='store_true')
    args = parser.parse_args()
    try:
        run(args.root, args.preview, args.refresh_index)
    except Exception as exc:
        if not args.preview and not args.refresh_index:
            path = args.root / 'data/state.json'
            state = load_json(path, {'version': 1})
            if state.get('generation') == 'running':
                state['generation'] = 'failed'
            state['last_error'] = type(exc).__name__
            save_json(path, state)
        raise
