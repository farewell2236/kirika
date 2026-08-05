#!/usr/bin/env python3
"""公開ページの全SP☆12譜面に、atwikiの地力分類を合成する。"""
from __future__ import annotations

import ast
import html as html_module
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

NORMAL_URL = "https://w.atwiki.jp/bemani2sp11/pages/19.html"
HARD_URL = "https://w.atwiki.jp/bemani2sp11/pages/18.html"
MASTER_PAGE_URLS = (
    "https://sp12.iidx.app/sheets/2891-1732/clear",
    "https://sp12.iidx.app/sheets/2891-1732/hard",
)
OUTPUT = Path("data/sp12.json")
REPORT = Path("data/update-report.json")
TIMEOUT = (8, 25)
MIN_MASTER = 640
RANK_RE = re.compile(r"^(地力(?:S\+?|A\+?|B\+?|C|D|E|F)|個人差(?:S\+?|A\+?|B\+?|C|D|E|F))$")


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (compatible; farewell2236-kirika/4.0; +https://github.com/farewell2236/kirika)",
        "Accept-Language": "ja,en;q=0.8",
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    }


def fetch_text(url: str) -> str:
    response = requests.get(url, headers=headers(), timeout=TIMEOUT)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    text = response.text
    if len(text) < 1000:
        raise RuntimeError(f"response too short: {url} ({len(text)} bytes)")
    return text


def pick(obj: dict, *names: str, default: object = "") -> object:
    for name in names:
        if name in obj and obj[name] is not None:
            return obj[name]
    return default


def normalize_wiki_url(value: str, base: str = "") -> str:
    if not value:
        return ""
    absolute = urljoin(base, value)
    parsed = urlparse(absolute)
    path = re.sub(r"/+", "/", parsed.path).rstrip("/").lower()
    return path


def normalize_title(value: str) -> str:
    value = clean(value)
    value = re.sub(r"\s*\((?:L|LEGGENDARIA)\)\s*$", "", value, flags=re.I)
    return value


def chart_name(value: object, title: str = "") -> str:
    text = clean(value).upper()
    if text in {"4", "L", "LEGGENDARIA", "SPL"} or "LEGGENDARIA" in text or re.search(r"\(L\)\s*$", title, re.I):
        return "LEGGENDARIA"
    return "ANOTHER"


def normalize_rank(text: str) -> str:
    value = clean(text)
    # 「未定」は表示上も未分類へ統合する。
    if not value or "未定" in value:
        return "未分類"
    value = re.sub(r"[（(]\s*\d+\s*曲\s*[）)]", "", value).strip()
    match = re.search(r"(?:地力|個人差)(?:S\+?|A\+?|B\+?|C|D|E|F)", value)
    if not match:
        return "未分類"
    rank = match.group(0)
    return rank if RANK_RE.fullmatch(rank) else "未分類"


def walk_json(value: object):
    """JSON内のすべての値を再帰的に走査する。"""
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def decode_script_payloads(text: str) -> list[object]:
    """HTML内のJSON/Redux初期値を、形式を決め打ちせず抽出する。"""
    soup = BeautifulSoup(text, "html.parser")
    candidates: list[str] = []
    for script in soup.find_all("script"):
        body = script.string or script.get_text() or ""
        body = html_module.unescape(body.strip())
        if not body:
            continue
        candidates.append(body)
        # window.foo = {...}; / const foo = [...] の右辺候補
        match = re.search(r"=\s*([\[{].*[\]}])\s*;?\s*$", body, re.S)
        if match:
            candidates.append(match.group(1))
        # JSON.parse("...") 形式
        for encoded in re.findall(r"JSON\.parse\((['\"])(.*?)\1\)", body, re.S):
            try:
                candidates.append(ast.literal_eval(encoded[0] + encoded[1] + encoded[0]))
            except Exception:
                pass

    # HTML全体に直接埋め込まれたJSONも候補にする。
    for marker in ("__NEXT_DATA__", "__INITIAL_STATE__", "preloadedState", "initialState"):
        if marker in text:
            candidates.append(html_module.unescape(text))
            break

    decoded: list[object] = []
    seen: set[str] = set()
    for raw in candidates:
        raw = raw.strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        attempts = [raw]
        # JSONオブジェクト/配列の範囲を切り出す。
        for opener, closer in (("{", "}"), ("[", "]")):
            left, right = raw.find(opener), raw.rfind(closer)
            if 0 <= left < right:
                attempts.append(raw[left:right + 1])
        for candidate in attempts:
            try:
                decoded.append(json.loads(candidate))
                break
            except Exception:
                continue
    return decoded


