# IdlixDownloader v2

Video downloader for [z2.idlixku.com](https://z2.idlixku.com) with automated network capture and parallel segment downloading.

## Features

- **Automated Network Capture** - Playwright-based browser automation with stealth techniques to bypass Cloudflare challenges
- **Smart Interaction** - Auto-detects and clicks play buttons, handles popup ads, and automatically skips pre-roll advertisements
- **Early Exit Optimization** - Polls for config URLs and exits early instead of waiting fixed timeouts (reduces capture time from 60s to ~10-20s)
- **Parallel Downloading** - Multi-threaded segment download (5 workers) with automatic retry logic (3 attempts per segment)
- **Interactive Selection** - User prompts for resolution and subtitle preferences during download
- **Proper fMP4 Assembly** - Handles init segments correctly for fragmented MP4 concatenation
- **JWT Token Handling** - Preserves authentication tokens throughout the download pipeline (~55 minute validity)
- **Subtitle Support** - Auto-detects and embeds Indonesian subtitles into MKV output

## Prerequisites

- **Python** ≥ 3.13
- **uv** package manager ([installation guide](https://docs.astral.sh/uv/))
- **FFmpeg** installed and available in PATH ([download](https://ffmpeg.org/download.html))
- **Chromium** browser (installed via Playwright)

## Installation

```bash
# Clone the repository
git clone https://github.com/mohfer/idlixdownloader-v2.git

# Navigate into the project directory
cd idlixdownloader-v2

# Install dependencies with uv
uv sync

# Install Playwright browser (one-time setup)
uv run playwright install chromium
```

## Usage

### Auto Mode (Recommended)

Automatically captures network traffic and extracts streaming URLs:

```bash
uv run idlix "https://z2.idlixku.com/movie/toy-story-5-2026"
```

**What happens:**
1. Launches visible browser window
2. Navigates to the video page
3. Clicks play button automatically
4. Closes popup ad tabs if they appear
5. Tool automatically clicks Skip Ad button after 8 seconds (if detected)
6. Captures network traffic (~70 seconds or until config URL found)
7. Extracts config and subtitle URLs from captured requests
8. Prompts for resolution selection (defaults to highest quality)
9. Prompts for subtitle inclusion (defaults to yes)
10. Downloads all segments in parallel (time varies by connection speed and server load)
11. Outputs: `output/Movie Title.mkv` with embedded subtitles

### Manual Mode

Use when you already have the config URL from a previous capture:

```bash
uv run idlix "https://z2.idlixku.com/movie/..." "https://e2e.majorplay.net/.../config.json?t=JWT_TOKEN"
```

This skips the browser automation step and goes directly to downloading.

## How It Works

MajorPlay uses standard HLS (HTTP Live Streaming) protocol with obfuscation techniques:

- **Config Disguise** - M3U8 master playlists disguised as `.json` files
- **Segment Disguise** - fMP4 video segments disguised as common file types (`.js`, `.png`, `.jpg`, `.css`, `.svg`, `.html`)
- **Multi-CDN Distribution** - Content distributed across 6+ CDN domains
- **JWT Authentication** - Time-limited tokens (~55 minute expiration) passed as query parameters
- **Pre-roll VAST Ads** - Standard video ad format that must be skipped before content plays

### Download Process

1. **Network Capture** - Browser automation captures all network requests during video playback
2. **URL Extraction** - Parses captured requests to find config URL (master playlist) and subtitle URLs
3. **Playlist Parsing** - Extracts video/audio variant playlists and segments from M3U8 master playlist
4. **Parallel Download** - Downloads init segment + all fMP4 fragments concurrently (5 workers with retry logic)
5. **Binary Concatenation** - Assembles complete video: `init_segment + frag1 + frag2 + ... = complete.mp4`
6. **FFmpeg Muxing** - Combines video + audio + subtitle into final MKV container

## Project Structure

```
idlixdownloader-v2/
├── src/
│   └── idlixdownloader/
│       ├── __init__.py           # Package initialization
│       ├── __main__.py           # CLI entry point
│       └── downloader.py         # Network capture + download + FFmpeg mux
├── tests/
│   └── test_downloader.py        # Unit tests
├── output/                       # Downloaded videos (gitignored)
├── pyproject.toml                # uv project configuration
└── README.md                     # This file
```

## Troubleshooting

**Config URL not found**
- Make sure to skip the ad after 8 seconds
- Video must play past the ad for config requests to be captured
- Check browser console for errors

**Segments fail to download**
- Network issues are handled automatically (3 retry attempts per segment)
- If many segments fail, check your internet connection
- Temporary CDN issues may resolve with a retry

**JWT token expired**
- Tokens last approximately 55 minutes
- If download takes longer, capture again to get a fresh token
- Manual mode will fail with expired tokens

**FFmpeg not found**
- Install FFmpeg and ensure it's in your system PATH
- Test with: `ffmpeg -version`
- Windows: Add FFmpeg bin directory to PATH environment variable

**Browser automation fails**
- Ensure Playwright Chromium is installed: `uv run playwright install chromium`
- Some networks/firewalls may block browser automation
- Try running with visible browser (default) to see what's happening

**Cloudflare challenge blocks access**
- The tool implements stealth techniques (user agent spoofing, webdriver flag removal)
- If still blocked, the site may have updated its detection
- Visible browser mode (default) is more reliable than headless

## Requirements

Documented in `pyproject.toml`:
- `cloudscraper>=1.2.71` - HTTP client with Cloudflare bypass capabilities
- `playwright>=1.40.0` - Browser automation framework

## License

MIT License. See LICENSE file for details.
