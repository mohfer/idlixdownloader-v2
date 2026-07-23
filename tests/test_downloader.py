#!/usr/bin/env python3
"""
Comprehensive unit tests for IdlixDownloader
Tests core functionality with mocked dependencies
"""

import os
import unittest
from unittest.mock import Mock, patch
from idlixdownloader import MajorPlayDownloader


class TestParseNetworkCapture(unittest.TestCase):
    """Test network capture parsing with various conditions"""

    def setUp(self):
        self.downloader = MajorPlayDownloader()

    def test_parse_config_url_found(self):
        """Test successful config URL extraction"""
        data = {
            'requests': [
                {'url': 'https://e2e.majorplay.net/v/z5/123/config-abc.json?t=token123'}
            ],
            'page_title': 'Test Movie'
        }
        result = self.downloader.parse_network_capture(data)
        self.assertTrue(result)
        self.assertIsNotNone(self.downloader.config_url)
        self.assertIn('config-', self.downloader.config_url)

    def test_parse_config_url_not_found(self):
        """Test when config URL is missing"""
        data = {
            'requests': [
                {'url': 'https://example.com/video.mp4'}
            ],
            'page_title': 'Test Movie'
        }
        result = self.downloader.parse_network_capture(data)
        self.assertFalse(result)

    def test_parse_empty_requests(self):
        """Test with empty request list"""
        data = {'requests': [], 'page_title': 'Test Movie'}
        result = self.downloader.parse_network_capture(data)
        self.assertFalse(result)

    def test_parse_single_subtitle(self):
        """Test single subtitle extraction"""
        data = {
            'requests': [
                {'url': 'https://e2e.majorplay.net/v/z5/123/config-abc.json?t=token'},
                {'url': 'https://e2e.majorplay.net/subtitle.vtt'}
            ],
            'page_title': 'Test Movie'
        }
        self.downloader.parse_network_capture(data)
        self.assertEqual(len(self.downloader.subtitles), 1)

    def test_parse_multiple_subtitles(self):
        """Test multiple subtitle extraction"""
        data = {
            'requests': [
                {'url': 'https://e2e.majorplay.net/v/z5/123/config-abc.json?t=token'},
                {'url': 'https://e2e.majorplay.net/subtitle-en.vtt'},
                {'url': 'https://e2e.majorplay.net/subtitle-id.vtt'},
                {'url': 'https://e2e.majorplay.net/subtitle-es.vtt'}
            ],
            'page_title': 'Test Movie'
        }
        self.downloader.parse_network_capture(data)
        self.assertEqual(len(self.downloader.subtitles), 3)

    def test_parse_duplicate_subtitles_filtered(self):
        """Test duplicate subtitle URLs are filtered"""
        data = {
            'requests': [
                {'url': 'https://e2e.majorplay.net/v/z5/123/config-abc.json?t=token'},
                {'url': 'https://e2e.majorplay.net/subtitle.vtt'},
                {'url': 'https://e2e.majorplay.net/subtitle.vtt'},
            ],
            'page_title': 'Test Movie'
        }
        self.downloader.parse_network_capture(data)
        self.assertEqual(len(self.downloader.subtitles), 1)

    def test_parse_no_subtitles(self):
        """Test when no subtitles found"""
        data = {
            'requests': [
                {'url': 'https://e2e.majorplay.net/v/z5/123/config-abc.json?t=token'}
            ],
            'page_title': 'Test Movie'
        }
        self.downloader.parse_network_capture(data)
        self.assertEqual(len(self.downloader.subtitles), 0)

    def test_parse_title_branding_removal(self):
        """Test site branding removal from title"""
        test_cases = [
            ('Movie Title / IDLIX', 'Movie Title'),
            ('Movie Title - IDLIX', 'Movie Title'),
            ('Movie Title | Streaming Online', 'Movie Title'),
            ('Movie Title – idlix premium', 'Movie Title'),
            ('Movie Title', 'Movie Title'),
        ]
        for input_title, expected_title in test_cases:
            self.downloader.subtitles = []
            data = {
                'requests': [
                    {'url': 'https://e2e.majorplay.net/v/z5/123/config-abc.json?t=token'}
                ],
                'page_title': input_title
            }
            self.downloader.parse_network_capture(data)
            self.assertEqual(self.downloader.video_name, expected_title)

    def test_parse_title_special_chars_cleaned(self):
        """Test title with special characters is cleaned"""
        data = {
            'requests': [
                {'url': 'https://e2e.majorplay.net/v/z5/123/config-abc.json?t=token'}
            ],
            'page_title': 'Movie: The "Best" <Title>?'
        }
        self.downloader.parse_network_capture(data)
        self.assertNotIn(':', self.downloader.video_name)
        self.assertNotIn('?', self.downloader.video_name)
        self.assertNotIn('"', self.downloader.video_name)

    def test_parse_exception_handling(self):
        """Test exception during parsing"""
        data = None
        result = self.downloader.parse_network_capture(data)
        self.assertFalse(result)


