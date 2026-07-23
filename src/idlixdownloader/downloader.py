#!/usr/bin/env python3
"""
MajorPlay Video Downloader
Downloads videos from IDLIX
"""

import os
import sys
import re
import time
import json
import subprocess
import cloudscraper
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from playwright.sync_api import sync_playwright

class MajorPlayDownloader:
    def __init__(self):
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
        )
        self.base_url = "https://z2.idlixku.com/"
        self.video_name = None
        self.config_url = None
        self.subtitles = []  # List of subtitle URLs

    def get_video_info(self, url):
        """Extract video metadata from page"""
        print(f"[1/6] Fetching video page...")

        response = self.scraper.get(url)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch page: {response.status_code}")

        # Extract title
        match = re.search(r'<meta itemprop="name" content="([^"]+)"', response.text)
        if match:
            self.video_name = match.group(1).replace('/', '-').replace('\\', '-')
        else:
            # Fallback: use URL slug
            self.video_name = url.rstrip('/').split('/')[-1]

        print(f"   Video: {self.video_name}")
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

        # Extract JWT token early for subtitle/playlist URLs
        jwt_token = ''
        if '?' in self.config_url:
            jwt_token = '?' + self.config_url.split('?', 1)[1]

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

        # Extract subtitles from master playlist with language info
        playlist_subs_found = 0
        for line in master_playlist.split('\n'):
            if 'TYPE=SUBTITLES' in line:
                # Parse subtitle metadata: NAME, LANGUAGE, URI
                name_match = re.search(r'NAME="([^"]+)"', line)
                lang_match = re.search(r'LANGUAGE="([^"]+)"', line)
                uri_match = re.search(r'URI="([^"]+)"', line)

                if uri_match:
                    # Build subtitle URL with JWT token
                    sub_url = uri_match.group(1)
                    if not sub_url.startswith('http'):
                        base = self.config_url.rsplit('?', 1)[0].rsplit('/', 1)[0]
                        sub_url = urljoin(base + '/', sub_url) + jwt_token

                    subtitle_info = {
                        'url': sub_url,
                        'name': name_match.group(1) if name_match else 'Unknown',
                        'language': lang_match.group(1) if lang_match else None
                    }

                    # Add if not duplicate
                    if not any(s['url'] == subtitle_info['url'] for s in self.subtitles):
                        self.subtitles.append(subtitle_info)
                        playlist_subs_found += 1

        if playlist_subs_found > 0:
            print(f"   [OK] {playlist_subs_found} subtitle(s) in master playlist")

        if not variants:
            raise Exception("No video variants found in config")

        def variant_label(v):
            # RESOLUTION often missing on MajorPlay; bandwidth is the stable id
            if v['resolution'] != 'unknown':
                return f"{v['resolution']} ({v['bandwidth']//1000} kbps)"
            return f"{v['bandwidth']//1000} kbps"

        # Resume: match by bandwidth (unique). Resolution alone collides as "unknown".
        selected = None
        if getattr(self, 'resume_mode', False):
            saved_bw = getattr(self, 'saved_bandwidth', None)
            if saved_bw is not None:
                for v in variants:
                    if v['bandwidth'] == saved_bw:
                        selected = v
                        print(f"\n   Using saved quality: {variant_label(selected)}")
                        break
            # Legacy state without bandwidth: only safe if resolution is unique & real
            if selected is None:
                saved_res = getattr(self, 'saved_resolution', None)
                if saved_res and saved_res != 'unknown':
                    matches = [v for v in variants if v['resolution'] == saved_res]
                    if len(matches) == 1:
                        selected = matches[0]
                        print(f"\n   Using saved quality: {variant_label(selected)}")
            if selected is None:
                print(f"\n   [!] Saved quality not available, prompting for selection")

        # Prompt user to select resolution if not resuming
        if selected is None:
            print(f"\n   Available qualities:")
            for i, v in enumerate(variants):
                print(f"   {i+1}. {variant_label(v)}")

            highest_idx = variants.index(max(variants, key=lambda x: x['bandwidth']))
            while selected is None:
                try:
                    choice = input(f"\n   Choose quality (1-{len(variants)}, Enter for highest): ").strip()
                    if not choice:
                        selected = variants[highest_idx]
                    else:
                        idx = int(choice) - 1
                        if 0 <= idx < len(variants):
                            selected = variants[idx]
                        else:
                            print(f"   Invalid choice. Please enter a number between 1 and {len(variants)}")
                except ValueError:
                    print(f"   Invalid input. Please enter a number between 1 and {len(variants)}")
                except (EOFError, KeyboardInterrupt):
                    selected = variants[highest_idx]
                    print(f"\n   Using highest quality")

            print(f"   Selected: {variant_label(selected)}")

        # Store for metadata / resume (bandwidth is the match key)
        self.selected_resolution = selected['resolution']
        self.selected_bandwidth = selected['bandwidth']

        # Construct base without query
        base = self.config_url.rsplit('?', 1)[0].rsplit('/', 1)[0]

        # Build URLs with JWT token (already extracted earlier)
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

            # Find subtitle URLs (fallback for subtitles not in master playlist)
            network_subs_found = 0
            for req in network_data:
                url = req.get('url', '')
                if 'majorplay.net' in url and '.vtt' in url:
                    # Check if not already added from master playlist
                    if not any(s['url'] == url for s in self.subtitles):
                        # Extract filename for display (no language info available from network capture)
                        filename = url.split('/')[-1].split('?')[0]
                        self.subtitles.append({
                            'url': url,
                            'name': filename.replace('.vtt', ''),
                            'language': None  # Unknown from network capture
                        })
                        network_subs_found += 1

            if network_subs_found > 0:
                print(f"   [OK] {network_subs_found} subtitle(s) from network capture")
            elif self.subtitles:
                print(f"   [OK] {len(self.subtitles)} subtitle(s) found")

            if not self.config_url:
                print(f"   [X] Config URL not found in capture")
                print(f"   Make sure video played past the ad (skip after 8 sec)")
                return False

            return True

        except Exception as e:
            print(f"   [X] Error parsing captured data: {e}")
            return False

    def download_segments(self, playlist_url, output_prefix):
        """Download all segments from fMP4 playlist with init segment (parallel)"""
        # Fetch playlist
        response = self.scraper.get(playlist_url)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch playlist: {response.status_code}")

        # Extract JWT token from playlist URL to pass to segments
        jwt_token = ''
        if '?' in playlist_url:
            jwt_token = '?' + playlist_url.split('?', 1)[1]

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
                    # Resolve relative URL and preserve JWT token
                    if not init_url.startswith('http'):
                        base = playlist_url.rsplit('/', 1)[0].rsplit('?', 1)[0]
                        init_url = urljoin(base + '/', init_url) + jwt_token
            elif line and not line.startswith('#'):
                # Resolve segment URL and append JWT token
                seg_url = line
                if not seg_url.startswith('http'):
                    # Relative URL - resolve against base and append JWT token
                    base = playlist_url.rsplit('/', 1)[0].rsplit('?', 1)[0]
                    seg_url = urljoin(base + '/', seg_url) + jwt_token
                else:
                    # Absolute URL - append JWT token if not already present
                    if '?' not in seg_url:
                        seg_url = seg_url + jwt_token
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

            # Continue download: skip if segment already exists with content
            if os.path.exists(seg_file) and os.path.getsize(seg_file) > 0:
                return seg_file

            for attempt in range(retries):
                try:
                    seg_response = self.scraper.get(seg_url, timeout=30)
                    if seg_response.status_code != 200:
                        # Debug logging for 401 errors
                        if seg_response.status_code == 401:
                            print(f"\n   [DEBUG] Segment {i} got 401 Unauthorized")
                            print(f"   [DEBUG] URL: {seg_url[:100]}{'...' if len(seg_url) > 100 else ''}")
                            print(f"   [DEBUG] Has query params: {'?' in seg_url}")
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

        # Manually manage executor for proper Ctrl+C handling
        executor = ThreadPoolExecutor(max_workers=5)
        try:
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
        except KeyboardInterrupt:
            print(f"\n\n   [!] Download cancelled by user (Ctrl+C)")
            print(f"   Progress: {completed}/{len(segments)} segments completed")
            print(f"   Continue download will skip completed segments on next run")
            # Don't wait for workers - cancel immediately
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        finally:
            # Normal shutdown for non-interrupted case
            if not executor._shutdown:
                executor.shutdown(wait=True)

        return {'segments': segment_files, 'init_data': init_data}

    def download_with_ffmpeg(self, output_file, subtitle_url=None, segments_dir=None):
        """Download segments then binary concat fMP4 fragments"""
        print(f"[5/6] Downloading video...")

        if not self.video_playlist_url:
            raise Exception("No video playlist URL")

        # Use segments_dir for intermediate files if provided, otherwise use output_file directory
        if segments_dir:
            base_name = os.path.splitext(os.path.basename(output_file))[0]
            segments_prefix = f"{segments_dir}/{base_name}"
        else:
            segments_prefix = output_file

        try:
            # Download video segments
            print(f"   Downloading video segments...")
            video_data = self.download_segments(self.video_playlist_url, f"{segments_prefix}_video")
            video_segments = video_data['segments']
            video_init = video_data['init_data']

            # Download audio segments if separate
            audio_segments = None
            audio_init = None
            if self.audio_playlist_url:
                print(f"   Downloading audio segments...")
                audio_data = self.download_segments(self.audio_playlist_url, f"{segments_prefix}_audio")
                audio_segments = audio_data['segments']
                audio_init = audio_data['init_data']

            # Download subtitle (keep in movie directory, not segments)
            subtitle_file = None
            if subtitle_url:
                print(f"   Downloading subtitle...")
                # Strip extension from output_file to avoid .mkv.vtt
                subtitle_file = f"{os.path.splitext(output_file)[0]}.vtt"
                sub_response = self.scraper.get(subtitle_url)
                if sub_response.status_code == 200:
                    with open(subtitle_file, 'wb') as f:
                        f.write(sub_response.content)

            # Binary concat: init + frag1 + frag2 + ... = complete.mp4
            print(f"   Concatenating fMP4 fragments...")
            video_complete = f"{segments_prefix}_video_complete.mp4"
            with open(video_complete, 'wb') as out:
                if video_init:
                    out.write(video_init)
                for seg_file in video_segments:
                    with open(seg_file, 'rb') as seg:
                        out.write(seg.read())

            # Binary concat audio if separate
            audio_complete = None
            if audio_segments:
                audio_complete = f"{segments_prefix}_audio_complete.mp4"
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

    def load_download_metadata(self, video_name):
        """Load metadata from previous download if exists"""
        movie_dir = f"output/{video_name}"
        metadata_file = f"{movie_dir}/download_state.json"

        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return None
        return None

    def save_download_metadata(self, video_name, resolution, subtitle_info, bandwidth=None):
        """Save download metadata for resume capability"""
        movie_dir = f"output/{video_name}"
        metadata_file = f"{movie_dir}/download_state.json"

        # Create directory if it doesn't exist
        os.makedirs(movie_dir, exist_ok=True)

        metadata = {
            'video_name': video_name,
            'resolution': resolution,
            'bandwidth': bandwidth,
            'subtitle': subtitle_info,
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }

        try:
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"   [DEBUG] Failed to save metadata: {e}")

    def get_language_from_subtitle_url(self, url):
        """Extract language name from subtitle URL path (e.g., /i18n/id/ -> Indonesian)"""
        if not url:
            return None
        match = re.search(r'/i18n/(\w+)/', url)
        if match:
            lang_code = match.group(1)
            # Map common language codes to readable names
            lang_map = {
                'id': 'Indonesian',
                'en': 'English',
                'es': 'Spanish',
                'pt': 'Portuguese',
                'fr': 'French',
                'de': 'German',
                'zh': 'Chinese',
                'ja': 'Japanese',
                'ko': 'Korean',
                'ar': 'Arabic',
                'ru': 'Russian',
                'it': 'Italian',
                'nl': 'Dutch',
                'pl': 'Polish',
                'tr': 'Turkish',
                'vi': 'Vietnamese',
                'th': 'Thai',
            }
            return lang_map.get(lang_code, lang_code.upper())
        return None

    def format_subtitle_label(self, sub_info, index=None):
        """Human-readable subtitle label. Handles playlist NAME/LANGUAGE and hash-only capture URLs."""
        if not sub_info:
            return 'none'

        name = (sub_info.get('name') or '').strip()
        language = sub_info.get('language')
        url = sub_info.get('url', '')

        # language may be a code ("id") or already a display name from metadata
        lang_from_url = self.get_language_from_subtitle_url(url)
        lang_map = {
            'id': 'Indonesian', 'en': 'English', 'es': 'Spanish', 'pt': 'Portuguese',
            'fr': 'French', 'de': 'German', 'zh': 'Chinese', 'ja': 'Japanese',
            'ko': 'Korean', 'ar': 'Arabic', 'ru': 'Russian', 'it': 'Italian',
            'nl': 'Dutch', 'pl': 'Polish', 'tr': 'Turkish', 'vi': 'Vietnamese',
            'th': 'Thai',
        }
        if language:
            lang_key = str(language).lower()
            language_display = lang_map.get(lang_key, language)
        else:
            language_display = lang_from_url

        # Hash-like capture filenames are not useful to show
        is_hash = (
            name
            and name != 'Unknown'
            and len(name) >= 16
            and name.replace('-', '').replace('_', '').isalnum()
        )
        if is_hash or not name or name == 'Unknown':
            if language_display:
                return f"{language_display} Subtitle"
            return f"Subtitle {index}" if index is not None else "Subtitle"

        if language_display and language_display.lower() not in name.lower():
            return f"{name} ({language_display})"
        return name

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
            # Manual mode: config_url already set — skip network capture

            # Check for existing download to offer resume
            self.resume_mode = False
            metadata = self.load_download_metadata(self.video_name)
            if metadata:
                movie_dir = f"output/{self.video_name}"
                segments_dir = f"{movie_dir}/segments"
                if os.path.exists(segments_dir):
                    segment_count = len([f for f in os.listdir(segments_dir) if f.endswith('.m4s')])
                    print(f"\n[!] Previous download found:")
                    res = metadata.get('resolution', 'unknown')
                    bw = metadata.get('bandwidth')
                    if res and res != 'unknown' and bw:
                        quality_display = f"{res} ({bw // 1000} kbps)"
                    elif bw:
                        quality_display = f"{bw // 1000} kbps"
                    else:
                        quality_display = res or 'unknown'
                    print(f"   Quality: {quality_display}")
                    # Old state without bandwidth can't safely resume multi-unknown masters
                    if bw is None and (not res or res == 'unknown'):
                        print(f"   [!] Incomplete quality info (pre-bandwidth state) — choose Fresh (n)")
                    sub_info = metadata.get('subtitle')
                    print(f"   Subtitle: {self.format_subtitle_label(sub_info)}")
                    print(f"   Segments: {segment_count} files")

                    choice = None
                    while choice is None:
                        try:
                            response = input("\n   Continue previous download? (Y/n): ").strip().lower()
                            if response == '' or response == 'y':
                                choice = 'continue'
                            elif response == 'n':
                                choice = 'fresh'
                            else:
                                print("   Invalid input. Please enter 'y' or 'n'")
                        except (EOFError, KeyboardInterrupt):
                            choice = 'continue'
                            print("\n   Continuing with previous settings")

                    if choice == 'continue':
                        self.resume_mode = True
                        self.saved_resolution = metadata.get('resolution')
                        self.saved_bandwidth = metadata.get('bandwidth')
                        self.saved_subtitle = metadata.get('subtitle')
                        print(f"   [OK] Resuming with saved settings")
                    elif choice == 'fresh':
                        # Delete old segments and metadata for fresh start
                        import shutil
                        if os.path.exists(segments_dir):
                            shutil.rmtree(segments_dir)
                            print(f"   [OK] Deleted {segment_count} old segments")

                        metadata_file = f"{movie_dir}/download_state.json"
                        if os.path.exists(metadata_file):
                            os.remove(metadata_file)

            # Step 3/4: Get config playlist
            if not self.get_config_playlist():
                return False

            # Step 4/5: Check subtitles
            subtitle_url = None
            subtitle_handled_by_resume = False  # Flag to skip prompting when resume mode handles it

            if self.subtitles:
                # Check if resuming with saved subtitle choice
                if hasattr(self, 'resume_mode') and self.resume_mode and hasattr(self, 'saved_subtitle'):
                    if self.saved_subtitle is not None:
                        # Match by base URL (ignore JWT token in query params)
                        saved_base_url = self.saved_subtitle.get('url', '').split('?')[0]
                        for sub_info in self.subtitles:
                            sub_base_url = sub_info['url'].split('?')[0]
                            if sub_base_url == saved_base_url:
                                subtitle_url = sub_info['url']  # fresh URL with new JWT
                                print(f"[4/6] Using saved subtitle: {self.format_subtitle_label(sub_info)}")
                                subtitle_handled_by_resume = True
                                break
                        if not subtitle_handled_by_resume:
                            print(f"[4/6] Saved subtitle not available, prompting for selection")
                    else:
                        # saved_subtitle is None - user previously chose no subtitle
                        print(f"[4/6] Skipping subtitle (previous choice: none)")
                        subtitle_handled_by_resume = True

                # Prompt for subtitle selection if not handled by resume mode
                if not subtitle_handled_by_resume and len(self.subtitles) == 1:
                    sub_info = self.subtitles[0]
                    print(f"[4/6] Subtitle found: {self.format_subtitle_label(sub_info)}")
                    include_subtitle = None
                    while include_subtitle is None:
                        try:
                            choice = input("   Include subtitle? (Y/n): ").strip().lower()
                            if choice == '' or choice == 'y':
                                include_subtitle = True
                            elif choice == 'n':
                                include_subtitle = False
                            else:
                                print("   Invalid input. Please enter 'y' for yes or 'n' for no")
                        except EOFError:
                            include_subtitle = True
                            print("\n   Including subtitle")

                    if include_subtitle:
                        subtitle_url = sub_info['url']
                    else:
                        print("   Subtitle skipped")
                elif not subtitle_handled_by_resume:
                    print(f"[4/6] {len(self.subtitles)} subtitles found")
                    print("\n   Available subtitles:")
                    for i, sub_info in enumerate(self.subtitles):
                        print(f"   {i+1}. {self.format_subtitle_label(sub_info, index=i + 1)}")

                    selected = None
                    while selected is None:
                        try:
                            choice = input(f"\n   Choose subtitle (1-{len(self.subtitles)}, or 'n' to skip): ").strip().lower()
                            if choice == 'n':
                                selected = 'skip'
                            elif choice:
                                idx = int(choice) - 1
                                if 0 <= idx < len(self.subtitles):
                                    selected = idx
                                else:
                                    print(f"   Invalid choice. Please enter a number between 1 and {len(self.subtitles)}, or 'n' to skip")
                            else:
                                print(f"   Invalid input. Please enter a number between 1 and {len(self.subtitles)}, or 'n' to skip")
                        except ValueError:
                            print(f"   Invalid input. Please enter a number between 1 and {len(self.subtitles)}, or 'n' to skip")
                        except EOFError:
                            selected = 0
                            print(f"\n   Using first subtitle")

                    if selected == 'skip':
                        print("   Subtitle skipped")
                    else:
                        sub_info = self.subtitles[selected]
                        subtitle_url = sub_info['url']
                        print(f"   Selected: {self.format_subtitle_label(sub_info, index=selected + 1)}")

            # Save metadata for resume capability (only in normal mode, not resume mode)
            if not hasattr(self, 'resume_mode') or not self.resume_mode:
                # Find subtitle info if subtitle was selected
                subtitle_info = None
                if subtitle_url:
                    for sub in self.subtitles:
                        if sub['url'] == subtitle_url:
                            subtitle_info = sub.copy()  # Make a copy so we don't modify the original
                            # Parse language from URL if not already set
                            if not subtitle_info.get('language'):
                                lang_from_url = self.get_language_from_subtitle_url(subtitle_info['url'])
                                if lang_from_url:
                                    subtitle_info['language'] = lang_from_url
                            break
                self.save_download_metadata(
                    self.video_name,
                    self.selected_resolution,
                    subtitle_info,
                    getattr(self, 'selected_bandwidth', None),
                )

            # Step 5/6: Download
            movie_dir = f"output/{self.video_name}"
            segments_dir = f"{movie_dir}/segments"
            os.makedirs(segments_dir, exist_ok=True)
            output = f"{movie_dir}/{self.video_name}.mkv"
            if not self.download_with_ffmpeg(output, subtitle_url, segments_dir):
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
    print("   Downloads videos from IDLIX")
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
