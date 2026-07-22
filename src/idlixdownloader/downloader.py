#!/usr/bin/env python3
"""
MajorPlay Video Downloader
Downloads videos from z2.idlixku.com
"""

import os
import sys
import json
import re
import time
import glob
import subprocess
import cloudscraper
from pathlib import Path
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from playwright.sync_api import sync_playwright

class MajorPlayDownloader:
    def __init__(self):
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
        )
        self.base_url = "https://z2.idlixku.com/"
        self.video_id = None
        self.video_name = None
        self.config_url = None
        self.jwt_token = None
        self.subtitle_url = None

    def get_video_info(self, url):
        """Extract video metadata from page"""
        print(f"[1/6] Fetching video page...")

        response = self.scraper.get(url)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch page: {response.status_code}")

        # Extract video ID
        match = re.search(r'data-postid="(\d+)"', response.text)
        if match:
            self.video_id = match.group(1)

        # Extract title
        match = re.search(r'<meta itemprop="name" content="([^"]+)"', response.text)
        if match:
            self.video_name = match.group(1).replace('/', '-').replace('\\', '-')
        else:
            # Fallback: use URL slug
            self.video_name = url.rstrip('/').split('/')[-1]

        print(f"   Video: {self.video_name}")
        return True

    def get_session_media(self):
        """Get session media (skip ad)"""
        print(f"[2/6] Getting session media...")

        response = self.scraper.get(f"{self.base_url}api/watch/session/media")
        if response.status_code != 200:
            raise Exception(f"Failed to get session media: {response.status_code}")

        # Response is VAST XML with ad - we can skip this
        print(f"   Ad detected (skipping)")
        return True

    def get_config_playlist(self):
        """Get config (master playlist)"""
        print(f"[3/6] Fetching MajorPlay config...")

        # For now, we need to provide the config URL
        # In a full implementation, this would be extracted from player JavaScript
        if not self.config_url:
            print("\n   Config URL required. Example:")
            print("   https://e2e.majorplay.net/v/z5/VIDEO_ID/config-XXXXX.json?t=JWT_TOKEN")
            return False

        response = self.scraper.get(self.config_url)
        if response.status_code != 200:
            raise Exception(f"Failed to get config: {response.status_code}")

        # Parse M3U8 master playlist
        master_playlist = response.text

        # Extract variant playlists
        variants = []
        for line in master_playlist.split('\n'):
            if line.startswith('#EXT-X-STREAM-INF'):
                # Extract resolution and bandwidth
                res_match = re.search(r'RESOLUTION=(\d+x\d+)', line)
                bw_match = re.search(r'BANDWIDTH=(\d+)', line)
                resolution = res_match.group(1) if res_match else 'unknown'
                bandwidth = int(bw_match.group(1)) if bw_match else 0
                variants.append({
                    'resolution': resolution,
                    'bandwidth': bandwidth,
                    'line': line
                })
            elif line and not line.startswith('#') and variants:
                # This is the playlist URL for the last variant
                variants[-1]['url'] = line

        # Extract audio
        audio_url = None
        for line in master_playlist.split('\n'):
            if 'TYPE=AUDIO' in line:
                match = re.search(r'URI="([^"]+)"', line)
                if match:
                    audio_url = match.group(1)

        if not variants:
            raise Exception("No video variants found in config")

        print(f"\n   Available resolutions:")
        for i, v in enumerate(variants):
            print(f"   {i+1}. {v['resolution']} ({v['bandwidth']//1000} kbps)")

        # Prompt user to select resolution
        highest_idx = variants.index(max(variants, key=lambda x: x['bandwidth']))
        try:
            choice = input(f"\n   Choose resolution (1-{len(variants)}, Enter for highest): ").strip()
            if choice:
                idx = int(choice) - 1
                if 0 <= idx < len(variants):
                    selected = variants[idx]
                else:
                    selected = variants[highest_idx]
            else:
                selected = variants[highest_idx]
        except (ValueError, EOFError):
            selected = variants[highest_idx]

        print(f"   Selected: {selected['resolution']}")

        # Extract JWT token from config URL
        jwt_token = ''
        if '?' in self.config_url:
            jwt_token = '?' + self.config_url.split('?', 1)[1]

        # Construct base without query
        base = self.config_url.rsplit('?', 1)[0].rsplit('/', 1)[0]

        # Build URLs with JWT token
        self.video_playlist_url = urljoin(base + '/', selected['url']) + jwt_token
        self.audio_playlist_url = urljoin(base + '/', audio_url) + jwt_token if audio_url else None

        return True

    def _capture_network_traffic(self, url, wait_time=60000):
        """Capture network requests using Playwright browser automation"""
        requests = []

        def handle_request(request):
            requests.append({
                'url': request.url,
                'method': request.method,
                'headers': request.headers
            })

        def handle_response(response):
            for req in requests:
                if req['url'] == response.url and 'status' not in req:
                    req['status'] = response.status
                    break

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=['--disable-blink-features=AutomationControlled']
            )
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            page.on('request', handle_request)
            page.on('response', handle_response)

            # Navigate and interact
            page.goto(url, wait_until='load')
            page.wait_for_timeout(3000)

            # Click play button
            play_selectors = ['button:has(svg)', 'div.rounded-full:has(svg)', 'div:has(svg[viewBox="0 0 24 24"])', '[role="button"]:has(svg)']
            clicked = False
            for selector in play_selectors:
                try:
                    button = page.wait_for_selector(selector, timeout=5000, state='visible')
                    if button:
                        button.click()
                        clicked = True
                        break
                except:
                    continue

            # Close popup ad tabs
            if clicked:
                page.wait_for_timeout(2000)
                pages = context.pages
                if len(pages) > 1:
                    for p in pages:
                        if p != page:
                            p.close()
                page.bring_to_front()

            if not clicked:
                page.wait_for_timeout(max(wait_time - 8000, 10000))
                page_title = page.title()
                browser.close()
                return {'requests': requests, 'page_title': page_title}

            # Click Skip Ad button after 8s
            page.wait_for_timeout(8000)
            skip_selectors = ['button:has-text("Skip Ad")', 'button.text-black:has(svg)', 'button:has(svg)']
            for selector in skip_selectors:
                try:
                    skip_button = page.wait_for_selector(selector, timeout=3000, state='visible')
                    if skip_button:
                        skip_button.click()
                        page.wait_for_timeout(3000)
                        break
                except:
                    continue

            # Poll for config URL (early exit)
            max_wait = max(wait_time - 8000, 30000)
            elapsed = 0
            check_interval = 3000

            while elapsed < max_wait:
                # Check if config URL found
                config_found = any('majorplay.net' in r['url'] and 'config-' in r['url'] and '.json' in r['url'] for r in requests)
                if config_found:
                    page.wait_for_timeout(5000)
                    break
                page.wait_for_timeout(check_interval)
                elapsed += check_interval

            page_title = page.title()
            browser.close()

        return {'requests': requests, 'page_title': page_title}

    def capture_network(self, url, wait_time=60000):
        """Capture network traffic using browser automation"""
        print(f"[2/6] Capturing network traffic (automated)...")
        print(f"   Launching browser...")
        print(f"   Capture will run for {wait_time//1000} seconds...")

        try:
            data = self._capture_network_traffic(url, wait_time)
            print(f"   [OK] Network captured")
            return data
        except Exception as e:
            print(f"   [X] Error capturing network: {e}")
            return None

    def parse_network_capture(self, data):
        """Parse captured network data to extract config and subtitle URLs"""
        print(f"[3/6] Extracting MajorPlay URLs from capture...")

        try:
            network_data = data['requests']

            # Extract page title if available (from browser capture)
            if 'page_title' in data and data['page_title']:
                title = data['page_title']

                # Remove site branding using regex (handles varying spaces/separators)
                # Matches patterns like " / IDLIX", " - IDLIX", " | Streaming", etc.
                import re
                title = re.sub(r'\s*[/|–—\-]\s*idlix.*$', '', title, flags=re.IGNORECASE)
                title = re.sub(r'\s*[/|–—\-]\s*streaming.*$', '', title, flags=re.IGNORECASE)
                title = title.strip()

                # Clean up title for filename (remove problematic characters)
                for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
                    title = title.replace(char, '-')
                self.video_name = title.strip()
                print(f"   [OK] Video title: {self.video_name}")

            # Find config URL (master playlist)
            for req in network_data:
                url = req.get('url', '')
                if 'majorplay.net' in url and 'config-' in url and '.json' in url:
                    self.config_url = url
                    print(f"   [OK] Config URL extracted")
                    break

            # Find subtitle URL
            for req in network_data:
                url = req.get('url', '')
                if 'majorplay.net' in url and '.vtt' in url:
                    self.subtitle_url = url
                    print(f"   [OK] Subtitle URL found")
                    break

            if not self.config_url:
                print(f"   [X] Config URL not found in capture")
                print(f"   Make sure video played past the ad (skip after 8 sec)")
                return False

            return True

        except Exception as e:
            print(f"   [X] Error parsing captured data: {e}")
            return False

    def get_subtitle_url(self):
        """Return subtitle URL if found"""
        return self.subtitle_url

    def download_segments(self, playlist_url, output_prefix):
        """Download all segments from fMP4 playlist with init segment (parallel)"""
        # Fetch playlist
        response = self.scraper.get(playlist_url)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch playlist: {response.status_code}")

        # Parse init segment (EXT-X-MAP) and segment URLs
        init_url = None
        segments = []
        for line in response.text.split('\n'):
            line = line.strip()
            if line.startswith('#EXT-X-MAP:'):
                # Extract init segment URL
                match = re.search(r'URI="([^"]+)"', line)
                if match:
                    init_url = match.group(1)
                    # Resolve relative URL
                    if not init_url.startswith('http'):
                        base = playlist_url.rsplit('/', 1)[0]
                        init_url = urljoin(base + '/', init_url)
            elif line and not line.startswith('#'):
                # Resolve relative segment URL
                seg_url = line
                if not seg_url.startswith('http'):
                    base = playlist_url.rsplit('/', 1)[0]
                    seg_url = urljoin(base + '/', seg_url)
                segments.append(seg_url)

        if not segments:
            raise Exception("No segments found in playlist")

        print(f"   Found {len(segments)} segments")

        # Download init segment (required for fMP4)
        init_data = None
        if init_url:
            print(f"   Downloading init segment...")
            init_response = self.scraper.get(init_url)
            if init_response.status_code == 200:
                init_data = init_response.content
            else:
                print(f"   Warning: Failed to download init segment")

        # Parallel download function with retry
        def download_segment(i, seg_url, retries=3):
            seg_file = f"{output_prefix}_seg{i:04d}.m4s"

            for attempt in range(retries):
                try:
                    seg_response = self.scraper.get(seg_url, timeout=30)
                    if seg_response.status_code != 200:
                        if attempt == retries - 1:
                            raise Exception(f"Failed segment {i}: {seg_response.status_code}")
                        time.sleep(1 * (attempt + 1))
                        continue

                    # Download fragment as-is (don't prepend init here)
                    with open(seg_file, 'wb') as f:
                        f.write(seg_response.content)
                    return seg_file

                except Exception as e:
                    if attempt == retries - 1:
                        raise Exception(f"Segment {i} failed after {retries} retries: {e}")
                    time.sleep(2 * (attempt + 1))

            raise Exception(f"Segment {i} failed")

        # Download segments in parallel (reduced workers to avoid rate-limit)
        print(f"   Downloading in parallel (5 workers)...")
        segment_files = [None] * len(segments)
        completed = 0
        progress_lock = Lock()

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(download_segment, i, url): i
                      for i, url in enumerate(segments, 1)}

            for future in as_completed(futures):
                i = futures[future]
                try:
                    segment_files[i-1] = future.result()
                    with progress_lock:
                        completed += 1
                        if completed % 50 == 0 or completed == len(segments):
                            print(f"   Downloaded {completed}/{len(segments)}...")
                except Exception as e:
                    print(f"\n   [X] Error downloading segment {i}: {e}")
                    raise

        return {'segments': segment_files, 'init_data': init_data}

    def download_with_ffmpeg(self, output_file, subtitle_url=None):
        """Download segments then binary concat fMP4 fragments"""
        print(f"[5/6] Downloading video...")

        if not self.video_playlist_url:
            raise Exception("No video playlist URL")

        try:
            # Download video segments
            print(f"   Downloading video segments...")
            video_data = self.download_segments(self.video_playlist_url, f"{output_file}_video")
            video_segments = video_data['segments']
            video_init = video_data['init_data']

            # Download audio segments if separate
            audio_segments = None
            audio_init = None
            if self.audio_playlist_url:
                print(f"   Downloading audio segments...")
                audio_data = self.download_segments(self.audio_playlist_url, f"{output_file}_audio")
                audio_segments = audio_data['segments']
                audio_init = audio_data['init_data']

            # Download subtitle
            subtitle_file = None
            if subtitle_url:
                print(f"   Downloading subtitle...")
                subtitle_file = f"{output_file}.vtt"
                sub_response = self.scraper.get(subtitle_url)
                if sub_response.status_code == 200:
                    with open(subtitle_file, 'wb') as f:
                        f.write(sub_response.content)

            # Binary concat: init + frag1 + frag2 + ... = complete.mp4
            print(f"   Concatenating fMP4 fragments...")
            video_complete = f"{output_file}_video_complete.mp4"
            with open(video_complete, 'wb') as out:
                if video_init:
                    out.write(video_init)
                for seg_file in video_segments:
                    with open(seg_file, 'rb') as seg:
                        out.write(seg.read())

            # Binary concat audio if separate
            audio_complete = None
            if audio_segments:
                audio_complete = f"{output_file}_audio_complete.mp4"
                with open(audio_complete, 'wb') as out:
                    if audio_init:
                        out.write(audio_init)
                    for seg_file in audio_segments:
                        with open(seg_file, 'rb') as seg:
                            out.write(seg.read())

            # Mux video + audio + subtitle with FFmpeg
            print(f"   Muxing with FFmpeg...")
            cmd = ['ffmpeg', '-i', video_complete]

            if audio_complete:
                cmd.extend(['-i', audio_complete])

            if subtitle_file:
                cmd.extend(['-i', subtitle_file])
                cmd.extend(['-c', 'copy', '-c:s', 'srt', '-metadata:s:s:0', 'language=ind'])
                output_file = output_file.replace('.mp4', '.mkv')
            else:
                cmd.extend(['-c', 'copy'])

            cmd.append(output_file)

            # Run FFmpeg
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"\n   FFmpeg stderr:")
                print(result.stderr)
                raise Exception(f"FFmpeg failed with code {result.returncode}")
            print(f"\n   [OK] Download complete: {output_file}")

            # Cleanup
            print(f"   Cleaning up temporary files...")
            for seg in video_segments:
                os.remove(seg)
            os.remove(video_complete)
            if audio_segments:
                for seg in audio_segments:
                    os.remove(seg)
                os.remove(audio_complete)
            if subtitle_file:
                os.remove(subtitle_file)
            print(f"   [OK] Cleanup complete")

            return True

        except Exception as e:
            print(f"\n   [X] Error: {e}")
            return False

    def download(self, url, config_url=None, auto_extract=True):
        """Main download flow"""
        self.config_url = config_url

        try:
            # Step 1: Get video info
            if not self.get_video_info(url):
                return False

            # Step 2: Auto-extract config URL if not provided
            if not self.config_url and auto_extract:
                # Capture network traffic
                data = self.capture_network(url, wait_time=70000)
                if not data:
                    print(f"\n   Manual mode: provide config_url as second argument")
                    return False

                # Parse captured data to extract URLs
                if not self.parse_network_capture(data):
                    return False
            elif not self.config_url:
                print(f"[2/6] Config URL required (or use auto_extract mode)")
                return False
            else:
                # Manual mode: skip network capture
                if not self.get_session_media():
                    return False

            # Step 3/4: Get config playlist
            if not self.get_config_playlist():
                return False

            # Step 4/5: Check subtitles
            subtitle_url = self.get_subtitle_url()
            if subtitle_url:
                print(f"[4/6] Subtitle found: Indonesian")
                try:
                    include_sub = input("   Include subtitle? (Y/n): ").strip().lower()
                    if include_sub == 'n':
                        subtitle_url = None
                        print("   Subtitle skipped")
                except (EOFError, KeyboardInterrupt):
                    pass  # Default to including subtitle

            # Step 5/6: Download
            os.makedirs('output', exist_ok=True)
            output = f"output/{self.video_name}.mp4"
            if not self.download_with_ffmpeg(output, subtitle_url):
                return False

            print(f"\n[6/6] Done!")
            return True

        except Exception as e:
            print(f"\n[X] Error: {e}")
            import traceback
            traceback.print_exc()
            return False

def main():
    print("=" * 60)
    print("   MajorPlay Video Downloader")
    print("   Downloads videos from z2.idlixku.com")
    print("=" * 60 + "\n")

    if len(sys.argv) < 2:
        print("Usage:")
        print("  uv run idlix <video_url> [config_url]")
        print("\nModes:")
        print("  Auto mode (default): Captures network automatically")
        print("    uv run idlix <video_url>")
        print("\n  Manual mode: Provide config URL from previous capture")
        print("    uv run idlix <video_url> <config_url>")
        print("\nExample:")
        print("  uv run idlix https://z2.idlixku.com/movie/toy-story-5-2026")
        sys.exit(1)

    video_url = sys.argv[1]
    config_url = sys.argv[2] if len(sys.argv) > 2 else None

    downloader = MajorPlayDownloader()
    success = downloader.download(video_url, config_url, auto_extract=True)

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
