#!/usr/bin/env python3
"""SP☆12の曲データを更新する。

分類名はtier番号から推測せず、元のatwiki難易度表に表示されている
見出し（地力A、個人差B+など）をそのまま使用する。
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

NORMAL_PAGE = "https://iidx-difficulty-table-checker.nomadblacky.dev/table/12_normal"
HARD_PAGE = "https://iidx-difficulty-table-checker.nomadblacky.dev/table/12_hard"
OUTPUT = Path("data/sp12.json")
TIMEOUT = (7, 20)
VALID_RANK = re.compile(r"^(?:未定|地力[0-9A-FS](?:\+)?|個人差[0-9A-FS](?:\+)?)$")


def get(url: str) -> str:
    headers = {"User-Agent": "farewell2236-kirika/2.0 (+GitHub Actions)"}
    response = requests.get(url, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    if len(response.text) < 1000:
        raise RuntimeError(f"response too short: {url} ({len(response.text)} bytes)")
    return response.text


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_url(url: str, base: str = "") -> str:
    absolute = urljoin(base, url)
    parsed = urlparse(absolute)
    # ドメイン変更（www19.atwiki.jp → w.atwiki.jp）があってもページパスで照合する
    path = re.sub(r"/+", "/", parsed.path).rstrip("/")
    return path.lower()


def parse_next_data(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    node = soup.find("script", id="__NEXT_DATA__")
    if not node or not node.string:
        raise RuntimeError("__NEXT_DATA__ not found")
    return json.loads(node.string)


def get_tables(document: dict) -> dict[str, dict]:
    entries = document["props"]["pageProps"]["tables"]["tables"]
    return {str(entry["id"]): entry["table"] for entry in entries}


def displayed_ranks(atwiki_html: str, page_url: str) -> dict[str, str]:
    """Wiki URLのパス → 画面に表示されている分類名。"""
    soup = BeautifulSoup(atwiki_html, "html.parser")
    result: dict[str, str] = {}
    current_rank = "未分類"

    # 見出しと表をページ上の順番どおりに処理する
    for element in soup.find_all(["h2", "h3", "h4", "h5", "h6", "table"]):
        if element.name != "table":
            text = clean(element.get_text(" ", strip=True))
            text = re.sub(r"[（(]\s*\d+\s*曲?\s*[）)]$", "", text).strip()
            # 見出しに余分な説明が付いていても分類名だけを抽出
            match = re.search(r"(?:未定|地力[0-9A-FS](?:\+)?|個人差[0-9A-FS](?:\+)?)", text)
            if match and VALID_RANK.fullmatch(match.group(0)):
                current_rank = match.group(0)
            continue

        rows = element.find_all("tr")
        if not rows:
            continue
        headers = [clean(cell.get_text(" ", strip=True)) for cell in rows[0].find_all(["th", "td"])]
        title_index = next((i for i, value in enumerate(headers) if "曲名" in value), None)
        if title_index is None:
            continue

        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) <= title_index:
                continue
            title_cell = cells[title_index]
            link = title_cell.find("a", href=True)
            if not link:
                continue
            key = normalize_url(link["href"], page_url)
            if key:
                result[key] = current_rank

    if len(result) < 300:
        raise RuntimeError(f"too few ranked charts parsed from {page_url}: {len(result)}")
    return result


def chart_key(item: dict) -> tuple[str, str, int]:
    return (
        clean(item.get("name")),
        clean(item.get("version")),
        int(item.get("difficulty", 3)),
    )


def build_rows(tables: dict[str, dict]) -> list[dict]:
    normal_table = tables["12_normal"]
    hard_table = tables["12_hard"]

    normal_ranks = displayed_ranks(get(normal_table["url"]), normal_table["url"])
    hard_ranks = displayed_ranks(get(hard_table["url"]), hard_table["url"])

    normal = {chart_key(item): item for item in normal_table["data"]}
    hard = {chart_key(item): item for item in hard_table["data"]}
    rows: list[dict] = []
    missing_normal = 0
    missing_hard = 0

    for key in sorted(set(normal) | set(hard), key=lambda value: (value[0].casefold(), value[2])):
        n = normal.get(key)
        h = hard.get(key)
        base = n or h
        assert base is not None
        difficulty = int(base.get("difficulty", 3))
        wiki_path = normalize_url(clean(base.get("wikiUrl")))
        normal_rank = normal_ranks.get(wiki_path, "未分類") if n else "未分類"
        hard_rank = hard_ranks.get(wiki_path, "未分類") if h else "未分類"
        missing_normal += int(n is not None and normal_rank == "未分類")
        missing_hard += int(h is not None and hard_rank == "未分類")

        rows.append({
            "title": clean(base.get("name")),
            "chart": {3: "ANOTHER", 4: "LEGGENDARIA"}.get(difficulty, "SP☆12"),
            "ver": clean(base.get("version")) or "-",
            "normal": normal_rank,
            "hard": hard_rank,
            "level": 12,
            "wikiUrl": clean(base.get("wikiUrl")),
            "source": "displayed headings on atwiki",
        })

    rows = [row for row in rows if row["title"]]
    if len(rows) < 400:
        raise RuntimeError(f"not enough SP12 charts: {len(rows)}")
    # ページ構造の変化を誤って正常扱いしない
    if missing_normal > 15 or missing_hard > 15:
        raise RuntimeError(
            f"too many unmatched rank labels: normal={missing_normal}, hard={missing_hard}"
        )
    return rows


def main() -> None:
    errors: list[str] = []
    for page in (NORMAL_PAGE, HARD_PAGE):
        try:
            document = parse_next_data(get(page))
            tables = get_tables(document)
            if "12_normal" not in tables or "12_hard" not in tables:
                raise RuntimeError("12_normal / 12_hard not found")
            rows = build_rows(tables)
            payload = {
                "updatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                "sourceUrl": page,
                "classificationMethod": "displayed atwiki section headings (no tier conversion)",
                "data": rows,
            }
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            temporary = OUTPUT.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(OUTPUT)
            print(f"updated {OUTPUT}: {len(rows)} charts")
            return
        except Exception as exc:  # try the other Next.js page as a metadata source
            errors.append(f"{page}: {exc}")

    print("update failed; existing data/sp12.json was preserved", file=sys.stderr)
    print("\n".join(errors), file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
