# Playwright Browser Automation Skill

Native Python browser automation skill for Claude Code that provides comprehensive browser automation capabilities without requiring an MCP server.

## Overview

This skill provides a lightweight, standalone implementation of browser automation using the Playwright Python library directly. It's designed to be a drop-in replacement for the playwright MCP server with significantly reduced token overhead and simpler installation.

**Key Features:**
- Native Python implementation using `playwright.sync_api`
- Comprehensive test suite with 57 unit tests and 5 integration tests
- 98% code coverage
- CLI interface for command-line usage
- Context manager support for automatic resource management
- Full browser automation capabilities

## Installation

### Prerequisites

Ensure you have Python 3.8+ installed.

### Quick Install

```bash
# 1. Copy skill to your Claude skills directory
cp -r /path/to/playwright ~/.claude/skills/

# 2. Install Playwright Python library
pip3 install playwright

# 3. Install Chromium browser
python3 -m playwright install chromium
```

### System-Wide Installation (Alternative)

If you encounter permission issues, use the `--break-system-packages` flag:

```bash
pip3 install --break-system-packages playwright
python3 -m playwright install chromium
```

### Verify Installation

```bash
# Test the installation
python3 ~/.claude/skills/playwright/scripts/playwright_controller.py navigate https://example.com
```

## Features

### Core Capabilities

- **Page Navigation**: Navigate to URLs, go back/forward, reload pages
- **Element Interaction**: Click, double-click, hover, type text
- **Form Automation**: Fill text fields, check boxes, select dropdowns
- **Screenshot Capture**: Full page, viewport, or element-specific screenshots
- **Content Extraction**: Get page HTML, element text, and attributes
- **JavaScript Execution**: Evaluate custom JavaScript in page context
- **Wait Operations**: Wait for selectors with customizable timeouts
- **Browser Control**: Headless Chromium automation

### Complete Method Reference

| Method | Description | Parameters |
|--------|-------------|------------|
| `navigate(url)` | Navigate to a URL | `url`: Target URL |
| `click(selector, button, double_click)` | Click an element | `selector`: CSS selector<br>`button`: "left", "right", "middle"<br>`double_click`: boolean |
| `type_text(selector, text, delay)` | Type text into element | `selector`: CSS selector<br>`text`: Text to type<br>`delay`: Optional delay in ms |
| `take_screenshot(filename, full_page, selector)` | Capture screenshot | `filename`: Output path<br>`full_page`: boolean<br>`selector`: Optional element selector |
| `get_content()` | Get page HTML content | None |
| `get_text(selector)` | Get element text | `selector`: CSS selector |
| `get_attribute(selector, attribute)` | Get element attribute | `selector`: CSS selector<br>`attribute`: Attribute name |
| `fill_form(fields)` | Fill multiple form fields | `fields`: List of field dictionaries |
| `wait_for_selector(selector, timeout)` | Wait for element | `selector`: CSS selector<br>`timeout`: Timeout in ms (default: 30000) |
| `evaluate(expression)` | Run JavaScript | `expression`: JavaScript code |
| `hover(selector)` | Hover over element | `selector`: CSS selector |
| `go_back()` | Navigate back | None |
| `reload()` | Reload current page | None |
| `close()` | Close browser | None |

## Usage

### With Claude Code

Once installed, just ask Claude:

```
"Navigate to https://example.com and take a screenshot"
"Fill in the login form with username 'test@example.com' and password 'secret'"
"Click the submit button and wait for the page to load"
"Get the text content of the main heading"
"Take a full page screenshot of the current page"
```

Claude will automatically use the playwright skill for browser automation tasks.

### Command Line Interface

The skill can also be used directly from the command line:

```bash
# Navigate to a URL
python3 ~/.claude/skills/playwright/scripts/playwright_controller.py navigate https://example.com

# Take a screenshot
python3 ~/.claude/skills/playwright/scripts/playwright_controller.py screenshot --full-page --filename output.png

# Take element screenshot
python3 ~/.claude/skills/playwright/scripts/playwright_controller.py screenshot --selector ".header" --filename header.png

# Get page content
python3 ~/.claude/skills/playwright/scripts/playwright_controller.py content

# Click an element
python3 ~/.claude/skills/playwright/scripts/playwright_controller.py click "#submit-button"

# Type text
python3 ~/.claude/skills/playwright/scripts/playwright_controller.py type "#search-box" "search query"

# Get element text
python3 ~/.claude/skills/playwright/scripts/playwright_controller.py text ".heading"

# Close browser
python3 ~/.claude/skills/playwright/scripts/playwright_controller.py close
```

