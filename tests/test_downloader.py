#!/usr/bin/env python3
"""
Comprehensive unit tests for IdlixDownloader
Tests core functionality with mocked dependencies
"""

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


class TestVideoInfo(unittest.TestCase):
    """Test video info extraction"""

    def setUp(self):
        self.downloader = MajorPlayDownloader()

    def test_extract_video_id_and_title(self):
        """Test video ID and title extraction"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<div data-postid="12345">Content</div><meta itemprop="name" content="Test Movie">'

        with patch.object(self.downloader.scraper, 'get', return_value=mock_response):
            result = self.downloader.get_video_info('https://z2.idlixku.com/movie/test')
            self.assertTrue(result)
            self.assertEqual(self.downloader.video_id, '12345')
            self.assertEqual(self.downloader.video_name, 'Test Movie')

    def test_extract_title_only(self):
        """Test title extraction when ID not found"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<meta itemprop="name" content="Awesome Movie">'

        with patch.object(self.downloader.scraper, 'get', return_value=mock_response):
            result = self.downloader.get_video_info('https://z2.idlixku.com/movie/test')
            self.assertTrue(result)
            self.assertEqual(self.downloader.video_name, 'Awesome Movie')
            self.assertIsNone(self.downloader.video_id)

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


if __name__ == '__main__':
    unittest.main()
