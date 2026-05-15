---
name: playwright
description: Native Python browser automation using Playwright for navigation, interaction, screenshots, and form filling
---

# Playwright Browser Automation

Native Python implementation for browser automation, testing, and web scraping using Playwright. No MCP server required - fully standalone with 98% test coverage.

## Keywords

browser automation, web testing, playwright, screenshots, form filling, web scraping, browser navigation, click elements, take screenshot, fill form, browser testing, e2e testing, web automation, headless browser, page interaction, selenium alternative, puppeteer alternative, browser control, web driver

## Capabilities

### Navigation
- Navigate to URLs with network idle detection
- Go back/forward in browser history
- Reload current page
- Full URL support with status code reporting

### Element Interaction
- Click elements (left, right, middle button)
- Double-click support
- Hover over elements
- Type text with optional delay
- CSS selector support (#id, .class, [attribute])

### Form Automation
- Fill text inputs, email fields, password fields
- Check/uncheck checkboxes
- Select dropdown options
- Batch form filling with multiple fields
- Support for all standard HTML form elements

### Screenshots
- Full page screenshots (including scrollable content)
- Viewport screenshots
- Element-specific screenshots
- Automatic filename generation with timestamps
- PNG/JPEG format support

### Content Extraction
- Get complete page HTML
- Extract element text content
- Get element attributes
- Get page title and URL

### Advanced Features
- JavaScript evaluation in page context
- Wait for selectors with custom timeouts
- Context manager for automatic resource cleanup
- CLI interface for command-line usage
- Headless Chromium automation

## Input Requirements

### Navigation
- `url`: Full URL to navigate to (required, e.g., "https://example.com")

### Element Interaction
- `selector`: CSS selector string (required, e.g., "#id", ".class", "button[type='submit']")
- `text`: Text to type (for typing operations)
- `button`: Mouse button (optional, default: "left", options: "right", "middle")
- `double_click`: Boolean for double-click (optional, default: false)

### Screenshots
- `filename`: Output filename (optional, auto-generated if not provided)
- `full_page`: Capture entire scrollable page (optional, default: false)
- `selector`: Element to screenshot (optional, captures element only)

### Form Filling
- `fields`: Array of field objects with:
  - `selector`: CSS selector for field
  - `value`: Value to fill/select/check
  - `type`: Field type ("text", "email", "password", "checkbox", "select")

### Wait Operations
- `selector`: CSS selector to wait for
- `timeout`: Timeout in milliseconds (optional, default: 30000)

### JavaScript Evaluation
- `expression`: JavaScript code to execute (string)

## Output Formats

### Standard Response
All methods return a dictionary with:
```json
{
  "success": true,
  "...": "method-specific data"
}
```

Or on error:
```json
{
  "success": false,
  "error": "error message"
}
```

### Navigation Response
```json
{
  "success": true,
  "url": "https://example.com/",
  "title": "Example Domain",
  "status": 200
}
```

### Screenshot Response
```json
{
  "success": true,
  "filename": "/absolute/path/to/screenshot.png",
  "full_page": true
}
```

### Content Response
```json
{
  "success": true,
  "url": "https://example.com",
  "title": "Page Title",
  "content": "<html>...</html>"
}
```

### Text Extraction Response
```json
{
  "success": true,
  "selector": "h1",
  "text": "Heading Text"
}
```

## How to Use

### Basic Navigation
```
"Navigate to https://example.com"
"Go to the login page at https://app.example.com/login"
"Go back to the previous page"
"Reload the current page"
```

### Taking Screenshots
```
"Take a screenshot of the current page"
"Screenshot the full page including scrollable content"
"Capture a screenshot of the header element"
"Save a screenshot as dashboard.png"
```

### Form Automation
```
"Fill in the login form with username 'test@example.com' and password 'secret'"
"Select 'United States' from the country dropdown"
"Check the 'agree to terms' checkbox"
"Fill the email field with 'user@example.com'"
```

### Element Interaction
```
"Click the 'Submit' button"
"Hover over the menu icon"
"Type 'search query' into the search box"
"Double-click the file in the list"
"Right-click the context menu"
```

### Content Extraction
```
"Get the page HTML content"
"Extract the text from the main heading"
"Get the href attribute from the first link"
"Show me the page title"
```

### Advanced Operations
```
"Wait for the loading spinner to disappear"
"Evaluate JavaScript to count all links on the page"
"Get all form fields using JavaScript"
"Wait 5 seconds for the modal to appear"
```

## Implementation Details

### Single Script
- `playwright_controller.py`: Complete implementation with all browser operations

### Key Classes
- `PlaywrightNative`: Main controller class with context manager support

### Available Methods
1. `navigate(url)` - Navigate to URL
2. `click(selector, button, double_click)` - Click element
3. `type_text(selector, text, delay)` - Type into element
4. `take_screenshot(filename, full_page, selector)` - Capture screenshot
5. `get_content()` - Get page HTML
6. `get_text(selector)` - Get element text
7. `get_attribute(selector, attribute)` - Get element attribute
8. `fill_form(fields)` - Fill multiple form fields
9. `wait_for_selector(selector, timeout)` - Wait for element
10. `evaluate(expression)` - Run JavaScript
11. `hover(selector)` - Hover over element
12. `go_back()` - Navigate back
13. `reload()` - Reload page
14. `close()` - Close browser

### CLI Usage
```bash
# Navigate
python3 scripts/playwright_controller.py navigate https://example.com

# Screenshot
python3 scripts/playwright_controller.py screenshot --full-page --filename output.png

# Click element
python3 scripts/playwright_controller.py click "#button"

# Type text
python3 scripts/playwright_controller.py type "#input" "text"

# Get content
python3 scripts/playwright_controller.py content

# Get element text
python3 scripts/playwright_controller.py text ".heading"
```

## Best Practices

### Element Selection
- Use specific selectors (ID preferred): `#submit-button` over `button`
- Wait for elements before interaction
- Verify element existence with `wait_for_selector()` first

### Screenshots
- Use descriptive filenames with context
- Use `full_page=True` for complete documentation
- Wait for content to load before capturing
- Use element screenshots for specific components

### Form Filling
- Batch form fields together with `fill_form()`
- Use appropriate field types for proper handling
- Wait for form to be visible before filling

### Error Handling
- All methods return `{"success": false, "error": "..."}` on failure
- Always check the `success` field before using results
- Use try-except when calling from Python code

### Resource Management
- Use context manager (`with PlaywrightNative() as pw:`) for automatic cleanup
- Call `close()` explicitly if not using context manager
- Browser instances persist across operations

### Performance
- Navigation waits for network idle by default
- Use custom timeouts for slow-loading pages
- Avoid unnecessary full page screenshots (larger file size)

## Limitations

### Technical Limitations
- **Browser Required**: Chromium must be installed (~200MB disk space)
- **Headless Only**: No visible browser window
- **Single Page**: One page per controller instance
- **Memory Usage**: Browser processes consume significant RAM
- **Performance**: Browser automation slower than direct API calls

### Content Limitations
- **JavaScript Required**: Cannot render server-side only content
- **Dynamic Content**: Requires proper waiting strategies
- **CAPTCHA**: Cannot bypass CAPTCHA or anti-bot protection
- **Complex Auth**: OAuth flows may require manual intervention
- **Anti-Bot Detection**: Some sites block headless browsers

### Feature Limitations
- **File Downloads**: Not currently implemented
- **Multiple Tabs**: Single tab support only
- **Network Monitoring**: Not available (console/network features not implemented)
- **Drag and Drop**: Not currently implemented
- **File Uploads**: Not currently implemented

## When to Use This Skill

### Ideal Use Cases
- Testing web applications end-to-end
- Automating repetitive browser tasks
- Taking screenshots for documentation
- Filling and submitting web forms
- Extracting content from JavaScript-heavy sites
- Debugging frontend rendering issues
- Monitoring web application behavior
- Scraping data requiring browser rendering

### Recommended Scenarios
- Sites requiring JavaScript execution
- Modern SPAs (React, Vue, Angular)
- Pages with dynamic content loading
- Form submission workflows
- Login automation
- Multi-step user flows

## When NOT to Use This Skill

### Use Alternatives Instead
- **Simple API calls**: Use fetch/curl/requests
- **Static HTML content**: Use web-fetch skill
- **High-volume scraping**: Too slow for large-scale operations
- **PDF generation**: Use dedicated PDF tools
- **Mobile app testing**: Requires Appium or similar
- **Performance testing**: Use k6, JMeter, or similar
- **Server-side rendering**: Use simple HTTP requests

### Not Suitable For
- Real-time data streaming
- Video/audio processing
- Binary file manipulation
- Database operations
- Network protocol testing (non-HTTP)

## Example Workflows

### Login and Screenshot
```
1. Navigate to login page
2. Fill username field
3. Fill password field
4. Click submit button
5. Wait for dashboard to load
6. Take screenshot of logged-in state
```

### Form Submission Test
```
1. Navigate to form page
2. Fill all required fields
3. Check terms checkbox
4. Select country from dropdown
5. Click submit
6. Verify success message appears
```

### Content Extraction
```
1. Navigate to target page
2. Wait for dynamic content to load
3. Extract specific elements
4. Get text content
5. Save to file or return data
```

### Multi-Step Workflow
```
1. Navigate to start page
2. Click through navigation
3. Fill intermediate forms
4. Submit final form
5. Verify completion
6. Take evidence screenshots
```

## Testing

### Test Coverage
- **57 unit tests**: All functionality with mocked browser
- **5 integration tests**: Real browser operations
- **98% code coverage**: Comprehensive test suite
- **Pytest framework**: Industry-standard testing

### Running Tests
```bash
# All tests
python3 -m pytest

# Unit tests only (fast, no browser)
python3 -m pytest -m "not integration"

# Integration tests (requires Playwright)
python3 -m pytest -m integration

# With coverage
python3 -m pytest --cov=scripts --cov-report=html
```

## Installation Requirements

### Required
- Python 3.8 or higher
- playwright Python package
- Chromium browser (via playwright install)

### Optional (for testing)
- pytest (testing framework)
- pytest-cov (coverage reporting)
- pytest-mock (mocking utilities)

### Installation
```bash
pip3 install playwright
python3 -m playwright install chromium
```

## Notes

- Browser runs in headless mode (no visible window)
- Screenshots saved to current working directory by default
- Browser instance persists across operations in same session
- Context manager recommended for automatic cleanup
- All selectors use CSS syntax
- Default timeout: 30 seconds for wait operations
- Navigation waits for network idle automatically
- Supports Chromium browser only (not Firefox or WebKit)

## Version

**1.0.0** - Initial release
- Complete Playwright Python implementation
- 57 unit tests, 5 integration tests
- 98% code coverage
- CLI interface
- Context manager support
- All core browser automation features