### Python API

Use as a context manager for automatic resource cleanup:

```python
from playwright_controller import PlaywrightNative

# Context manager (recommended)
with PlaywrightNative() as pw:
    # Navigate to a page
    result = pw.navigate("https://example.com")
    print(f"Navigated to: {result['url']}")

    # Take a screenshot
    screenshot = pw.take_screenshot(filename="example.png", full_page=True)
    print(f"Screenshot saved to: {screenshot['filename']}")

    # Get page content
    content = pw.get_content()
    print(f"Page title: {content['title']}")

# Manual resource management
pw = PlaywrightNative()
try:
    result = pw.navigate("https://example.com")
    # ... perform operations
finally:
    pw.close()
```

### Common Workflows

#### Login and Screenshot

```python
with PlaywrightNative() as pw:
    # Navigate to login page
    pw.navigate("https://app.example.com/login")

    # Fill login form
    pw.fill_form([
        {"selector": "#username", "value": "user@example.com", "type": "email"},
        {"selector": "#password", "value": "secret123", "type": "password"}
    ])

    # Click submit
    pw.click("#login-button")

    # Wait for dashboard
    pw.wait_for_selector(".dashboard")

    # Take screenshot
    pw.take_screenshot(filename="dashboard.png", full_page=True)
```

#### Form Automation

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com/contact")

    # Fill contact form
    pw.fill_form([
        {"selector": "#name", "value": "John Doe", "type": "text"},
        {"selector": "#email", "value": "john@example.com", "type": "email"},
        {"selector": "#country", "value": "us", "type": "select"},
        {"selector": "#agree", "value": "true", "type": "checkbox"}
    ])

    # Submit form
    pw.click("button[type='submit']")

    # Check for success message
    success = pw.get_text(".success-message")
    print(success['text'])
```

#### Content Extraction

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com")

    # Get page title
    content = pw.get_content()
    print(f"Title: {content['title']}")

    # Get specific text
    heading = pw.get_text("h1")
    print(f"Heading: {heading['text']}")

    # Get attribute value
    link = pw.get_attribute("a.main-link", "href")
    print(f"Link URL: {link['value']}")
```

#### JavaScript Evaluation

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com")

    # Execute JavaScript
    result = pw.evaluate("document.querySelectorAll('a').length")
    print(f"Number of links: {result['result']}")

    # Complex JavaScript
    data = pw.evaluate("""
        ({
            title: document.title,
            links: document.querySelectorAll('a').length,
            images: document.querySelectorAll('img').length
        })
    """)
    print(f"Page data: {data['result']}")
```

## Testing

The skill includes a comprehensive test suite with 98% code coverage.

### Running Tests

```bash
# Install test dependencies
pip3 install -r requirements-test.txt

# Run all tests
python3 -m pytest

# Run only unit tests (fast, no browser required)
python3 -m pytest -m "not integration"

# Run with coverage report
python3 -m pytest --cov=scripts --cov-report=html

# Run integration tests (requires playwright installed)
python3 -m pytest -m integration
```

### Test Structure

- **Unit Tests** (57 tests): Fast, mocked tests covering all functionality
  - Initialization and lifecycle
  - Navigation operations
  - Element interaction
  - Screenshots
  - Form filling
  - Content extraction
  - Wait operations
  - JavaScript evaluation
  - Error handling
  - CLI interface

- **Integration Tests** (5 tests): Real browser tests
  - Real website navigation
  - Actual screenshot capture
  - Content extraction from live pages
  - JavaScript evaluation
  - Complete workflows

### Coverage Report

```bash
# Generate HTML coverage report
python3 -m pytest --cov=scripts --cov-report=html

# View coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

Current coverage: **98%** (202/206 lines covered)

## Comparison to playwright MCP

| Feature | playwright Skill | playwright MCP |
|---------|------------------|----------------|
| Installation | Single copy + pip install | Requires MCP server setup |
| Dependencies | Python playwright library | Node.js + MCP server |
| Token Usage | ~50 tokens until activated | ~14,000 tokens always loaded |
| Startup Time | Instant (on-demand) | Requires server connection |
| Maintenance | Standard Python package updates | Requires MCP server updates |
| Features | Native Python API | All features via MCP |
| Performance | Direct API calls | MCP protocol overhead |
| Testing | 57 unit + 5 integration tests | Depends on MCP implementation |
| Code Coverage | 98% | Varies |

