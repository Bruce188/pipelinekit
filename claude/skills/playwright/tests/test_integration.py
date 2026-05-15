"""
Integration tests for playwright skill.

These tests require playwright to be installed and will launch a real browser.
Run with: pytest tests/test_integration.py -m integration
"""

import pytest
import os
import sys
from pathlib import Path
import tempfile

# Add scripts to path
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def check_playwright_installed():
    """Check if playwright is installed."""
    try:
        from playwright.sync_api import sync_playwright
        return True
    except ImportError:
        pytest.skip("Playwright not installed. Run: pip install playwright && python -m playwright install chromium")


class TestPlaywrightIntegration:
    """Integration tests with real browser."""

    def test_navigate_to_real_site(self, check_playwright_installed):
        """Test navigating to a real website."""
        from playwright_controller import PlaywrightNative

        with PlaywrightNative() as pw:
            result = pw.navigate("https://example.com")

            assert result["success"] is True
            assert "example.com" in result["url"]
            assert result["title"] is not None
            assert result["status"] == 200

    def test_take_real_screenshot(self, check_playwright_installed):
        """Test taking a real screenshot."""
        from playwright_controller import PlaywrightNative

        with tempfile.TemporaryDirectory() as tmpdir:
            screenshot_path = os.path.join(tmpdir, "test_screenshot.png")

            with PlaywrightNative() as pw:
                pw.navigate("https://example.com")
                result = pw.take_screenshot(filename=screenshot_path)

                assert result["success"] is True
                assert os.path.exists(screenshot_path)
                assert os.path.getsize(screenshot_path) > 0

    def test_get_real_content(self, check_playwright_installed):
        """Test getting content from real page."""
        from playwright_controller import PlaywrightNative

        with PlaywrightNative() as pw:
            pw.navigate("https://example.com")
            result = pw.get_content()

            assert result["success"] is True
            assert "example.com" in result["url"]
            assert len(result["content"]) > 0
            assert "<html>" in result["content"].lower()

    def test_javascript_evaluation(self, check_playwright_installed):
        """Test JavaScript evaluation on real page."""
        from playwright_controller import PlaywrightNative

        with PlaywrightNative() as pw:
            pw.navigate("https://example.com")
            result = pw.evaluate("document.title")

            assert result["success"] is True
            assert result["result"] is not None

    def test_full_workflow(self, check_playwright_installed):
        """Test complete workflow with real browser."""
        from playwright_controller import PlaywrightNative

        with tempfile.TemporaryDirectory() as tmpdir:
            screenshot_path = os.path.join(tmpdir, "workflow_screenshot.png")

            with PlaywrightNative() as pw:
                # Navigate
                nav_result = pw.navigate("https://example.com")
                assert nav_result["success"] is True

                # Get content
                content_result = pw.get_content()
                assert content_result["success"] is True
                assert len(content_result["content"]) > 0

                # Take screenshot
                screenshot_result = pw.take_screenshot(filename=screenshot_path)
                assert screenshot_result["success"] is True
                assert os.path.exists(screenshot_path)

                # Evaluate JavaScript
                js_result = pw.evaluate("document.title")
                assert js_result["success"] is True
