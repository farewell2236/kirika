#!/usr/bin/env python3
"""sp12.iidx.app が実際に返す全SP☆12譜面と分類文字列をそのまま保存する。"""
from __future__ import annotations

import ast
import html as html_module
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

MASTER_PAGE_URLS = (
    "https://sp12.iidx.app/sheets/2891-1732/clear",
    "https://sp12.iidx.app/sheets/2891-1732/hard",
)
OUTPUT = Path("data/sp12.json")
REPORT = Path("data/update-report.json")
MIN_MASTER = 640
VALID_RANK_RE = re.compile(r"^(?:地力|個人差)(?:S\+?|A\+?|B\+?|C|D|E|F)$")


def clean(value: object) -> str:
    if isinstance(value, list):
        value = " / ".join(clean(x) for x in value if clean(x))
    return re.sub(r"\s+", " ", str(value or "")).strip()


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
    return re.sub(r"/+", "/", parsed.path).rstrip("/").lower()


def normalize_title(value: str) -> str:
    value = clean(value)
    return re.sub(r"\s*\((?:L|LEGGENDARIA)\)\s*$", "", value, flags=re.I)


def chart_name(value: object, title: str = "") -> str:
    text = clean(value).upper()
    if text in {"4", "L", "LEGGENDARIA", "SPL"} or "LEGGENDARIA" in text or re.search(r"\(L\)\s*$", title, re.I):
        return "LEGGENDARIA"
    return "ANOTHER"


def normalize_direct_rank(value: object) -> str:
    """元サイトの文字列分類だけを採用し、未定・空・数値は未分類へ送る。"""
    text = clean(value)
    if not text or text in {"-", "null", "None"} or "未定" in text:
        return "未分類"
    text = re.sub(r"[（(]\s*\d+\s*曲\s*[）)]", "", text).strip()
    match = re.search(r"(?:地力|個人差)(?:S\+?|A\+?|B\+?|C|D|E|F)", text)
    if not match:
        return "未分類"
    rank = match.group(0)
    return rank if VALID_RANK_RE.fullmatch(rank) else "未分類"


def walk_json(value: object):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def decode_script_payloads(text: str) -> list[object]:
    soup = BeautifulSoup(text, "html.parser")
    candidates: list[str] = []
    for script in soup.find_all("script"):
        body = html_module.unescape((script.string or script.get_text() or "").strip())
        if not body:
            continue
        candidates.append(body)
        match = re.search(r"=\s*([\[{].*[\]}])\s*;?\s*$", body, re.S)
        if match:
            candidates.append(match.group(1))
        for quote, encoded in re.findall(r"JSON\.parse\((['\"])(.*?)\1\)", body, re.S):
            try:
                candidates.append(ast.literal_eval(quote + encoded + quote))
            except Exception:
                pass

    decoded: list[object] = []
    seen: set[str] = set()
    for raw in candidates:
        raw = raw.strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        attempts = [raw]
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


def nested_dicts(item: dict) -> list[dict]:
    result = [item]
    for key in ("sheet", "music", "song", "chart", "attributes"):
        value = item.get(key)
        if isinstance(value, dict):
            result.append(value)
    return result


def direct_rank(item: dict, mode: str) -> str:
    if mode == "normal":
        names = (
            "n_clear_string", "normal_string", "normal_rank", "normal_difficulty_string",
            "n_ability_string", "nAbilityString", "nClearString",
        )
    else:
        names = (
            "hard_string", "hard_rank", "hard_difficulty_string", "h_ability_string",
            "hAbilityString", "hardString",
        )
    for obj in nested_dicts(item):
        value = pick(obj, *names, default="")
        rank = normalize_direct_rank(value)
        if rank != "未分類":
            return rank
        if clean(value) and ("未定" in clean(value) or clean(value) in {"-", "null", "None"}):
            return "未分類"
    return "未分類"


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
    row_id = clean(pick(item, "id", "sheet_id", "chart_id", default="") or pick(nested_sheet, "id", "sheet_id", "chart_id", default=""))
    wiki_key = normalize_wiki_url(wiki_url)
    # IDがページごとに同一なら最優先。なければWiki URL、最後に曲名+ver+譜面種別。
    master_key = row_id or (f"url:{wiki_key}\0{chart}" if wiki_key else f"fallback:{title.casefold()}\0{ver}\0{chart}")
    return {
        "masterKey": master_key,
        "title": title,
        "chart": chart,
        "ver": ver,
        "bpm": clean(pick(item, "bpm", default="") or pick(nested_music, "bpm", default="")),
        "notes": clean(pick(item, "notes", "note_count", default="") or pick(nested_sheet, "notes", "note_count", default="")),
        "attr": clean(pick(item, "attributes", "attribute", default="")),
        "wikiUrl": wiki_url,
        "normal": direct_rank(item, "normal"),
        "hard": direct_rank(item, "hard"),
    }


def looks_like_sheet(value: dict, row: dict) -> bool:
    keys = set(value)
    nested = value.get("sheet") if isinstance(value.get("sheet"), dict) else {}
    return bool(
        keys & {
            "n_clear", "n_clear_string", "normal_string", "n_ability_string",
            "hard", "hard_string", "h_ability_string", "difficulty", "difficulty_id",
            "notes", "sheet_id", "chart_id",
        }
        or set(nested) & {"difficulty", "difficulty_id", "notes", "note_count", "sheet_id"}
        or row["wikiUrl"]
    )


