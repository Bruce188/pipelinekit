"""
Unit tests for PlaywrightNative controller.
"""

import pytest
import json
import os
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path


class TestPlaywrightNativeInitialization:
    """Test PlaywrightNative initialization and lifecycle."""

    def test_init_creates_none_attributes(self):
        """Test that initialization sets all attributes to None."""
        from playwright_controller import PlaywrightNative

        controller = PlaywrightNative()

        assert controller.playwright is None
        assert controller.browser is None
        assert controller.context is None
        assert controller.page is None

    def test_context_manager_enter(self, mock_playwright):
        """Test context manager __enter__ method."""
        from playwright_controller import PlaywrightNative

        controller = PlaywrightNative()
        result = controller.__enter__()

        assert result is controller
        assert controller.playwright is not None
        assert controller.browser is not None
        assert controller.context is not None
        assert controller.page is not None

    def test_context_manager_exit(self, mock_playwright):
        """Test context manager __exit__ method."""
        from playwright_controller import PlaywrightNative

        controller = PlaywrightNative()
        controller.start()

        controller.__exit__(None, None, None)

        assert controller.page is None
        assert controller.context is None
        assert controller.browser is None
        assert controller.playwright is None


class TestPlaywrightNativeNavigation:
    """Test navigation functionality."""

    def test_navigate_success(self, playwright_controller, mock_playwright):
        """Test successful navigation to URL."""
        result = playwright_controller.navigate("https://example.com")

        assert result["success"] is True
        assert result["url"] == "https://example.com/"
        assert result["title"] == "Example Domain"
        assert result["status"] == 200

        mock_playwright['page'].goto.assert_called_once()

    def test_navigate_with_different_urls(self, playwright_controller, mock_playwright):
        """Test navigation to different URLs."""
        urls = [
            "https://example.com",
            "https://google.com",
            "https://github.com"
        ]

        for url in urls:
            mock_playwright['page'].url = url
            result = playwright_controller.navigate(url)

            assert result["success"] is True
            assert result["url"] == url

    def test_navigate_error_handling(self, playwright_controller, mock_playwright):
        """Test navigation error handling."""
        mock_playwright['page'].goto.side_effect = Exception("Network error")

        result = playwright_controller.navigate("https://invalid.com")

        assert result["success"] is False
        assert "error" in result
        assert "Network error" in result["error"]

    def test_go_back(self, playwright_controller, mock_playwright):
        """Test browser back navigation."""
        mock_playwright['page'].url = "https://previous-page.com"

        result = playwright_controller.go_back()

        assert result["success"] is True
        assert result["url"] == "https://previous-page.com"
        mock_playwright['page'].go_back.assert_called_once()

    def test_reload(self, playwright_controller, mock_playwright):
        """Test page reload."""
        mock_playwright['page'].url = "https://example.com"

        result = playwright_controller.reload()

        assert result["success"] is True
        assert result["url"] == "https://example.com"
        mock_playwright['page'].reload.assert_called_once()


class TestPlaywrightNativeElementInteraction:
    """Test element interaction functionality."""

    def test_click_element(self, playwright_controller, mock_playwright):
        """Test clicking an element."""
        result = playwright_controller.click("#submit-button")

        assert result["success"] is True
        assert result["selector"] == "#submit-button"
        mock_playwright['page'].click.assert_called_once_with("#submit-button", button="left")

    def test_click_with_different_buttons(self, playwright_controller, mock_playwright):
        """Test clicking with different mouse buttons."""
        buttons = ["left", "right", "middle"]

        for button in buttons:
            result = playwright_controller.click(".element", button=button)

            assert result["success"] is True
            mock_playwright['page'].click.assert_called_with(".element", button=button)

    def test_double_click(self, playwright_controller, mock_playwright):
        """Test double-clicking an element."""
        result = playwright_controller.click(".element", double_click=True)

        assert result["success"] is True
        mock_playwright['page'].dblclick.assert_called_once_with(".element")

    def test_type_text(self, playwright_controller, mock_playwright):
        """Test typing text into an element."""
        result = playwright_controller.type_text("#input", "test text")

        assert result["success"] is True
        assert result["selector"] == "#input"
        assert result["text"] == "test text"
        mock_playwright['page'].fill.assert_called_once_with("#input", "test text")

    def test_type_text_with_delay(self, playwright_controller, mock_playwright):
        """Test typing text with delay."""
        result = playwright_controller.type_text("#input", "slow text", delay=100)

        assert result["success"] is True
        mock_playwright['page'].type.assert_called_once_with("#input", "slow text", delay=100)

    def test_hover(self, playwright_controller, mock_playwright):
        """Test hovering over an element."""
        result = playwright_controller.hover(".menu-item")

        assert result["success"] is True
        assert result["selector"] == ".menu-item"
        mock_playwright['page'].hover.assert_called_once_with(".menu-item")


