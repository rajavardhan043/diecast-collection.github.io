#!/usr/bin/env python3
"""
Self-contained scraper + patch generator for GitHub Actions.

Scrapes the Hot Wheels Wiki for the latest car data, diffs against
baseline.json, and updates manifest.json (with embedded entries) plus
baseline.json if new entries are found. No separate patch files.
"""

import urllib.request
import urllib.parse
import json
import re
import time
import sys
import os
import ssl

API = "https://hotwheels.fandom.com/api.php"
YEARS = range(1968, 2028)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE_PATH = os.path.join(REPO_ROOT, "baseline.json")
MANIFEST_PATH = os.path.join(REPO_ROOT, "manifest.json")
# App's carLookup (when diecast-data is inside app repo)
CARLOOKUP_PATH = os.path.join(os.path.dirname(REPO_ROOT), "src", "data", "carLookup.json")
IMG_BASE = "https://hotwheels.fandom.com/wiki/Special:FilePath/"


def fetch_json(params):
    qs = urllib.parse.urlencode(params)
    url = f"{API}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "DiecastApp/1.0"})
    for attempt in range(3):
        try:
            resp = urllib.request.urlopen(req, timeout=30, context=ctx)
            return json.loads(resp.read())
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                print(f"  Failed: {e}", file=sys.stderr)
                return None


def parse_wikitext(text, year):
    entries = []
    rows = text.split("|-")
    for row in rows:
        cells = [c.strip() for c in row.split("\n|") if c.strip()]
        if len(cells) < 4:
            continue

        name_cell = None
        series_cell = None
        img_filename = None

        for cell in cells:
            if "[[" in cell and "File:" not in cell and not name_cell:
                m = re.search(r'\[\[([^|\]]+?)(?:\|([^]]+))?\]\]', cell)
                if m:
                    name_cell = m.group(2) or m.group(1)
                    name_cell = re.sub(r"\s*\(.*?\)\s*$", "", name_cell).strip()
                    name_cell = re.sub(r"'''.*?'''", "", name_cell).strip()
                    name_cell = re.sub(r"''+", "", name_cell).strip()
                    name_cell = re.sub(r'<[^>]+>', '', name_cell).strip()
            if "bgcolor" in cell.lower() and "[[" in cell and not series_cell:
                sm = re.search(r'\[\[(?:[^|\]]*\|)?\s*([^]]+?)\]\]', cell)
                if sm:
                    series_cell = sm.group(1).strip()
                    series_cell = re.sub(r"'''.*?'''", "", series_cell).strip()
                    series_cell = re.sub(r"''+", "", series_cell).strip()
                    series_cell = re.sub(r'<[^>]+>', '', series_cell).strip()
                    series_cell = re.sub(r'\s*Mini Collection\s*\(\d+\)\s*$', '', series_cell).strip()
            if "[[File:" in cell and not img_filename:
                fm = re.search(r'\[\[File:([^\]|]+)(?:\|[^\]]*)?\]\]', cell)
                if fm:
                    fname = fm.group(1).strip()
                    if fname and "Image_Not_Available" not in fname:
                        img_filename = fname

        if name_cell and len(name_cell) > 1:
            if re.search(r'\((?:2nd|3rd|4th|5th)\s+Color', name_cell):
                continue
            if "Zamac" in (name_cell or ""):
                continue
            entry = {
                "name": name_cell,
                "year": str(year),
                "series": series_cell or "",
            }
            if img_filename:
                entry["img"] = IMG_BASE + urllib.parse.quote(img_filename.replace(" ", "_"))
            entries.append(entry)
    return entries


