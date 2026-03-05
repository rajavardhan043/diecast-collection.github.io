# Diecast Data - OTA Updates

This folder contains the over-the-air update files for the DiecastApp car lookup dataset.

## How to publish updates

1. Create a public GitHub repo named `diecast-data`
2. Push the contents of this folder to the `main` branch
3. The app fetches `manifest.json` from `https://raw.githubusercontent.com/rajavardhan043/diecast-collection.github.io/main/manifest.json`

## How to generate a new patch

```bash
# 1. Scrape latest data from Hot Wheels Wiki into a temp file
cd /path/to/DiecastApp
python3 scripts/scrape_wiki_v2.py
# This updates src/data/carLookup.json — copy it first as the fresh file
cp src/data/carLookup.json /tmp/fresh_lookup.json

# 2. Restore the bundled baseline
git checkout src/data/carLookup.json

# 3. Generate the patch (auto-increments version)
python3 scripts/generate_patch.py /tmp/fresh_lookup.json

# 4. Push to GitHub
cd diecast-data
git add . && git commit -m "Patch vN" && git push
```

## File structure

- `manifest.json` — version number + URL to latest patch
- `patch-vN.json` — new entries not in the bundled dataset