class TestPlaywrightNativeScreenshots:
    """Test screenshot functionality."""

    @patch('os.path.abspath')
    @patch('datetime.datetime')
    def test_take_screenshot_default_filename(self, mock_datetime, mock_abspath, playwright_controller, mock_playwright, tmp_path):
        """Test taking screenshot with default filename."""
        expected_path = str(tmp_path / "screenshot_20240101_120000.png")
        mock_abspath.return_value = expected_path

        # Mock datetime.now().strftime()
        mock_now = Mock()
        mock_now.strftime.return_value = "20240101_120000"
        mock_datetime.now.return_value = mock_now

        result = playwright_controller.take_screenshot()

        assert result["success"] is True
        assert "filename" in result
        assert result["full_page"] is False

    def test_take_screenshot_custom_filename(self, playwright_controller, mock_playwright):
        """Test taking screenshot with custom filename."""
        result = playwright_controller.take_screenshot(filename="custom.png")

        assert result["success"] is True
        assert "custom.png" in result["filename"]

    def test_take_screenshot_full_page(self, playwright_controller, mock_playwright):
        """Test taking full page screenshot."""
        result = playwright_controller.take_screenshot(full_page=True)

        assert result["success"] is True
        assert result["full_page"] is True

        # Verify screenshot was called with full_page=True
        call_kwargs = mock_playwright['page'].screenshot.call_args[1]
        assert call_kwargs.get('full_page') is True

    def test_take_screenshot_with_selector(self, playwright_controller, mock_playwright):
        """Test taking screenshot of specific element."""
        mock_locator = MagicMock()
        mock_playwright['page'].locator.return_value = mock_locator

        result = playwright_controller.take_screenshot(selector=".specific-element")

        assert result["success"] is True
        mock_playwright['page'].locator.assert_called_once_with(".specific-element")
        mock_locator.screenshot.assert_called_once()

    def test_take_screenshot_adds_extension(self, playwright_controller, mock_playwright):
        """Test that screenshot adds .png extension if missing."""
        result = playwright_controller.take_screenshot(filename="test")

        assert result["success"] is True
        assert result["filename"].endswith(".png")


class TestPlaywrightNativeFormFilling:
    """Test form filling functionality."""

    def test_fill_form_text_fields(self, playwright_controller, mock_playwright):
        """Test filling text input fields."""
        fields = [
            {"selector": "#username", "value": "testuser", "type": "text"},
            {"selector": "#email", "value": "test@example.com", "type": "email"},
            {"selector": "#password", "value": "secret123", "type": "password"}
        ]

        result = playwright_controller.fill_form(fields)

        assert result["success"] is True
        assert len(result["fields"]) == 3
        assert mock_playwright['page'].fill.call_count == 3

    def test_fill_form_checkbox(self, playwright_controller, mock_playwright):
        """Test checking checkboxes."""
        fields = [
            {"selector": "#agree", "value": "true", "type": "checkbox"},
            {"selector": "#newsletter", "value": "false", "type": "checkbox"}
        ]

        result = playwright_controller.fill_form(fields)

        assert result["success"] is True
        mock_playwright['page'].check.assert_called_once_with("#agree")
        mock_playwright['page'].uncheck.assert_called_once_with("#newsletter")

    def test_fill_form_select(self, playwright_controller, mock_playwright):
        """Test selecting dropdown options."""
        fields = [
            {"selector": "#country", "value": "us", "type": "select"}
        ]

        result = playwright_controller.fill_form(fields)

        assert result["success"] is True
        mock_playwright['page'].select_option.assert_called_once_with("#country", "us")

    def test_fill_form_mixed_fields(self, playwright_controller, mock_playwright):
        """Test filling form with mixed field types."""
        fields = [
            {"selector": "#username", "value": "user", "type": "text"},
            {"selector": "#agree", "value": "yes", "type": "checkbox"},
            {"selector": "#country", "value": "uk", "type": "select"}
        ]

        result = playwright_controller.fill_form(fields)

        assert result["success"] is True
        assert len(result["fields"]) == 3


