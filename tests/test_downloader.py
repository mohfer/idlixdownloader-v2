#!/usr/bin/env python3
"""
Basic tests for IdlixDownloader package
"""

import sys

def test_imports():
    """Test that package imports work correctly"""
    print("Testing IdlixDownloader package...")
    print("\nTest 1: Check package imports")

    try:
        from idlixdownloader import MajorPlayDownloader
        print("[OK] Package imports successful")
        return True
    except ImportError as e:
        print(f"[ERROR] Import failed: {e}")
        return False

def test_dependencies():
    """Test that required dependencies are available"""
    print("\nTest 2: Check dependencies")

    try:
        import cloudscraper
        print("[OK] cloudscraper installed")
    except ImportError:
        print("[ERROR] cloudscraper not found. Install: uv sync")
        return False

    try:
        import playwright
        print("[OK] playwright installed")
    except ImportError:
        print("[ERROR] playwright not found. Install: uv sync")
        return False

    print("\n" + "="*50)
    print("Tests complete!")
    print("="*50)
    print("\nUsage:")
    print("  uv run idlix <video_url>")
    print("\nExample:")
    print("  uv run idlix https://z2.idlixku.com/movie/toy-story-5-2026")

    return True

if __name__ == "__main__":
    success = test_imports() and test_dependencies()
    sys.exit(0 if success else 1)