class TestConfigPlaylist(unittest.TestCase):
    """Test config playlist parsing"""

    def setUp(self):
        self.downloader = MajorPlayDownloader()
        self.downloader.config_url = 'https://e2e.majorplay.net/config.json?t=token123'

    @patch('idlixdownloader.downloader.input')
    def test_parse_config_highest_resolution(self, mock_input):
        """Test selecting highest resolution (default)"""
        mock_input.return_value = ''

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '''#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080
video-1080p.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720
video-720p.m3u8
#EXT-X-MEDIA:TYPE=AUDIO,URI="audio.m3u8"
'''

        with patch.object(self.downloader.scraper, 'get', return_value=mock_response):
            result = self.downloader.get_config_playlist()
            self.assertTrue(result)
            self.assertIn('1080p', self.downloader.video_playlist_url)

    @patch('idlixdownloader.downloader.input')
    def test_parse_config_selected_resolution(self, mock_input):
        """Test selecting specific resolution"""
        mock_input.return_value = '2'

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '''#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080
video-1080p.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720
video-720p.m3u8
'''

        with patch.object(self.downloader.scraper, 'get', return_value=mock_response):
            result = self.downloader.get_config_playlist()
            self.assertTrue(result)
            self.assertIn('720p', self.downloader.video_playlist_url)

    @patch('idlixdownloader.downloader.input')
    def test_parse_config_invalid_choice_retries(self, mock_input):
        """Test invalid resolution choice triggers retry"""
        mock_input.side_effect = ['99', '1']

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '''#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080
video-1080p.m3u8
'''

        with patch.object(self.downloader.scraper, 'get', return_value=mock_response):
            result = self.downloader.get_config_playlist()
            self.assertTrue(result)
            self.assertEqual(mock_input.call_count, 2)

    @patch('idlixdownloader.downloader.input')
    def test_parse_config_non_numeric_retries(self, mock_input):
        """Test non-numeric input triggers retry"""
        mock_input.side_effect = ['abc', '1']

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '''#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080
video-1080p.m3u8
'''

        with patch.object(self.downloader.scraper, 'get', return_value=mock_response):
            result = self.downloader.get_config_playlist()
            self.assertTrue(result)
            self.assertEqual(mock_input.call_count, 2)

    def test_parse_config_no_variants(self):
        """Test error when no video variants found"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '#EXTM3U\n'

        with patch.object(self.downloader.scraper, 'get', return_value=mock_response):
            with self.assertRaises(Exception) as context:
                self.downloader.get_config_playlist()
            self.assertIn('No video variants', str(context.exception))

    def test_parse_config_url_not_set(self):
        """Test when config URL is not set"""
        self.downloader.config_url = None
        result = self.downloader.get_config_playlist()
        self.assertFalse(result)

    def test_resume_matches_by_bandwidth_when_resolution_unknown(self):
        """Resume must pick by bandwidth; all-unknown RESOLUTION collides otherwise"""
        self.downloader.resume_mode = True
        self.downloader.saved_resolution = 'unknown'
        self.downloader.saved_bandwidth = 5800000

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '''#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=700000
video-low.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=3500000
video-mid.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=5800000
video-high.m3u8
'''

        with patch.object(self.downloader.scraper, 'get', return_value=mock_response):
            result = self.downloader.get_config_playlist()
            self.assertTrue(result)
            self.assertIn('video-high', self.downloader.video_playlist_url)
            self.assertEqual(self.downloader.selected_bandwidth, 5800000)

    def test_resume_legacy_unknown_without_bandwidth_prompts(self):
        """Legacy state with only resolution=unknown cannot safely auto-match"""
        self.downloader.resume_mode = True
        self.downloader.saved_resolution = 'unknown'
        self.downloader.saved_bandwidth = None

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '''#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=700000
video-low.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=5800000
video-high.m3u8
'''

        with patch('idlixdownloader.downloader.input', return_value='') as mock_input:
            with patch.object(self.downloader.scraper, 'get', return_value=mock_response):
                result = self.downloader.get_config_playlist()
                self.assertTrue(result)
                mock_input.assert_called()
                self.assertIn('video-high', self.downloader.video_playlist_url)


class TestVideoInfo(unittest.TestCase):
    """Test video info extraction"""

    def setUp(self):
        self.downloader = MajorPlayDownloader()

    def test_extract_title(self):
        """Test title extraction from meta tag"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<div data-postid="12345">Content</div><meta itemprop="name" content="Test Movie">'

        with patch.object(self.downloader.scraper, 'get', return_value=mock_response):
            result = self.downloader.get_video_info('https://z2.idlixku.com/movie/test')
            self.assertTrue(result)
            self.assertEqual(self.downloader.video_name, 'Test Movie')

    def test_fallback_to_url_slug(self):
        """Test fallback to URL slug when title not found"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<html><body>No meta tag</body></html>'

        with patch.object(self.downloader.scraper, 'get', return_value=mock_response):
            result = self.downloader.get_video_info('https://z2.idlixku.com/movie/toy-story-5')
            self.assertTrue(result)
            self.assertEqual(self.downloader.video_name, 'toy-story-5')

    def test_http_error(self):
        """Test HTTP error handling"""
        mock_response = Mock()
        mock_response.status_code = 404

        with patch.object(self.downloader.scraper, 'get', return_value=mock_response):
            with self.assertRaises(Exception) as context:
                self.downloader.get_video_info('https://z2.idlixku.com/movie/test')
            self.assertIn('Failed to fetch page', str(context.exception))


class TestMetadataSystem(unittest.TestCase):
    """Test metadata save/load functionality"""

    def setUp(self):
        self.downloader = MajorPlayDownloader()
        self.downloader.video_name = "Test Movie"

    def test_save_metadata_creates_directory(self):
        """Test that save_metadata creates output directory if not exists"""
        import tempfile
        import shutil

        with tempfile.TemporaryDirectory() as tmpdir:
            # Override output path temporarily
            original_cwd = os.getcwd()
            os.chdir(tmpdir)

            try:
                self.downloader.save_download_metadata("Test Movie", "1920x1080", None)
                self.assertTrue(os.path.exists(os.path.join(tmpdir, "output/Test Movie")))
                self.assertTrue(os.path.exists(os.path.join(tmpdir, "output/Test Movie/download_state.json")))
            finally:
                os.chdir(original_cwd)

    def test_load_metadata_not_exists(self):
        """Test loading metadata when file doesn't exist"""
        result = self.downloader.load_download_metadata("NonexistentMovie")
        self.assertIsNone(result)

    def test_save_and_load_metadata(self):
        """Test saving and loading metadata roundtrip"""
        import tempfile
        import shutil

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)

            try:
                subtitle_info = {
                    'url': 'https://example.com/subtitle.vtt',
                    'name': 'English',
                    'language': 'en'
                }

                self.downloader.save_download_metadata(
                    "Test Movie", "1920x1080", subtitle_info, bandwidth=5000000
                )
                loaded = self.downloader.load_download_metadata("Test Movie")

                self.assertIsNotNone(loaded)
                self.assertEqual(loaded['video_name'], "Test Movie")
                self.assertEqual(loaded['resolution'], "1920x1080")
                self.assertEqual(loaded['bandwidth'], 5000000)
                self.assertEqual(loaded['subtitle']['language'], 'en')
            finally:
                os.chdir(original_cwd)