class TestPlaywrightNativeContentExtraction:
    """Test content extraction functionality."""

    def test_get_content(self, playwright_controller, mock_playwright):
        """Test getting page content."""
        mock_playwright['page'].url = "https://example.com"
        mock_playwright['page'].title.return_value = "Test Page"
        mock_playwright['page'].content.return_value = "<html><body>Test</body></html>"

        result = playwright_controller.get_content()

        assert result["success"] is True
        assert result["url"] == "https://example.com"
        assert result["title"] == "Test Page"
        assert "<html>" in result["content"]

    def test_get_text(self, playwright_controller, mock_playwright):
        """Test getting element text."""
        mock_locator = MagicMock()
        mock_locator.text_content.return_value = "Element text"
        mock_playwright['page'].locator.return_value = mock_locator

        result = playwright_controller.get_text(".element")

        assert result["success"] is True
        assert result["text"] == "Element text"
        assert result["selector"] == ".element"

    def test_get_attribute(self, playwright_controller, mock_playwright):
        """Test getting element attribute."""
        mock_locator = MagicMock()
        mock_locator.get_attribute.return_value = "attribute-value"
        mock_playwright['page'].locator.return_value = mock_locator

        result = playwright_controller.get_attribute(".element", "data-id")

        assert result["success"] is True
        assert result["value"] == "attribute-value"
        assert result["attribute"] == "data-id"


class TestPlaywrightNativeWaitOperations:
    """Test wait operations."""

    def test_wait_for_selector(self, playwright_controller, mock_playwright):
        """Test waiting for selector."""
        result = playwright_controller.wait_for_selector(".loading", timeout=5000)

        assert result["success"] is True
        assert result["selector"] == ".loading"
        mock_playwright['page'].wait_for_selector.assert_called_once_with(".loading", timeout=5000)

    def test_wait_for_selector_default_timeout(self, playwright_controller, mock_playwright):
        """Test waiting for selector with default timeout."""
        result = playwright_controller.wait_for_selector(".element")

        assert result["success"] is True
        # Verify default timeout of 30000ms is used
        call_kwargs = mock_playwright['page'].wait_for_selector.call_args[1]
        assert call_kwargs.get('timeout') == 30000


class TestPlaywrightNativeJavaScriptEvaluation:
    """Test JavaScript evaluation."""

    def test_evaluate_expression(self, playwright_controller, mock_playwright):
        """Test evaluating JavaScript expression."""
        mock_playwright['page'].evaluate.return_value = {"data": "result"}

        result = playwright_controller.evaluate("return document.title")

        assert result["success"] is True
        assert result["result"] == {"data": "result"}
        mock_playwright['page'].evaluate.assert_called_once_with("return document.title")

    def test_evaluate_with_error(self, playwright_controller, mock_playwright):
        """Test JavaScript evaluation error handling."""
        mock_playwright['page'].evaluate.side_effect = Exception("JS Error")

        result = playwright_controller.evaluate("invalid.code")

        assert result["success"] is False
        assert "error" in result


class TestPlaywrightNativeCleanup:
    """Test cleanup and resource management."""

    def test_close_releases_resources(self, playwright_controller, mock_playwright):
        """Test that close releases all resources properly."""
        playwright_controller.start()

        playwright_controller.close()

        mock_playwright['page'].close.assert_called_once()
        mock_playwright['context'].close.assert_called_once()
        mock_playwright['browser'].close.assert_called_once()

        assert playwright_controller.page is None
        assert playwright_controller.context is None
        assert playwright_controller.browser is None
        assert playwright_controller.playwright is None

    def test_close_handles_none_values(self, playwright_controller):
        """Test close handles None values gracefully."""
        # Don't call start(), so all values are None

        # Should not raise exception
        playwright_controller.close()

        assert playwright_controller.page is None
        assert playwright_controller.context is None
        assert playwright_controller.browser is None


