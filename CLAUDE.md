# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Setup:**
```bash
uv sync                              # Install dependencies
uv run playwright install chromium   # One-time browser setup (required)
```

**Run:**
```bash
uv run idlix <video_url>                      # Auto mode: automated network capture
uv run idlix <video_url> <config_url>         # Manual mode: skip capture, use known config URL
```

**Test:**
```bash
uv run python tests/test_downloader.py                          # Full unit suite (unittest)
uv run python tests/test_downloader.py TestParseNetworkCapture  # One test class
uv run python -m unittest tests.test_downloader.TestLanguageParsing.test_parse_language_english  # Single test
```

No linter/formatter is configured. Dependencies: `cloudscraper`, `playwright`. Python ≥ 3.13. FFmpeg must be on PATH (`ffmpeg -version`).

## Architecture

Single class owns the pipeline: `MajorPlayDownloader` in `src/idlixdownloader/downloader.py`. CLI is `idlix` → `__main__.main()` → `downloader.main()`.

### Pipeline (`download`)

1. **Metadata** (`get_video_info`) — scrape page for title (slug fallback).
2. **Config discovery**
   - Auto: Playwright capture (`capture_network` / `_capture_network_traffic`) → `parse_network_capture`
   - Manual: caller supplies config URL; skip browser capture
3. **Resume check** — if `output/<title>/download_state.json` + `segments/` exist, prompt continue vs fresh.
4. **Playlist** (`get_config_playlist`) — fetch disguised M3U8 master; pick quality by bandwidth (or reuse saved); collect audio + subtitles. Highest = max bandwidth, not list index 1.
5. **Subtitle choice** — interactive, or restored from metadata by base URL (JWT query stripped). Labels via `format_subtitle_label` (playlist NAME/LANGUAGE, `/i18n/<code>/`, or generic `Subtitle`).
6. **Download + mux** (`download_segments` → `download_with_ffmpeg`) — parallel fMP4 segments, binary concat, FFmpeg → MKV.

### Network capture

- Visible Chromium (`headless=False`), stealth UA + `navigator.webdriver` stripped.
- Auto-clicks play, closes popup tabs, skips pre-roll after ~8s.
- Early exit: poll every 3s for `majorplay.net` + `config-` + `.json` (often 10–20s vs full wait).
- Capture budget in auto mode is 70s wall clock.

### Resume / metadata

- State file: `output/<video_name>/download_state.json` (`resolution`, `bandwidth`, `subtitle` dict, timestamp).
- Resume matches quality by **bandwidth** (MajorPlay often omits `RESOLUTION=`, so label collides as `unknown`). Legacy state without bandwidth + unknown resolution cannot auto-match — prompt / prefer Fresh.
- Helpers: `save_download_metadata`, `load_download_metadata`, `get_language_from_subtitle_url` (`/i18n/<code>/` → display name), `format_subtitle_label`.
- Resume keeps quality/subtitle prefs; segment download skips existing `.m4s`. Fresh mode deletes segments + state.
- Subtitle rematch ignores JWT query so resume survives token expiry; capture must still produce a fresh config URL/token for new segment fetches.
- Different qualities ⇒ different segment counts; wrong-quality resume can mix partial segments — prefer Fresh if match is ambiguous.

### MajorPlay obfuscation

Standard HLS, disguised:
- Master playlist as `.json`; fMP4 fragments as `.js`/`.png`/`.jpg`/`.css`/`.svg`/`.html`
- Multi-CDN; JWT on query (~55 min lifetime) must stay on every authenticated URL
- Pre-roll VAST must be skipped before config appears

### Design choices worth preserving

- **Playwright + cloudscraper**: browser for CF + interaction/capture; cloudscraper for authenticated segment GETs with JWT intact.
- **Binary concat, not FFmpeg concat demuxer**: `init + frags` is already valid fMP4; faster path.
- **Visible browser**: more reliable CF bypass than headless.

### Layout

- `src/idlixdownloader/downloader.py` — all download logic
- `src/idlixdownloader/__main__.py` — CLI entry
- `tests/test_downloader.py` — unittest (parse, playlist, video info, metadata, language, subtitle labels, bandwidth resume)
- `output/` — downloads (gitignored); per-title dirs hold `segments/`, `download_state.json`, final `.mkv`

### Debug

- **No config URL**: video never got past ad; look for `majorplay.net` + `config-` + `.json` in capture.
- **HTTP 403 on segments**: JWT expired → re-capture; do not reuse stale config URLs for long runs.
- **Many segment failures**: 3 retries/segment already; wait and re-run if CDN is flaky.
