#!/usr/bin/env python3
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

URLS = [
    'https://iidx-difficulty-table-checker.nomadblacky.dev/table/12_normal',
    'https://iidx-difficulty-table-checker.nomadblacky.dev/table/12_hard',
]
OUTPUT = Path('data/sp12.json')
TIER_LABELS = {
    0:'個人差S+', 1:'地力S+', 2:'個人差S', 3:'地力S',
    4:'個人差A+', 5:'地力A+', 6:'個人差A', 7:'地力A',
    8:'個人差B+', 9:'地力B+', 10:'個人差B', 11:'地力B',
    12:'個人差C', 13:'地力C', 14:'個人差D', 15:'地力D',
    16:'個人差E', 17:'地力E', 18:'個人差F', 19:'地力F',
}

def fetch_html(url: str) -> str:
    cmd = [
        'curl', '--fail', '--location', '--silent', '--show-error',
        '--connect-timeout', '5', '--max-time', '18',
        '--retry', '1', '--retry-delay', '1',
        '--user-agent', 'farewell2236-naide/1.0', url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f'curl exit {result.returncode}')
    if len(result.stdout) < 10000:
        raise RuntimeError(f'HTML response too short: {len(result.stdout)} bytes')
    return result.stdout

def parse(html: str) -> dict:
    m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.S | re.I)
    if not m:
        raise RuntimeError('__NEXT_DATA__ not found')
    return json.loads(m.group(1))

def extract(doc: dict) -> list[dict]:
    entries = doc['props']['pageProps']['tables']['tables']
    tables = {str(x['id']): x['table']['data'] for x in entries}
    if '12_normal' not in tables or '12_hard' not in tables:
        raise RuntimeError('12_normal / 12_hard tables not found')

    def key(x):
        return (str(x.get('name','')).strip(), str(x.get('version','')).strip(), int(x.get('difficulty',3)))

    normal = {key(x): x for x in tables['12_normal']}
    hard = {key(x): x for x in tables['12_hard']}
    rows = []
    for k in sorted(set(normal) | set(hard), key=lambda z: (z[0].casefold(), z[2])):
        n, h = normal.get(k), hard.get(k)
        base = n or h
        difficulty = int(base.get('difficulty',3))
        rows.append({
            'title': str(base.get('name','')).strip(),
            'chart': {3:'ANOTHER',4:'LEGGENDARIA'}.get(difficulty,'SP☆12'),
            'ver': str(base.get('version','-')).strip() or '-',
            'normal': TIER_LABELS.get((n or {}).get('tier'), '未分類'),
            'hard': TIER_LABELS.get((h or {}).get('tier'), '未分類'),
            'level': 12,
            'source': 'iidx-difficulty-table-checker.nomadblacky.dev',
        })
    rows = [x for x in rows if x['title']]
    if len(rows) < 400:
        raise RuntimeError(f'not enough charts: {len(rows)}')
    return rows

def main() -> None:
    errors=[]
    for url in URLS:
        try:
            rows=extract(parse(fetch_html(url)))
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT.write_text(json.dumps({
                'updatedAt': datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'),
                'sourceUrl': url,
                'data': rows,
            }, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            print(f'updated {OUTPUT}: {len(rows)} charts')
            return
        except Exception as exc:
            errors.append(f'{url}: {exc}')
    print('update failed; existing data/sp12.json is preserved', file=sys.stderr)
    print('\n'.join(errors), file=sys.stderr)
    raise SystemExit(1)

if __name__ == '__main__':
    main()