class TestPlaywrightNativeErrorHandling:
    """Test error handling in various methods."""

    def test_click_error_handling(self, playwright_controller, mock_playwright):
        """Test click error handling."""
        mock_playwright['page'].click.side_effect = Exception("Click failed")

        result = playwright_controller.click("#button")

        assert result["success"] is False
        assert "error" in result
        assert "Click failed" in result["error"]

    def test_type_text_error_handling(self, playwright_controller, mock_playwright):
        """Test type_text error handling."""
        mock_playwright['page'].fill.side_effect = Exception("Fill failed")

        result = playwright_controller.type_text("#input", "text")

        assert result["success"] is False
        assert "error" in result

    def test_take_screenshot_error_handling(self, playwright_controller, mock_playwright):
        """Test screenshot error handling."""
        mock_playwright['page'].screenshot.side_effect = Exception("Screenshot failed")

        result = playwright_controller.take_screenshot()

        assert result["success"] is False
        assert "error" in result

    def test_get_content_error_handling(self, playwright_controller, mock_playwright):
        """Test get_content error handling."""
        mock_playwright['page'].content.side_effect = Exception("Content failed")

        result = playwright_controller.get_content()

        assert result["success"] is False
        assert "error" in result

    def test_get_text_error_handling(self, playwright_controller, mock_playwright):
        """Test get_text error handling."""
        mock_locator = MagicMock()
        mock_locator.text_content.side_effect = Exception("Text failed")
        mock_playwright['page'].locator.return_value = mock_locator

        result = playwright_controller.get_text(".element")

        assert result["success"] is False
        assert "error" in result

    def test_fill_form_error_handling(self, playwright_controller, mock_playwright):
        """Test fill_form error handling."""
        mock_playwright['page'].fill.side_effect = Exception("Form fill failed")
        fields = [{"selector": "#input", "value": "test", "type": "text"}]

        result = playwright_controller.fill_form(fields)

        assert result["success"] is False
        assert "error" in result

    def test_wait_for_selector_error_handling(self, playwright_controller, mock_playwright):
        """Test wait_for_selector error handling."""
        mock_playwright['page'].wait_for_selector.side_effect = Exception("Timeout")

        result = playwright_controller.wait_for_selector(".element")

        assert result["success"] is False
        assert "error" in result

    def test_get_attribute_error_handling(self, playwright_controller, mock_playwright):
        """Test get_attribute error handling."""
        mock_locator = MagicMock()
        mock_locator.get_attribute.side_effect = Exception("Attribute failed")
        mock_playwright['page'].locator.return_value = mock_locator

        result = playwright_controller.get_attribute(".element", "href")

        assert result["success"] is False
        assert "error" in result

    def test_hover_error_handling(self, playwright_controller, mock_playwright):
        """Test hover error handling."""
        mock_playwright['page'].hover.side_effect = Exception("Hover failed")

        result = playwright_controller.hover(".element")

        assert result["success"] is False
        assert "error" in result

    def test_go_back_error_handling(self, playwright_controller, mock_playwright):
        """Test go_back error handling."""
        mock_playwright['page'].go_back.side_effect = Exception("Go back failed")

        result = playwright_controller.go_back()

        assert result["success"] is False
        assert "error" in result

    def test_reload_error_handling(self, playwright_controller, mock_playwright):
        """Test reload error handling."""
        mock_playwright['page'].reload.side_effect = Exception("Reload failed")

        result = playwright_controller.reload()

        assert result["success"] is False
        assert "error" in result