def scrape_all():
    all_entries = []
    seen = set()

    for year in YEARS:
        page = f"List_of_{year}_Hot_Wheels"
        print(f"Fetching {year}...", end=" ", flush=True)

        data = fetch_json({
            "action": "parse",
            "page": page,
            "prop": "wikitext",
            "format": "json",
        })

        if not data or "parse" not in data:
            print("not found")
            continue

        wikitext = data["parse"]["wikitext"]["*"]
        entries = parse_wikitext(wikitext, year)

        new_count = 0
        for e in entries:
            key = f"{e['name']}||{e['year']}"
            if key not in seen:
                seen.add(key)
                all_entries.append(e)
                new_count += 1

        print(f"{new_count} entries")
        time.sleep(0.3)

    all_entries.sort(key=lambda e: (e["name"].lower(), e.get("year", "")))
    print(f"\nTotal scraped: {len(all_entries)} entries")
    return all_entries


def generate_patch(fresh_entries):
    with open(BASELINE_PATH, "r", encoding="utf-8") as f:
        baseline = json.load(f)

    baseline_keys = set(f"{e['name']}||{e.get('year','')}" for e in baseline)
    new_entries = [e for e in fresh_entries if f"{e['name']}||{e.get('year','')}" not in baseline_keys]

    if not new_entries:
        print("No new entries found. Dataset is up to date.")
        return False

    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            old_manifest = json.load(f)
        version = old_manifest.get("version", 0) + 1
        existing_entries = old_manifest.get("entries", [])
    except FileNotFoundError:
        version = 1
        existing_entries = []

    # Cumulative entries (for users who skip updates)
    seen_keys = set(f"{e['name']}||{e.get('year','')}" for e in existing_entries)
    for e in new_entries:
        key = f"{e['name']}||{e.get('year','')}"
        if key not in seen_keys:
            seen_keys.add(key)
            existing_entries.append(e)
    existing_entries.sort(key=lambda e: (e.get("name", "").lower(), e.get("year", "")))

    # Update baseline so next run won't re-detect these as "new"
    updated_baseline = baseline + new_entries
    updated_baseline.sort(key=lambda e: (e.get("name", "").lower(), e.get("year", "")))
    with open(BASELINE_PATH, "w", encoding="utf-8") as f:
        json.dump(updated_baseline, f, ensure_ascii=False, indent=2)

    max_year = max((e.get("year", "0") for e in fresh_entries), default="0")
    data_url = "https://raw.githubusercontent.com/rajavardhan043/DiecastApp/main/src/data/carLookup.json"
    manifest = {
        "version": version,
        "lastYear": max_year,
        "entries": existing_entries,
        "dataUrl": data_url,
    }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\nUpdate v{version}: {len(new_entries)} new entries (total patch: {len(existing_entries)})")
    print(f"Updated: {MANIFEST_PATH}")
    print(f"Updated: {BASELINE_PATH}")

    for e in new_entries[:5]:
        print(f"  {e['name']} ({e.get('year','?')}) - {e.get('series','')}")

    # Append new entries to carLookup.json when running from app repo
    if os.path.isfile(CARLOOKUP_PATH):
        try:
            with open(CARLOOKUP_PATH, "r", encoding="utf-8") as f:
                carlookup = json.load(f)
            seen = set(f"{e['name']}||{e.get('year','')}" for e in carlookup)
            to_append = []
            for e in new_entries:
                key = f"{e['name']}||{e.get('year','')}"
                if key not in seen:
                    seen.add(key)
                    to_append.append(e)
            if to_append:
                carlookup.extend(to_append)
                carlookup.sort(key=lambda x: (x.get("name", "").lower(), x.get("year", "")))
                with open(CARLOOKUP_PATH, "w", encoding="utf-8") as f:
                    json.dump(carlookup, f, ensure_ascii=False, indent=2)
                print(f"Updated: {CARLOOKUP_PATH} (+{len(to_append)} entries)")
        except Exception as ex:
            print(f"Warning: could not update carLookup.json: {ex}", file=sys.stderr)

    return True


def main():
    print("=== Hot Wheels Data Updater ===\n")
    fresh = scrape_all()
    changed = generate_patch(fresh)
    if changed:
        print("\n✓ New data found and patch generated.")
    else:
        print("\n✓ No changes needed.")
    sys.exit(0 if not changed else 0)


if __name__ == "__main__":
    main()