class TestLanguageParsing(unittest.TestCase):
    """Test language extraction from subtitle URLs"""

    def setUp(self):
        self.downloader = MajorPlayDownloader()

    def test_parse_language_indonesian(self):
        """Test parsing Indonesian language code from URL"""
        url = "https://e2e.majorplay.net/v/z5/abc/i18n/id/subtitle.vtt?t=token"
        result = self.downloader.get_language_from_subtitle_url(url)
        self.assertEqual(result, "Indonesian")

    def test_parse_language_english(self):
        """Test parsing English language code from URL"""
        url = "https://e2e.majorplay.net/v/z5/abc/i18n/en/subtitle.vtt?t=token"
        result = self.downloader.get_language_from_subtitle_url(url)
        self.assertEqual(result, "English")

    def test_parse_language_unknown_code(self):
        """Test parsing unknown language code returns uppercase code"""
        url = "https://e2e.majorplay.net/v/z5/abc/i18n/xx/subtitle.vtt?t=token"
        result = self.downloader.get_language_from_subtitle_url(url)
        self.assertEqual(result, "XX")

    def test_parse_language_no_pattern(self):
        """Test URL without language pattern returns None"""
        url = "https://example.com/subtitle.vtt"
        result = self.downloader.get_language_from_subtitle_url(url)
        self.assertIsNone(result)

    def test_format_playlist_name_and_language(self):
        label = self.downloader.format_subtitle_label({
            'name': 'Bahasa Indonesia',
            'language': 'id',
            'url': 'https://e2e.majorplay.net/subs.vtt',
        })
        self.assertEqual(label, 'Bahasa Indonesia (Indonesian)')

    def test_format_hash_with_i18n_url(self):
        label = self.downloader.format_subtitle_label({
            'name': 'd0690e6eec95a54d285545da878c41af',
            'language': None,
            'url': 'https://e2e.majorplay.net/v/x/i18n/en/subtitle.vtt?t=tok',
        })
        self.assertEqual(label, 'English Subtitle')

    def test_format_hash_without_language(self):
        label = self.downloader.format_subtitle_label({
            'name': 'd0690e6eec95a54d285545da878c41af',
            'language': None,
            'url': 'https://e2e.majorplay.net/subs-legacy/d0690e6eec95a54d285545da878c41af.vtt',
        })
        self.assertEqual(label, 'Subtitle')

    def test_format_hash_without_language_indexed(self):
        label = self.downloader.format_subtitle_label({
            'name': 'd0690e6eec95a54d285545da878c41af',
            'language': None,
            'url': 'https://e2e.majorplay.net/subs-legacy/hash.vtt',
        }, index=2)
        self.assertEqual(label, 'Subtitle 2')

    def test_format_none_subtitle(self):
        self.assertEqual(self.downloader.format_subtitle_label(None), 'none')


if __name__ == '__main__':
    unittest.main()