class TestPlaywrightNativeCLI:
    """Test CLI interface."""

    @patch('sys.argv', ['playwright_controller.py', 'navigate', 'https://example.com'])
    @patch('playwright_controller.PlaywrightNative')
    @patch('builtins.print')
    def test_cli_navigate(self, mock_print, mock_controller_class):
        """Test CLI navigation command."""
        from playwright_controller import main

        mock_controller = MagicMock()
        mock_controller.__enter__ = Mock(return_value=mock_controller)
        mock_controller.__exit__ = Mock(return_value=False)
        mock_controller.navigate.return_value = {"success": True, "url": "https://example.com"}
        mock_controller_class.return_value = mock_controller

        main()

        mock_controller.navigate.assert_called_once_with('https://example.com')

    @patch('sys.argv', ['playwright_controller.py'])
    @patch('builtins.print')
    def test_cli_no_command(self, mock_print):
        """Test CLI with no command shows usage."""
        from playwright_controller import main

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        assert mock_print.called

    @patch('sys.argv', ['playwright_controller.py', 'screenshot'])
    @patch('playwright_controller.PlaywrightNative')
    @patch('builtins.print')
    def test_cli_screenshot(self, mock_print, mock_controller_class):
        """Test CLI screenshot command."""
        from playwright_controller import main

        mock_controller = MagicMock()
        mock_controller.__enter__ = Mock(return_value=mock_controller)
        mock_controller.__exit__ = Mock(return_value=False)
        mock_controller.take_screenshot.return_value = {"success": True, "filename": "test.png"}
        mock_controller_class.return_value = mock_controller

        main()

        mock_controller.take_screenshot.assert_called_once()

    @patch('sys.argv', ['playwright_controller.py', 'screenshot', '--full-page', '--filename', 'test.png', '--selector', '.element'])
    @patch('playwright_controller.PlaywrightNative')
    @patch('builtins.print')
    def test_cli_screenshot_with_options(self, mock_print, mock_controller_class):
        """Test CLI screenshot with all options."""
        from playwright_controller import main

        mock_controller = MagicMock()
        mock_controller.__enter__ = Mock(return_value=mock_controller)
        mock_controller.__exit__ = Mock(return_value=False)
        mock_controller.take_screenshot.return_value = {"success": True, "filename": "test.png"}
        mock_controller_class.return_value = mock_controller

        main()

        mock_controller.take_screenshot.assert_called_once_with(
            filename='test.png', full_page=True, selector='.element'
        )

    @patch('sys.argv', ['playwright_controller.py', 'click', '#button'])
    @patch('playwright_controller.PlaywrightNative')
    @patch('builtins.print')
    def test_cli_click(self, mock_print, mock_controller_class):
        """Test CLI click command."""
        from playwright_controller import main

        mock_controller = MagicMock()
        mock_controller.__enter__ = Mock(return_value=mock_controller)
        mock_controller.__exit__ = Mock(return_value=False)
        mock_controller.click.return_value = {"success": True}
        mock_controller_class.return_value = mock_controller

        main()

        mock_controller.click.assert_called_once_with('#button')

    @patch('sys.argv', ['playwright_controller.py', 'type', '#input', 'test text'])
    @patch('playwright_controller.PlaywrightNative')
    @patch('builtins.print')
    def test_cli_type(self, mock_print, mock_controller_class):
        """Test CLI type command."""
        from playwright_controller import main

        mock_controller = MagicMock()
        mock_controller.__enter__ = Mock(return_value=mock_controller)
        mock_controller.__exit__ = Mock(return_value=False)
        mock_controller.type_text.return_value = {"success": True}
        mock_controller_class.return_value = mock_controller

        main()

        mock_controller.type_text.assert_called_once_with('#input', 'test text')

    @patch('sys.argv', ['playwright_controller.py', 'content'])
    @patch('playwright_controller.PlaywrightNative')
    @patch('builtins.print')
    def test_cli_content(self, mock_print, mock_controller_class):
        """Test CLI content command."""
        from playwright_controller import main

        mock_controller = MagicMock()
        mock_controller.__enter__ = Mock(return_value=mock_controller)
        mock_controller.__exit__ = Mock(return_value=False)
        mock_controller.get_content.return_value = {"success": True, "content": "<html></html>"}
        mock_controller_class.return_value = mock_controller

        main()

        mock_controller.get_content.assert_called_once()

    @patch('sys.argv', ['playwright_controller.py', 'text', '.element'])
    @patch('playwright_controller.PlaywrightNative')
    @patch('builtins.print')
    def test_cli_text(self, mock_print, mock_controller_class):
        """Test CLI text command."""
        from playwright_controller import main

        mock_controller = MagicMock()
        mock_controller.__enter__ = Mock(return_value=mock_controller)
        mock_controller.__exit__ = Mock(return_value=False)
        mock_controller.get_text.return_value = {"success": True, "text": "Element text"}
        mock_controller_class.return_value = mock_controller

        main()

        mock_controller.get_text.assert_called_once_with('.element')

    @patch('sys.argv', ['playwright_controller.py', 'close'])
    @patch('playwright_controller.PlaywrightNative')
    @patch('builtins.print')
    def test_cli_close(self, mock_print, mock_controller_class):
        """Test CLI close command."""
        from playwright_controller import main

        mock_controller = MagicMock()
        mock_controller.__enter__ = Mock(return_value=mock_controller)
        mock_controller.__exit__ = Mock(return_value=False)
        mock_controller_class.return_value = mock_controller

        main()

        mock_controller.close.assert_called_once()

    @patch('sys.argv', ['playwright_controller.py', 'unknown_command'])
    @patch('playwright_controller.PlaywrightNative')
    @patch('builtins.print')
    def test_cli_unknown_command(self, mock_print, mock_controller_class):
        """Test CLI with unknown command."""
        from playwright_controller import main

        mock_controller = MagicMock()
        mock_controller.__enter__ = Mock(return_value=mock_controller)
        mock_controller.__exit__ = Mock(return_value=False)
        mock_controller_class.return_value = mock_controller

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        assert mock_print.called


@pytest.mark.parametrize("selector,expected", [
    ("#id", True),
    (".class", True),
    ("element", True),
    ("[data-test='value']", True),
])
class TestPlaywrightNativeSelectorTypes:
    """Test different CSS selector types."""

    def test_selector_support(self, playwright_controller, mock_playwright, selector, expected):
        """Test that various selector types are supported."""
        result = playwright_controller.click(selector)

        assert result["success"] is expected
        if expected:
            mock_playwright['page'].click.assert_called()