def dict_title(item: dict) -> str:
    direct = pick(item, "title", "music_title", "name", "song_name")
    if direct:
        return clean(direct)
    for key in ("music", "song", "sheet", "chart"):
        nested = item.get(key)
        if isinstance(nested, dict):
            value = pick(nested, "title", "music_title", "name", "song_name")
            if value:
                return clean(value)
    return ""


def master_row(item: dict) -> dict | None:
    raw_title = dict_title(item)
    if not raw_title:
        return None
    title = normalize_title(raw_title)
    nested_music = item.get("music") if isinstance(item.get("music"), dict) else {}
    nested_sheet = item.get("sheet") if isinstance(item.get("sheet"), dict) else {}
    ver = clean(
        pick(item, "version", "ver", "series", "version_id", default="")
        or pick(nested_music, "version", "ver", "series", default="-")
    ) or "-"
    difficulty = pick(item, "difficulty", "chart", "play_style", "another", "difficulty_id", default="")
    if not difficulty:
        difficulty = pick(nested_sheet, "difficulty", "chart", "difficulty_id", default="")
    chart = chart_name(difficulty, raw_title)
    wiki_url = clean(
        pick(item, "wiki_url", "wikiUrl", "url", "atwiki_url", default="")
        or pick(nested_music, "wiki_url", "wikiUrl", "url", default="")
    )
    row_id = clean(pick(item, "id", "sheet_id", "chart_id", default=""))
    wiki_key = normalize_wiki_url(wiki_url)
    return {
        "masterKey": row_id or (f"url:{wiki_key}\0{chart}" if wiki_key else f"fallback:{title.casefold()}\0{ver}\0{chart}"),
        "title": title,
        "chart": chart,
        "ver": ver,
        "bpm": clean(pick(item, "bpm", default="") or pick(nested_music, "bpm", default="")),
        "notes": clean(pick(item, "notes", "note_count", default="") or pick(nested_sheet, "notes", "note_count", default="")),
        "attr": clean(pick(item, "attributes", "attribute", default="")),
        "wikiUrl": wiki_url,
    }


def extract_master_from_page(text: str, page_url: str) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()

    # 1. scriptに埋め込まれたJSON/初期stateを解析。
    for payload in decode_script_payloads(text):
        for value in walk_json(payload):
            if not isinstance(value, dict):
                continue
            row = master_row(value)
            if not row or row["masterKey"] in seen:
                continue
            # UI設定やユーザー名等を曲と誤認しないため、譜面らしい情報を要求。
            keys = set(value)
            nested = value.get("sheet") if isinstance(value.get("sheet"), dict) else {}
            looks_like_sheet = bool(
                keys & {"n_clear", "n_clear_string", "hard", "hard_string", "difficulty", "difficulty_id", "notes", "sheet_id"}
                or set(nested) & {"difficulty", "difficulty_id", "notes", "note_count"}
                or row["wikiUrl"]
            )
            if not looks_like_sheet:
                continue
            seen.add(row["masterKey"])
            rows.append(row)

    # 2. サーバー描画された表がある場合のフォールバック。
    soup = BeautifulSoup(text, "html.parser")
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        values = [clean(c.get_text(" ", strip=True)) for c in cells]
        if len(values) < 2:
            continue
        title_index = next((i for i, v in enumerate(values) if i > 0 and v and v not in {"曲名", "タイトル"}), None)
        if title_index is None:
            continue
        ver = values[0]
        if not re.fullmatch(r"\d{1,2}", ver):
            continue
        title_cell = cells[title_index]
        raw_title = values[title_index]
        link = title_cell.find("a", href=True)
        wiki_url = urljoin(page_url, link["href"]) if link else ""
        row = {
            "masterKey": f"html:{normalize_title(raw_title).casefold()}\0{ver}\0{chart_name('', raw_title)}",
            "title": normalize_title(raw_title), "chart": chart_name("", raw_title), "ver": ver,
            "bpm": "", "notes": "", "attr": "", "wikiUrl": wiki_url,
        }
        if row["masterKey"] not in seen:
            seen.add(row["masterKey"])
            rows.append(row)
    return rows