**Token Savings: ~14,000 tokens (99.6% reduction)**

**Fully standalone - no MCP server required!**

## Use Cases

### When to Use This Skill

- E2E testing of web applications
- Automating repetitive browser tasks
- Taking screenshots for documentation
- Filling and submitting web forms
- Extracting content from JavaScript-heavy sites
- Debugging frontend issues
- Monitoring web application behavior
- Scraping data that requires browser rendering

### When NOT to Use This Skill

- Simple API calls (use fetch/curl instead)
- Static content extraction (use web-fetch skill)
- High-volume data scraping (too slow)
- PDF generation (use dedicated PDF tools)
- Mobile app testing (requires different tools)
- Performance/load testing (use specialized tools)

## Configuration

No configuration needed! The skill works out of the box with sensible defaults:

- **Browser**: Chromium (headless mode)
- **Wait timeout**: 30 seconds
- **Navigation**: Wait for network idle
- **Screenshot format**: PNG
- **Auto-cleanup**: Resources freed on close

## Troubleshooting

### "Playwright not found"

```bash
# Install Playwright
pip3 install playwright
python3 -m playwright install chromium
```

### "Browser launch failed"

**Cause**: Insufficient permissions or missing dependencies

**Solutions**:
```bash
# Linux: Install browser dependencies
sudo apt-get install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2

# Check disk space (Chromium requires ~200MB)
df -h

# Try system-wide installation
pip3 install --break-system-packages playwright
```

### "Element not found" or "Timeout"

**Cause**: Element doesn't exist or page hasn't loaded

**Solutions**:
```python
# Wait for element before interaction
pw.wait_for_selector("#element", timeout=10000)
pw.click("#element")

# Use longer timeout for slow pages
pw.navigate("https://slow-site.com")
pw.wait_for_selector(".content", timeout=60000)
```

### Screenshots are blank or incomplete

**Cause**: Page hasn't finished rendering

**Solutions**:
```python
# Wait for specific element
pw.navigate("https://example.com")
pw.wait_for_selector(".main-content")
pw.take_screenshot(full_page=True)

# Add small delay for dynamic content
import time
pw.navigate("https://example.com")
time.sleep(2)  # Wait for animations
pw.take_screenshot(full_page=True)
```

### Permission denied errors

```bash
# Use system packages flag
pip3 install --break-system-packages playwright

# Or use virtual environment
python3 -m venv venv
source venv/bin/activate
pip install playwright
```

## Limitations

- **Browser Operations**: Slower than direct API calls
- **Anti-Bot Protection**: Cannot bypass CAPTCHA or anti-bot systems
- **Headless Detection**: Some sites may block headless browsers
- **OAuth Flows**: Complex OAuth may need manual intervention
- **File Downloads**: Requires special configuration
- **Disk Space**: Chromium uses ~200MB
- **Memory Usage**: Browser processes consume significant RAM
- **JavaScript Required**: Cannot render pure server-side content

## Project Structure

```
playwright/
├── README.md                    # Main documentation (this file)
├── SKILL.md                     # Skill metadata for Claude Code
├── scripts/
│   └── playwright_controller.py # Main implementation
├── tests/
│   ├── conftest.py             # Pytest fixtures and configuration
│   ├── test_playwright_controller.py  # Unit tests (57 tests)
│   └── test_integration.py     # Integration tests (5 tests)
├── requirements-test.txt        # Testing dependencies
├── pytest.ini                   # Pytest configuration
└── htmlcov/                     # Coverage reports (generated)
```

## Contributing

Contributions are welcome! Please ensure:

1. All tests pass: `python3 -m pytest`
2. Coverage remains above 80%: `python3 -m pytest --cov=scripts`
3. Code follows existing style
4. New features include tests

## Version History

- **1.0.0** - Initial release with full Playwright functionality
  - 57 unit tests, 5 integration tests
  - 98% code coverage
  - Complete API implementation
  - CLI interface
  - Context manager support

## License

MIT License - See project root for details

## Support

For issues, questions, or contributions:
1. Check the troubleshooting section above
2. Review test files for usage examples
3. Consult Playwright Python documentation: https://playwright.dev/python/

## Related Skills

- **web-fetch**: For simple content fetching without JavaScript
- **archon**: For documentation and knowledge base search
- **brave-search**: For web search capabilities