def merge_row(target: dict, candidate: dict) -> None:
    for field in ("title", "chart", "ver", "bpm", "notes", "attr", "wikiUrl"):
        if not target.get(field) and candidate.get(field):
            target[field] = candidate[field]
    for field in ("normal", "hard"):
        if target.get(field, "未分類") == "未分類" and candidate.get(field, "未分類") != "未分類":
            target[field] = candidate[field]


def rows_from_payloads(payloads: list[object]) -> list[dict]:
    merged: dict[str, dict] = {}
    for payload in payloads:
        for value in walk_json(payload):
            if not isinstance(value, dict):
                continue
            row = master_row(value)
            if not row or not looks_like_sheet(value, row):
                continue
            old = merged.get(row["masterKey"])
            if old is None:
                merged[row["masterKey"]] = row
            else:
                merge_row(old, row)
    return list(merged.values())


def extract_from_html(text: str) -> list[dict]:
    return rows_from_payloads(decode_script_payloads(text))


def fetch_page_with_browser(url: str) -> tuple[list[dict], dict]:
    from playwright.sync_api import sync_playwright

    payloads: list[object] = []
    response_urls: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"])
        context = browser.new_context(
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            extra_http_headers={"Accept-Language": "ja,en-US;q=0.9,en;q=0.8", "Referer": "https://sp12.iidx.app/"},
        )
        page = context.new_page()

        def on_response(response):
            try:
                ctype = (response.headers.get("content-type") or "").lower()
                if "json" in ctype or "/api/" in response.url or "sheets" in response.url:
                    body = response.body()
                    if len(body) > 20:
                        payloads.append(json.loads(body.decode("utf-8", errors="replace")))
                        response_urls.append(response.url)
            except Exception:
                pass

        page.on("response", on_response)
        response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
        if response and response.status >= 400:
            raise RuntimeError(f"browser HTTP {response.status}: {url}")
        try:
            page.wait_for_load_state("networkidle", timeout=45000)
        except Exception:
            page.wait_for_timeout(8000)
        html_text = page.content()
        browser.close()

    payloads.extend(decode_script_payloads(html_text))
    rows = rows_from_payloads(payloads)
    report = {
        "pageUrl": url,
        "capturedJsonResponses": len(response_urls),
        "responseUrls": sorted(set(response_urls)),
        "extractedCount": len(rows),
        "normalClassified": sum(r["normal"] != "未分類" for r in rows),
        "hardClassified": sum(r["hard"] != "未分類" for r in rows),
    }
    return rows, report


def fetch_all_pages() -> tuple[list[dict], list[dict]]:
    merged: dict[str, dict] = {}
    reports: list[dict] = []
    errors: list[str] = []
    for url in MASTER_PAGE_URLS:
        try:
            rows, report = fetch_page_with_browser(url)
            reports.append(report)
            print(
                f"browser page: {url} -> {len(rows)} charts "
                f"(normal {report['normalClassified']}, hard {report['hardClassified']})"
            )
            for row in rows:
                old = merged.get(row["masterKey"])
                if old is None:
                    merged[row["masterKey"]] = row
                else:
                    merge_row(old, row)
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    rows = list(merged.values())
    if len(rows) < MIN_MASTER:
        raise RuntimeError(f"too few master charts: {len(rows)} / " + " / ".join(errors))
    return rows, reports


def write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    try:
        rows, page_reports = fetch_all_pages()
        output_rows = []
        for row in rows:
            output_rows.append({
                "title": row["title"],
                "chart": row["chart"],
                "ver": row["ver"],
                "bpm": row["bpm"],
                "notes": row["notes"],
                "attr": row["attr"],
                "normal": normalize_direct_rank(row["normal"]),
                "hard": normalize_direct_rank(row["hard"]),
                "level": 12,
                "wikiUrl": row["wikiUrl"],
                "source": "sp12.iidx.app direct classification strings",
            })
        output_rows.sort(key=lambda r: (r["title"].casefold(), r["chart"], r["ver"]))
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        normal_unclassified = [r for r in output_rows if r["normal"] == "未分類"]
        hard_unclassified = [r for r in output_rows if r["hard"] == "未分類"]
        payload = {
            "updatedAt": now,
            "sourceUrl": list(MASTER_PAGE_URLS),
            "classificationMethod": "n_clear_string and hard_string captured directly from sp12.iidx.app; blank and undecided values are 未分類",
            "data": output_rows,
        }
        report = {
            "updatedAt": now,
            "pageReports": page_reports,
            "totalCount": len(output_rows),
            "normalClassifiedCount": len(output_rows) - len(normal_unclassified),
            "hardClassifiedCount": len(output_rows) - len(hard_unclassified),
            "normalUnclassifiedCount": len(normal_unclassified),
            "hardUnclassifiedCount": len(hard_unclassified),
            "normalUnclassified": [{"title": r["title"], "chart": r["chart"], "ver": r["ver"]} for r in normal_unclassified],
            "hardUnclassified": [{"title": r["title"], "chart": r["chart"], "ver": r["ver"]} for r in hard_unclassified],
        }
        write_json_atomic(OUTPUT, payload)
        write_json_atomic(REPORT, report)
        print(f"updated {OUTPUT}: {len(output_rows)} charts")
        print(json.dumps({
            "total": len(output_rows),
            "normalClassified": report["normalClassifiedCount"],
            "hardClassified": report["hardClassifiedCount"],
            "normalUnclassified": report["normalUnclassifiedCount"],
            "hardUnclassified": report["hardUnclassifiedCount"],
        }, ensure_ascii=False))
    except Exception as exc:
        print(f"update failed; existing JSON was preserved: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
