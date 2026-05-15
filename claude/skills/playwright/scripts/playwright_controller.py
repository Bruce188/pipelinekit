#!/usr/bin/env python3
"""
Native Playwright Browser Automation Controller

Uses the Playwright Python library directly for browser automation.
No MCP server required - fully standalone implementation.
"""

import json
import sys
import os
from typing import Dict, Any, Optional, List
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
except ImportError:
    print("ERROR: Playwright not installed. Run: pip3 install playwright && python3 -m playwright install chromium")
    sys.exit(1)


class PlaywrightNative:
    """Native Playwright browser automation controller."""

    def __init__(self):
        """Initialize the controller."""
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def start(self):
        """Start the browser."""
        if not self.playwright:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=True)
            self.context = self.browser.new_context()
            self.page = self.context.new_page()

    def close(self):
        """Close the browser."""
        if self.page:
            self.page.close()
            self.page = None
        if self.context:
            self.context.close()
            self.context = None
        if self.browser:
            self.browser.close()
            self.browser = None
        if self.playwright:
            self.playwright.stop()
            self.playwright = None

    def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to a URL."""
        try:
            self.start()
            response = self.page.goto(url, wait_until="networkidle")
            return {
                "success": True,
                "url": self.page.url,
                "title": self.page.title(),
                "status": response.status if response else None
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def click(self, selector: str, button: str = "left",
              double_click: bool = False) -> Dict[str, Any]:
        """Click an element by selector."""
        try:
            self.start()
            if double_click:
                self.page.dblclick(selector)
            else:
                self.page.click(selector, button=button)
            return {"success": True, "selector": selector}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def type_text(self, selector: str, text: str,
                  delay: Optional[int] = None) -> Dict[str, Any]:
        """Type text into an element."""
        try:
            self.start()
            if delay:
                self.page.type(selector, text, delay=delay)
            else:
                self.page.fill(selector, text)
            return {"success": True, "selector": selector, "text": text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def take_screenshot(self, filename: Optional[str] = None,
                       full_page: bool = False,
                       selector: Optional[str] = None) -> Dict[str, Any]:
        """Take a screenshot."""
        try:
            self.start()

            # Generate filename if not provided
            if not filename:
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{timestamp}.png"

            # Ensure filename has extension
            if not filename.endswith(('.png', '.jpg', '.jpeg')):
                filename += '.png'

            # Take screenshot
            if selector:
                element = self.page.locator(selector)
                element.screenshot(path=filename)
            else:
                self.page.screenshot(path=filename, full_page=full_page)

            abs_path = os.path.abspath(filename)
            return {
                "success": True,
                "filename": abs_path,
                "full_page": full_page
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_content(self) -> Dict[str, Any]:
        """Get page content."""
        try:
            self.start()
            return {
                "success": True,
                "url": self.page.url,
                "title": self.page.title(),
                "content": self.page.content()
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_text(self, selector: str) -> Dict[str, Any]:
        """Get text content of an element."""
        try:
            self.start()
            text = self.page.locator(selector).text_content()
            return {"success": True, "selector": selector, "text": text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def fill_form(self, fields: List[Dict[str, str]]) -> Dict[str, Any]:
        """Fill multiple form fields."""
        try:
            self.start()
            results = []
            for field in fields:
                selector = field.get("selector")
                value = field.get("value")
                field_type = field.get("type", "text")

                if field_type in ["text", "email", "password"]:
                    self.page.fill(selector, value)
                elif field_type == "checkbox":
                    if value.lower() in ["true", "yes", "1"]:
                        self.page.check(selector)
                    else:
                        self.page.uncheck(selector)
                elif field_type == "select":
                    self.page.select_option(selector, value)

                results.append({"selector": selector, "value": value})

            return {"success": True, "fields": results}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def wait_for_selector(self, selector: str, timeout: int = 30000) -> Dict[str, Any]:
        """Wait for an element to appear."""
        try:
            self.start()
            self.page.wait_for_selector(selector, timeout=timeout)
            return {"success": True, "selector": selector}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def evaluate(self, expression: str) -> Dict[str, Any]:
        """Evaluate JavaScript in the page."""
        try:
            self.start()
            result = self.page.evaluate(expression)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_attribute(self, selector: str, attribute: str) -> Dict[str, Any]:
        """Get an attribute value from an element."""
        try:
            self.start()
            value = self.page.locator(selector).get_attribute(attribute)
            return {"success": True, "selector": selector, "attribute": attribute, "value": value}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def hover(self, selector: str) -> Dict[str, Any]:
        """Hover over an element."""
        try:
            self.start()
            self.page.hover(selector)
            return {"success": True, "selector": selector}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def go_back(self) -> Dict[str, Any]:
        """Navigate back."""
        try:
            self.start()
            self.page.go_back()
            return {"success": True, "url": self.page.url}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def reload(self) -> Dict[str, Any]:
        """Reload the page."""
        try:
            self.start()
            self.page.reload()
            return {"success": True, "url": self.page.url}
        except Exception as e:
            return {"success": False, "error": str(e)}


def main():
    """CLI interface for native Playwright controller."""
    if len(sys.argv) < 2:
        print("Usage: playwright_native.py <command> [args...]")
        print("\nCommands:")
        print("  navigate <url>")
        print("  screenshot [--full-page] [--filename output.png] [--selector .class]")
        print("  click <selector>")
        print("  type <selector> <text>")
        print("  content")
        print("  text <selector>")
        print("  close")
        sys.exit(1)

    command = sys.argv[1]

    with PlaywrightNative() as pw:
        if command == "navigate" and len(sys.argv) > 2:
            result = pw.navigate(sys.argv[2])

        elif command == "screenshot":
            full_page = "--full-page" in sys.argv
            filename = None
            selector = None

            if "--filename" in sys.argv:
                idx = sys.argv.index("--filename")
                if idx + 1 < len(sys.argv):
                    filename = sys.argv[idx + 1]

            if "--selector" in sys.argv:
                idx = sys.argv.index("--selector")
                if idx + 1 < len(sys.argv):
                    selector = sys.argv[idx + 1]

            result = pw.take_screenshot(filename=filename, full_page=full_page, selector=selector)

        elif command == "click" and len(sys.argv) > 2:
            result = pw.click(sys.argv[2])

        elif command == "type" and len(sys.argv) > 3:
            result = pw.type_text(sys.argv[2], sys.argv[3])

        elif command == "content":
            result = pw.get_content()

        elif command == "text" and len(sys.argv) > 2:
            result = pw.get_text(sys.argv[2])

        elif command == "close":
            pw.close()
            result = {"success": True, "message": "Browser closed"}

        else:
            print(f"Unknown command: {command}")
            sys.exit(1)

        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
