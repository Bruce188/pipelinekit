"""
Pytest configuration and fixtures for playwright skill tests.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

# Add the scripts directory to the path
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))


@pytest.fixture
def mock_playwright():
    """Mock playwright instance."""
    with patch('playwright_controller.sync_playwright') as mock_pw:
        mock_instance = MagicMock()
        mock_context_manager = MagicMock()
        mock_context_manager.__enter__ = Mock(return_value=mock_instance)
        mock_context_manager.__exit__ = Mock(return_value=False)
        mock_pw.return_value.start.return_value = mock_instance

        # Mock browser
        mock_browser = MagicMock()
        mock_instance.chromium.launch.return_value = mock_browser

        # Mock context
        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context

        # Mock page
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page

        # Configure page mock methods
        mock_page.goto.return_value = Mock(status=200)
        mock_page.url = "https://example.com/"
        mock_page.title.return_value = "Example Domain"
        mock_page.content.return_value = "<html><body>Test</body></html>"

        yield {
            'playwright': mock_instance,
            'browser': mock_browser,
            'context': mock_context,
            'page': mock_page
        }


@pytest.fixture
def playwright_controller(mock_playwright):
    """Create PlaywrightNative instance with mocked dependencies."""
    from playwright_controller import PlaywrightNative
    controller = PlaywrightNative()
    return controller


@pytest.fixture
def sample_html():
    """Sample HTML for testing."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Test Page</title></head>
    <body>
        <h1>Test Heading</h1>
        <form id="test-form">
            <input type="text" name="username" id="username" />
            <input type="email" name="email" id="email" />
            <input type="password" name="password" id="password" />
            <input type="checkbox" name="agree" id="agree" />
            <select name="country" id="country">
                <option value="us">United States</option>
                <option value="uk">United Kingdom</option>
            </select>
            <button type="submit">Submit</button>
        </form>
    </body>
    </html>
    """


@pytest.fixture
def temp_screenshot_dir(tmp_path):
    """Create temporary directory for screenshots."""
    screenshot_dir = tmp_path / "screenshots"
    screenshot_dir.mkdir()
    return screenshot_dir