def fetch_master() -> tuple[list[dict], str]:
    """403になるAPIを使わず、公開ページの埋め込みデータを読む。"""
    errors: list[str] = []
    best: tuple[list[dict], str] = ([], "")
    for url in MASTER_PAGE_URLS:
        try:
            text = fetch_text(url)
            rows = extract_master_from_page(text, url)
            print(f"master page candidate: {url} -> {len(rows)} charts")
            if len(rows) > len(best[0]):
                best = (rows, url)
            if len(rows) >= MIN_MASTER:
                return rows, url
            errors.append(f"{url}: extracted only {len(rows)} charts")
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    if len(best[0]) >= MIN_MASTER:
        return best
    raise RuntimeError("all public master pages failed / " + " / ".join(errors))


def table_header_indexes(table: Tag) -> dict[str, int] | None:
    for row in table.find_all("tr")[:3]:
        values = [clean(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
        title_idx = next((i for i, text in enumerate(values) if "曲名" in text), None)
        if title_idx is None:
            continue
        return {
            "title": title_idx,
            "ver": next((i for i, text in enumerate(values) if text.lower() == "ver"), 0),
            "bpm": next((i for i, text in enumerate(values) if "BPM" in text.upper()), -1),
            "notes": next((i for i, text in enumerate(values) if "notes" in text.lower()), -1),
            "attr": next((i for i, text in enumerate(values) if "属性" in text), -1),
        }
    return None


def cell_text(cells: list[Tag], index: int) -> str:
    return clean(cells[index].get_text(" ", strip=True)) if 0 <= index < len(cells) else ""


def parse_rank_page(html: str, page_url: str, mode: str) -> tuple[list[dict], dict]:
    soup = BeautifulSoup(html, "html.parser")
    current_rank = "未分類"
    rows: list[dict] = []
    parsed_tables = 0
    for element in soup.find_all(["h2", "h3", "h4", "h5", "h6", "table"]):
        if element.name != "table":
            text = clean(element.get_text(" ", strip=True))
            if "未定" in text or re.search(r"(?:地力|個人差)(?:S\+?|A\+?|B\+?|C|D|E|F)", text):
                current_rank = normalize_rank(text)
            continue
        indexes = table_header_indexes(element)
        if not indexes:
            continue
        parsed_tables += 1
        for tr in element.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) <= indexes["title"]:
                continue
            title_cell = cells[indexes["title"]]
            raw_title = clean(title_cell.get_text(" ", strip=True))
            if not raw_title or raw_title == "曲名":
                continue
            ver = cell_text(cells, indexes["ver"])
            if not re.fullmatch(r"\d{1,2}", ver):
                continue
            link = title_cell.find("a", href=True)
            wiki_url = urljoin(page_url, link["href"]) if link else ""
            chart = chart_name("", raw_title)
            rows.append({
                "title": normalize_title(raw_title), "chart": chart, "ver": ver,
                "bpm": cell_text(cells, indexes["bpm"]),
                "notes": cell_text(cells, indexes["notes"]),
                "attr": cell_text(cells, indexes["attr"]),
                "wikiUrl": wiki_url, "wikiKey": normalize_wiki_url(wiki_url, page_url),
                "rank": current_rank, "mode": mode,
            })
    # 同じ照合キーが複数ある場合は、未分類より有効分類を優先する。
    unique: dict[str, dict] = {}
    for row in rows:
        key = (f"url:{row['wikiKey']}\0{row['chart']}" if row["wikiKey"]
               else f"fallback:{row['title'].casefold()}\0{row['ver']}\0{row['chart']}")
        old = unique.get(key)
        if old is None or (old["rank"] == "未分類" and row["rank"] != "未分類"):
            unique[key] = row
    result = list(unique.values())
    if len(result) < 500:
        raise RuntimeError(f"too few charts parsed from {page_url}: {len(result)}")
    return result, {"url": page_url, "mode": mode, "parsedCount": len(result), "parsedTables": parsed_tables}


def fallback_identity(row: dict) -> str:
    return f"{row['title'].casefold()}\0{row['ver']}\0{row['chart']}"


def build_rank_indexes(rows: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    by_url: dict[str, dict] = {}
    by_fallback: dict[str, dict] = {}
    for row in rows:
        if row.get("wikiKey"):
            by_url[f"{row['wikiKey']}\0{row['chart']}"] = row
        by_fallback[fallback_identity(row)] = row
    return by_url, by_fallback


def find_rank(master: dict, by_url: dict[str, dict], by_fallback: dict[str, dict]) -> tuple[str, str, dict | None]:
    wiki_key = normalize_wiki_url(master.get("wikiUrl", ""))
    if wiki_key:
        row = by_url.get(f"{wiki_key}\0{master['chart']}")
        if row:
            return row["rank"], "wikiUrl", row
    row = by_fallback.get(fallback_identity(master))
    if row:
        return row["rank"], "title+ver+chart", row
    return "未分類", "unlisted", None


def merge(master: list[dict], normal_rows: list[dict], hard_rows: list[dict]) -> tuple[list[dict], dict]:
    normal_url, normal_fallback = build_rank_indexes(normal_rows)
    hard_url, hard_fallback = build_rank_indexes(hard_rows)
    merged: list[dict] = []
    stats = {"normal": {}, "hard": {}}
    unlisted_normal: list[dict] = []
    unlisted_hard: list[dict] = []
    for item in master:
        normal, normal_method, nrow = find_rank(item, normal_url, normal_fallback)
        hard, hard_method, hrow = find_rank(item, hard_url, hard_fallback)
        # 未定・非掲載・照合不能はすべて未分類。
        normal = normalize_rank(normal)
        hard = normalize_rank(hard)
        stats["normal"][normal] = stats["normal"].get(normal, 0) + 1
        stats["hard"][hard] = stats["hard"].get(hard, 0) + 1
        if normal == "未分類":
            unlisted_normal.append({"title": item["title"], "chart": item["chart"], "ver": item["ver"], "match": normal_method})
        if hard == "未分類":
            unlisted_hard.append({"title": item["title"], "chart": item["chart"], "ver": item["ver"], "match": hard_method})
        source_row = nrow or hrow or {}
        merged.append({
            "title": item["title"], "chart": item["chart"], "ver": item["ver"],
            "bpm": item["bpm"] or source_row.get("bpm", ""),
            "notes": item["notes"] or source_row.get("notes", ""),
            "attr": item["attr"] or source_row.get("attr", ""),
            "normal": normal, "hard": hard, "level": 12,
            "wikiUrl": item["wikiUrl"] or source_row.get("wikiUrl", ""),
            "normalMatch": normal_method, "hardMatch": hard_method,
            "source": "sp12.iidx.app public page + atwiki classifications",
        })
    merged.sort(key=lambda row: (row["title"].casefold(), row["chart"], row["ver"]))
    return merged, {
        "masterCount": len(master), "rankCounts": stats,
        "normalUnclassifiedCount": len(unlisted_normal),
        "hardUnclassifiedCount": len(unlisted_hard),
        "normalUnclassified": unlisted_normal,
        "hardUnclassified": unlisted_hard,
    }


def write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    try:
        master, master_url = fetch_master()
        normal_rows, normal_report = parse_rank_page(fetch_text(NORMAL_URL), NORMAL_URL, "normal")
        hard_rows, hard_report = parse_rank_page(fetch_text(HARD_URL), HARD_URL, "hard")
        rows, merge_report = merge(master, normal_rows, hard_rows)
        if len(rows) < MIN_MASTER:
            raise RuntimeError(f"merged chart count too low: {len(rows)}")
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        payload = {
            "updatedAt": now,
            "sourceUrl": {"master": master_url, "normal": NORMAL_URL, "hard": HARD_URL},
            "classificationMethod": "SP12 master; unlisted and undecided ranks are grouped as 未分類",
            "data": rows,
        }
        report = {"updatedAt": now, "masterUrl": master_url, "normal": normal_report, "hard": hard_report, "merge": merge_report}
        write_json_atomic(OUTPUT, payload)
        write_json_atomic(REPORT, report)
        print(f"updated {OUTPUT}: {len(rows)} charts")
        print(json.dumps({"master": len(master), "normalUnclassified": merge_report["normalUnclassifiedCount"], "hardUnclassified": merge_report["hardUnclassifiedCount"]}, ensure_ascii=False))
    except Exception as exc:
        print(f"update failed; existing JSON was preserved: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
