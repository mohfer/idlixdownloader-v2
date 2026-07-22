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
uv run python tests/test_downloader.py   # Run unit tests for downloader
```

**Requirements:**
- FFmpeg must be installed and in PATH (run `ffmpeg -version` to verify)
- Python ≥ 3.13

## Architecture

### Three-Phase Pipeline

1. **Network Capture** (`_capture_network_traffic`, `capture_network`)
   - Playwright browser automation with Cloudflare bypass (stealth user agent, webdriver flag removal)
   - Automates play button clicks, closes popup ad tabs, auto-skips pre-roll ads after 8 seconds
   - **Early exit optimization**: polls every 3s for config URL, exits when found (typically 10-20s vs 60s fixed wait)
   - Captures all network requests to extract config URL and subtitle URL

2. **Playlist Parsing** (`parse_network_capture`, `get_config_playlist`)
   - Extracts JWT token from config URL (~55 minute validity - must be preserved throughout)
   - Parses M3U8 master playlist (disguised as `.json`) to get video/audio variant playlists
   - Interactive prompts for resolution selection (defaults to highest) and subtitle inclusion

3. **Parallel Download** (`download_segments`, `download_with_ffmpeg`)
   - 5 worker threads, 3 retry attempts per segment
   - Downloads fMP4 init segment + all fragments
   - **Binary concatenation**: `init_segment + frag1 + frag2 + ... = complete.mp4` (not FFmpeg concat)
   - FFmpeg muxes video + audio + subtitles into final MKV container

### MajorPlay Obfuscation

MajorPlay uses standard HLS with disguises:
- M3U8 master playlists disguised as `.json` files
- fMP4 video segments disguised as common extensions (`.js`, `.png`, `.jpg`, `.css`, `.svg`, `.html`)
- Content distributed across 6+ CDN domains
- JWT authentication tokens (~55 min expiration) appended as query parameters
- Pre-roll VAST ads must be skipped before content plays

### Key Design Decisions

**Why Playwright + cloudscraper combo?**
- Playwright: bypasses Cloudflare, captures network traffic, automates browser interactions
- cloudscraper: handles authenticated segment downloads with preserved JWT tokens

**Why binary concatenation instead of FFmpeg concat demuxer?**
- fMP4 fragments are already in the correct format (init + fragments = valid MP4)
- Direct binary concat is faster and simpler than FFmpeg's concat protocol

**Why visible browser (headless=False)?**
- More reliable for Cloudflare bypass
- User can see what's happening during the ~10-20s capture phase

## File Structure

- `src/idlixdownloader/downloader.py` - Single-class implementation (`MajorPlayDownloader`)
- `src/idlixdownloader/__main__.py` - CLI entry point (delegates to `downloader.main()`)
- `output/` - Downloaded videos (gitignored)

## Debugging

**Config URL not found:**
- Video must play past the ad - ensure ad skip button clicked after 8s
- Check if config URL appears in captured requests (look for `majorplay.net` + `config-` + `.json`)

**JWT token expired (HTTP 403 on segments):**
- Tokens last ~55 minutes from capture time
- Re-run full capture to get fresh token (don't reuse old config URLs)

**Segments fail to download:**
- Retry logic handles transient network issues (3 attempts per segment)
- CDN issues are temporary - wait and retry full download if many segments fail
