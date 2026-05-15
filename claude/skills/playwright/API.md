# API Reference

Complete API reference for the Playwright Browser Automation Skill.

## Table of Contents

- [PlaywrightNative Class](#playwrightnative-class)
- [Navigation Methods](#navigation-methods)
- [Element Interaction](#element-interaction)
- [Screenshots](#screenshots)
- [Form Automation](#form-automation)
- [Content Extraction](#content-extraction)
- [JavaScript Evaluation](#javascript-evaluation)
- [Wait Operations](#wait-operations)
- [Resource Management](#resource-management)
- [CLI Interface](#cli-interface)
- [Response Format](#response-format)
- [Error Handling](#error-handling)

## PlaywrightNative Class

Main controller class for browser automation.

```python
class PlaywrightNative:
    """Native Playwright browser automation controller."""
```

### Constructor

```python
def __init__(self):
    """Initialize the controller."""
```

**Parameters**: None

**Returns**: PlaywrightNative instance

**Example**:
```python
from playwright_controller import PlaywrightNative

pw = PlaywrightNative()
```

### Context Manager Support

The class supports the context manager protocol for automatic resource cleanup.

```python
with PlaywrightNative() as pw:
    # Browser automatically started
    pw.navigate("https://example.com")
    # Browser automatically closed on exit
```

**Methods**:
- `__enter__()`: Starts the browser, returns self
- `__exit__(exc_type, exc_val, exc_tb)`: Closes the browser

## Navigation Methods

### navigate()

Navigate to a URL and wait for the page to load.

```python
def navigate(self, url: str) -> Dict[str, Any]:
    """Navigate to a URL."""
```

**Parameters**:
- `url` (str, required): Full URL to navigate to (must include protocol)

**Returns**: Dictionary with:
- `success` (bool): True if navigation succeeded
- `url` (str): Final URL after navigation (may differ due to redirects)
- `title` (str): Page title
- `status` (int): HTTP status code

**Example**:
```python
result = pw.navigate("https://example.com")
# {
#   "success": True,
#   "url": "https://example.com/",
#   "title": "Example Domain",
#   "status": 200
# }
```

**Notes**:
- Waits for network idle before returning
- Follows redirects automatically
- Returns final URL after redirects

---

### go_back()

Navigate back in browser history.

```python
def go_back(self) -> Dict[str, Any]:
    """Navigate back."""
```

**Parameters**: None

**Returns**: Dictionary with:
- `success` (bool): True if navigation succeeded
- `url` (str): Current URL after going back

**Example**:
```python
result = pw.go_back()
# {"success": True, "url": "https://previous-page.com"}
```

**Notes**:
- No-op if already at the first page in history

---

### reload()

Reload the current page.

```python
def reload(self) -> Dict[str, Any]:
    """Reload the page."""
```

**Parameters**: None

**Returns**: Dictionary with:
- `success` (bool): True if reload succeeded
- `url` (str): Current URL

**Example**:
```python
result = pw.reload()
# {"success": True, "url": "https://example.com"}
```

**Notes**:
- Performs a hard reload (ignores cache)
- Waits for page to load completely

## Element Interaction

### click()

Click an element using a CSS selector.

```python
def click(self, selector: str, button: str = "left",
          double_click: bool = False) -> Dict[str, Any]:
    """Click an element by selector."""
```

**Parameters**:
- `selector` (str, required): CSS selector for element
- `button` (str, optional): Mouse button - "left", "right", or "middle" (default: "left")
- `double_click` (bool, optional): Perform double-click (default: False)

**Returns**: Dictionary with:
- `success` (bool): True if click succeeded
- `selector` (str): Selector that was clicked

**Example**:
```python
# Single left-click
result = pw.click("#submit-button")

# Right-click
result = pw.click(".context-menu", button="right")

# Double-click
result = pw.click(".file-item", double_click=True)
```

**Notes**:
- Waits for element to be visible and clickable
- Scrolls element into view if needed
- Fails if element is not found or not clickable

---

### type_text()

Type text into an input element.

```python
def type_text(self, selector: str, text: str,
              delay: Optional[int] = None) -> Dict[str, Any]:
    """Type text into an element."""
```

**Parameters**:
- `selector` (str, required): CSS selector for input element
- `text` (str, required): Text to type
- `delay` (int, optional): Delay in milliseconds between keypresses

**Returns**: Dictionary with:
- `success` (bool): True if typing succeeded
- `selector` (str): Selector of input element
- `text` (str): Text that was typed

**Example**:
```python
# Fast fill (no delay)
result = pw.type_text("#username", "user@example.com")

# Slow typing (100ms between keys)
result = pw.type_text("#search", "search query", delay=100)
```

**Notes**:
- Without delay: Uses fast fill (replaces content)
- With delay: Simulates human typing
- Clears existing content before typing

---

### hover()

Hover the mouse over an element.

```python
def hover(self, selector: str) -> Dict[str, Any]:
    """Hover over an element."""
```

**Parameters**:
- `selector` (str, required): CSS selector for element

**Returns**: Dictionary with:
- `success` (bool): True if hover succeeded
- `selector` (str): Selector that was hovered

**Example**:
```python
result = pw.hover(".dropdown-menu")
```

**Notes**:
- Useful for triggering hover-based dropdowns
- Scrolls element into view if needed

## Screenshots

### take_screenshot()

Capture a screenshot of the page or element.

```python
def take_screenshot(self, filename: Optional[str] = None,
                   full_page: bool = False,
                   selector: Optional[str] = None) -> Dict[str, Any]:
    """Take a screenshot."""
```

**Parameters**:
- `filename` (str, optional): Output filename (auto-generated if not provided)
- `full_page` (bool, optional): Capture full scrollable page (default: False)
- `selector` (str, optional): Capture specific element only

**Returns**: Dictionary with:
- `success` (bool): True if screenshot succeeded
- `filename` (str): Absolute path to screenshot file
- `full_page` (bool): Whether full page was captured

**Example**:
```python
# Auto-generated filename (screenshot_20240101_120000.png)
result = pw.take_screenshot()

# Custom filename
result = pw.take_screenshot(filename="dashboard.png")

# Full page screenshot
result = pw.take_screenshot(filename="page.png", full_page=True)

# Element screenshot
result = pw.take_screenshot(filename="header.png", selector=".header")
```

**Notes**:
- Default format: PNG
- Supported formats: PNG, JPG, JPEG (based on extension)
- Auto-adds `.png` extension if no extension provided
- Full page screenshots may take longer for long pages
- Element screenshots crop to element bounds

## Form Automation

### fill_form()

Fill multiple form fields at once.

```python
def fill_form(self, fields: List[Dict[str, str]]) -> Dict[str, Any]:
    """Fill multiple form fields."""
```

**Parameters**:
- `fields` (list, required): List of field dictionaries, each containing:
  - `selector` (str, required): CSS selector for field
  - `value` (str, required): Value to fill/select/check
  - `type` (str, optional): Field type (default: "text")

**Field Types**:
- `"text"`, `"email"`, `"password"`: Text input fields
- `"checkbox"`: Checkbox (value: "true"/"yes"/"1" to check)
- `"select"`: Dropdown select (value: option value)

**Returns**: Dictionary with:
- `success` (bool): True if all fields filled successfully
- `fields` (list): List of filled field information

**Example**:
```python
result = pw.fill_form([
    {"selector": "#username", "value": "user@example.com", "type": "email"},
    {"selector": "#password", "value": "secret123", "type": "password"},
    {"selector": "#country", "value": "us", "type": "select"},
    {"selector": "#agree", "value": "true", "type": "checkbox"}
])
```

**Notes**:
- Processes fields in order
- Stops on first error
- Use `type_text()` for single fields
- Checkboxes accept: "true", "yes", "1" (case-insensitive)

## Content Extraction

### get_content()

Get the complete HTML content of the page.

```python
def get_content(self) -> Dict[str, Any]:
    """Get page content."""
```

**Parameters**: None

**Returns**: Dictionary with:
- `success` (bool): True if content retrieved
- `url` (str): Current page URL
- `title` (str): Page title
- `content` (str): Full HTML content

**Example**:
```python
result = pw.get_content()
# {
#   "success": True,
#   "url": "https://example.com",
#   "title": "Example Domain",
#   "content": "<!DOCTYPE html><html>..."
# }
```

**Notes**:
- Returns rendered HTML (after JavaScript execution)
- Includes dynamically generated content

---

### get_text()

Get the text content of an element.

```python
def get_text(self, selector: str) -> Dict[str, Any]:
    """Get text content of an element."""
```

**Parameters**:
- `selector` (str, required): CSS selector for element

**Returns**: Dictionary with:
- `success` (bool): True if text retrieved
- `selector` (str): Selector used
- `text` (str): Text content (or None if empty)

**Example**:
```python
result = pw.get_text("h1")
# {"success": True, "selector": "h1", "text": "Welcome"}
```

**Notes**:
- Returns visible text only
- Strips whitespace
- Returns None for elements with no text

---

### get_attribute()

Get an attribute value from an element.

```python
def get_attribute(self, selector: str, attribute: str) -> Dict[str, Any]:
    """Get an attribute value from an element."""
```

**Parameters**:
- `selector` (str, required): CSS selector for element
- `attribute` (str, required): Attribute name (e.g., "href", "class", "data-id")

**Returns**: Dictionary with:
- `success` (bool): True if attribute retrieved
- `selector` (str): Selector used
- `attribute` (str): Attribute name
- `value` (str): Attribute value (or None if not present)

**Example**:
```python
# Get link URL
result = pw.get_attribute("a.main-link", "href")
# {"success": True, "selector": "a.main-link", "attribute": "href", "value": "https://..."}

# Get data attribute
result = pw.get_attribute(".item", "data-id")
```

**Notes**:
- Returns None if attribute doesn't exist
- Works with all HTML attributes
- Works with data attributes

## JavaScript Evaluation

### evaluate()

Execute JavaScript code in the page context.

```python
def evaluate(self, expression: str) -> Dict[str, Any]:
    """Evaluate JavaScript in the page."""
```

**Parameters**:
- `expression` (str, required): JavaScript code to execute

**Returns**: Dictionary with:
- `success` (bool): True if evaluation succeeded
- `result` (any): Return value from JavaScript (JSON-serializable)

**Example**:
```python
# Simple expression
result = pw.evaluate("document.title")
# {"success": True, "result": "Example Domain"}

# Count elements
result = pw.evaluate("document.querySelectorAll('a').length")
# {"success": True, "result": 42}

# Complex object
result = pw.evaluate("""
    ({
        title: document.title,
        links: document.querySelectorAll('a').length,
        url: window.location.href
    })
""")
# {"success": True, "result": {"title": "...", "links": 42, "url": "..."}}
```

**Notes**:
- Code runs in page context (has access to window, document, etc.)
- Return value must be JSON-serializable
- Can return objects, arrays, primitives
- Cannot return DOM nodes directly (serialize to objects first)

## Wait Operations

### wait_for_selector()

Wait for an element to appear in the DOM.

```python
def wait_for_selector(self, selector: str, timeout: int = 30000) -> Dict[str, Any]:
    """Wait for an element to appear."""
```

**Parameters**:
- `selector` (str, required): CSS selector to wait for
- `timeout` (int, optional): Timeout in milliseconds (default: 30000)

**Returns**: Dictionary with:
- `success` (bool): True if element appeared
- `selector` (str): Selector that was waited for

**Example**:
```python
# Wait with default timeout (30 seconds)
result = pw.wait_for_selector(".loading-complete")

# Wait with custom timeout (5 seconds)
result = pw.wait_for_selector("#modal", timeout=5000)
```

**Notes**:
- Waits for element to be attached to DOM
- Does not wait for visibility (use CSS selector for visible elements)
- Throws timeout error if element doesn't appear
- Use before interacting with dynamically loaded elements

## Resource Management

### start()

Manually start the browser.

```python
def start(self):
    """Start the browser."""
```

**Parameters**: None

**Returns**: None

**Notes**:
- Called automatically by navigation/interaction methods
- Safe to call multiple times (idempotent)
- Context manager calls this automatically

---

### close()

Close the browser and free resources.

```python
def close(self):
    """Close the browser."""
```

**Parameters**: None

**Returns**: None

**Example**:
```python
pw = PlaywrightNative()
try:
    pw.navigate("https://example.com")
finally:
    pw.close()  # Always clean up
```

**Notes**:
- Closes page, context, browser, and playwright
- Safe to call multiple times
- Context manager calls this automatically
- Always call when not using context manager

## CLI Interface

### Command Line Usage

```bash
python3 playwright_controller.py <command> [args...]
```

### Commands

#### navigate
```bash
python3 playwright_controller.py navigate <url>
```

**Example**:
```bash
python3 playwright_controller.py navigate https://example.com
```

---

#### screenshot
```bash
python3 playwright_controller.py screenshot [--full-page] [--filename PATH] [--selector SELECTOR]
```

**Options**:
- `--full-page`: Capture full scrollable page
- `--filename PATH`: Output filename
- `--selector SELECTOR`: Capture specific element

**Examples**:
```bash
# Viewport screenshot
python3 playwright_controller.py screenshot

# Full page
python3 playwright_controller.py screenshot --full-page --filename page.png

# Element screenshot
python3 playwright_controller.py screenshot --selector ".header" --filename header.png
```

---

#### click
```bash
python3 playwright_controller.py click <selector>
```

**Example**:
```bash
python3 playwright_controller.py click "#submit-button"
```

---

#### type
```bash
python3 playwright_controller.py type <selector> <text>
```

**Example**:
```bash
python3 playwright_controller.py type "#search" "search query"
```

---

#### content
```bash
python3 playwright_controller.py content
```

**Example**:
```bash
python3 playwright_controller.py content > page.html
```

---

#### text
```bash
python3 playwright_controller.py text <selector>
```

**Example**:
```bash
python3 playwright_controller.py text "h1"
```

---

#### close
```bash
python3 playwright_controller.py close
```

## Response Format

### Success Response

All methods return a dictionary with at minimum:

```json
{
  "success": true,
  // ... additional method-specific fields
}
```

### Error Response

On error, methods return:

```json
{
  "success": false,
  "error": "Error message describing what went wrong"
}
```

### Common Response Patterns

**Navigation**:
```json
{"success": true, "url": "...", "title": "...", "status": 200}
```

**Element Interaction**:
```json
{"success": true, "selector": "..."}
```

**Content Extraction**:
```json
{"success": true, "selector": "...", "text": "...", "value": "..."}
```

## Error Handling

### Exception Handling

All public methods catch exceptions and return error responses:

```python
try:
    result = pw.navigate("https://example.com")
    if not result["success"]:
        print(f"Error: {result['error']}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

### Common Errors

**Element not found**:
```json
{"success": false, "error": "Element not found: #missing-element"}
```

**Navigation timeout**:
```json
{"success": false, "error": "Navigation timeout exceeded"}
```

**JavaScript error**:
```json
{"success": false, "error": "ReferenceError: variable is not defined"}
```

### Best Practices

1. **Always check success field**:
   ```python
   result = pw.navigate(url)
   if result["success"]:
       print(f"Navigated to {result['url']}")
   else:
       print(f"Failed: {result['error']}")
   ```

2. **Use context manager**:
   ```python
   with PlaywrightNative() as pw:
       # Automatic cleanup
   ```

3. **Wait before interacting**:
   ```python
   pw.wait_for_selector("#element")
   pw.click("#element")
   ```

4. **Handle specific errors**:
   ```python
   if "timeout" in result.get("error", "").lower():
       # Handle timeout specifically
   ```

## Type Hints

The module uses Python type hints for better IDE support:

```python
from typing import Dict, Any, Optional, List

def navigate(self, url: str) -> Dict[str, Any]: ...
def click(self, selector: str, button: str = "left",
          double_click: bool = False) -> Dict[str, Any]: ...
def fill_form(self, fields: List[Dict[str, str]]) -> Dict[str, Any]: ...
```

## Version Compatibility

- **Python**: 3.8+
- **Playwright**: 1.40.0+
- **Browser**: Chromium (latest)

## See Also

- [README.md](~/.claude/skills/playwright/README.md) - Main documentation
- [TESTING.md](~/.claude/skills/playwright/TESTING.md) - Testing guide
- [Playwright Python Docs](https://playwright.dev/python/) - Official documentation
