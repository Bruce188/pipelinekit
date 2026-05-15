# Usage Examples

Practical examples demonstrating common use cases for the Playwright Browser Automation Skill.

## Table of Contents

- [Basic Navigation](#basic-navigation)
- [Taking Screenshots](#taking-screenshots)
- [Form Automation](#form-automation)
- [Content Extraction](#content-extraction)
- [JavaScript Evaluation](#javascript-evaluation)
- [Wait Operations](#wait-operations)
- [Complete Workflows](#complete-workflows)
- [Error Handling](#error-handling)
- [CLI Examples](#cli-examples)

## Basic Navigation

### Simple Page Visit

```python
from playwright_controller import PlaywrightNative

with PlaywrightNative() as pw:
    result = pw.navigate("https://example.com")
    print(f"Page title: {result['title']}")
    print(f"Final URL: {result['url']}")
```

### Navigate with History

```python
with PlaywrightNative() as pw:
    # Visit first page
    pw.navigate("https://example.com")

    # Click a link (assuming link exists)
    pw.click("a[href='/about']")

    # Go back
    result = pw.go_back()
    print(f"Back at: {result['url']}")

    # Reload page
    pw.reload()
```

### Handle Redirects

```python
with PlaywrightNative() as pw:
    result = pw.navigate("https://short.url/abc")
    # result['url'] contains final URL after redirect
    print(f"Started at: https://short.url/abc")
    print(f"Ended at: {result['url']}")
```

## Taking Screenshots

### Basic Screenshot

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com")

    # Auto-generated filename: screenshot_20240101_120000.png
    result = pw.take_screenshot()
    print(f"Screenshot saved: {result['filename']}")
```

### Named Screenshot

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com")

    # Custom filename
    result = pw.take_screenshot(filename="example_homepage.png")
    print(f"Saved to: {result['filename']}")
```

### Full Page Screenshot

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com/long-page")

    # Capture entire scrollable page
    result = pw.take_screenshot(
        filename="full_page.png",
        full_page=True
    )
    print(f"Full page captured: {result['filename']}")
```

### Element Screenshot

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com")

    # Screenshot only the header
    result = pw.take_screenshot(
        filename="header.png",
        selector=".site-header"
    )
```

### Multiple Screenshots Workflow

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com")

    # Before action
    pw.take_screenshot(filename="before.png")

    # Perform action
    pw.click("#toggle-button")

    # Wait for change
    pw.wait_for_selector(".toggled-content")

    # After action
    pw.take_screenshot(filename="after.png")
```

## Form Automation

### Login Form

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com/login")

    # Fill login form
    pw.fill_form([
        {"selector": "#username", "value": "user@example.com", "type": "email"},
        {"selector": "#password", "value": "secure_password", "type": "password"}
    ])

    # Submit
    pw.click("button[type='submit']")

    # Wait for dashboard
    pw.wait_for_selector(".dashboard")
    print("Login successful!")
```

### Contact Form

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com/contact")

    # Fill multi-field form
    pw.fill_form([
        {"selector": "#name", "value": "John Doe", "type": "text"},
        {"selector": "#email", "value": "john@example.com", "type": "email"},
        {"selector": "#subject", "value": "support", "type": "select"},
        {"selector": "#message", "value": "Help needed", "type": "text"},
        {"selector": "#newsletter", "value": "true", "type": "checkbox"}
    ])

    # Submit form
    pw.click("#submit-button")

    # Check confirmation
    result = pw.get_text(".confirmation-message")
    print(f"Message: {result['text']}")
```

### Search Form

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com")

    # Type in search box
    pw.type_text("#search-input", "playwright automation")

    # Click search button
    pw.click("button[type='submit']")

    # Wait for results
    pw.wait_for_selector(".search-results")

    # Get result count
    count_text = pw.get_text(".result-count")
    print(f"Found: {count_text['text']}")
```

### Registration Form

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com/register")

    pw.fill_form([
        {"selector": "#username", "value": "newuser123", "type": "text"},
        {"selector": "#email", "value": "new@example.com", "type": "email"},
        {"selector": "#password", "value": "SecurePass123!", "type": "password"},
        {"selector": "#confirm-password", "value": "SecurePass123!", "type": "password"},
        {"selector": "#country", "value": "us", "type": "select"},
        {"selector": "#terms", "value": "yes", "type": "checkbox"},
        {"selector": "#newsletter", "value": "no", "type": "checkbox"}
    ])

    pw.click("#register-button")
```

## Content Extraction

### Get Page Title and URL

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com")

    content = pw.get_content()
    print(f"Title: {content['title']}")
    print(f"URL: {content['url']}")
```

### Extract Specific Text

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com")

    # Get heading text
    heading = pw.get_text("h1")
    print(f"Main heading: {heading['text']}")

    # Get paragraph text
    intro = pw.get_text(".intro-paragraph")
    print(f"Introduction: {intro['text']}")
```

### Extract Links

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com")

    # Get link URL
    link = pw.get_attribute("a.main-link", "href")
    print(f"Link URL: {link['value']}")

    # Get all links via JavaScript
    links = pw.evaluate("""
        Array.from(document.querySelectorAll('a'))
            .map(a => ({
                text: a.textContent.trim(),
                href: a.href
            }))
    """)
    print(f"Found {len(links['result'])} links")
```

### Extract Data Attributes

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com/products")

    # Get product ID
    product_id = pw.get_attribute(".product-item", "data-product-id")
    print(f"Product ID: {product_id['value']}")

    # Get all data attributes
    data = pw.evaluate("""
        {
            id: document.querySelector('.product').dataset.id,
            name: document.querySelector('.product').dataset.name,
            price: document.querySelector('.product').dataset.price
        }
    """)
    print(f"Product data: {data['result']}")
```

### Extract Table Data

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com/table")

    # Extract table data
    table_data = pw.evaluate("""
        Array.from(document.querySelectorAll('table tr')).map(row =>
            Array.from(row.querySelectorAll('td')).map(cell => cell.textContent.trim())
        )
    """)

    for row in table_data['result']:
        print(row)
```

## JavaScript Evaluation

### Simple Evaluation

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com")

    # Get page title
    title = pw.evaluate("document.title")
    print(f"Title: {title['result']}")

    # Count elements
    link_count = pw.evaluate("document.querySelectorAll('a').length")
    print(f"Number of links: {link_count['result']}")
```

### Complex Data Extraction

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com")

    # Extract structured data
    page_data = pw.evaluate("""
        ({
            title: document.title,
            url: window.location.href,
            stats: {
                links: document.querySelectorAll('a').length,
                images: document.querySelectorAll('img').length,
                forms: document.querySelectorAll('form').length,
                buttons: document.querySelectorAll('button').length
            },
            meta: {
                description: document.querySelector('meta[name="description"]')?.content,
                keywords: document.querySelector('meta[name="keywords"]')?.content
            }
        })
    """)

    data = page_data['result']
    print(f"Page: {data['title']}")
    print(f"Links: {data['stats']['links']}")
    print(f"Description: {data['meta']['description']}")
```

### Modify Page Content

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com")

    # Highlight all links
    pw.evaluate("""
        document.querySelectorAll('a').forEach(link => {
            link.style.backgroundColor = 'yellow';
            link.style.border = '2px solid red';
        })
    """)

    # Take screenshot with highlights
    pw.take_screenshot(filename="highlighted_links.png")
```

### Get Computed Styles

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com")

    # Get element styles
    styles = pw.evaluate("""
        {
            color: window.getComputedStyle(document.querySelector('h1')).color,
            fontSize: window.getComputedStyle(document.querySelector('h1')).fontSize,
            fontFamily: window.getComputedStyle(document.querySelector('h1')).fontFamily
        }
    """)

    print(f"Heading styles: {styles['result']}")
```

## Wait Operations

### Wait for Element

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com")

    # Click button that loads content
    pw.click("#load-more-button")

    # Wait for new content to appear
    result = pw.wait_for_selector(".new-content", timeout=10000)

    if result['success']:
        print("Content loaded!")
    else:
        print(f"Timeout: {result['error']}")
```

### Wait Before Interaction

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com/dynamic-page")

    # Wait for element before clicking
    pw.wait_for_selector("#dynamic-button")
    pw.click("#dynamic-button")

    # Wait for modal
    pw.wait_for_selector(".modal.visible")
    pw.take_screenshot(filename="modal.png")
```

### Handle Slow Loading

```python
with PlaywrightNative() as pw:
    pw.navigate("https://slow-loading-site.com")

    # Wait up to 60 seconds for content
    result = pw.wait_for_selector(".main-content", timeout=60000)

    if result['success']:
        content = pw.get_content()
        print(f"Content loaded: {len(content['content'])} bytes")
```

## Complete Workflows

### E-commerce Checkout

```python
with PlaywrightNative() as pw:
    # Browse product
    pw.navigate("https://shop.example.com/products")
    pw.wait_for_selector(".product-grid")
    pw.take_screenshot(filename="1_products.png")

    # Select product
    pw.click(".product-item:first-child")
    pw.wait_for_selector(".product-details")
    pw.take_screenshot(filename="2_product_detail.png")

    # Add to cart
    pw.click("#add-to-cart")
    pw.wait_for_selector(".cart-notification")
    pw.take_screenshot(filename="3_added_to_cart.png")

    # Go to cart
    pw.click(".cart-link")
    pw.wait_for_selector(".cart-items")
    pw.take_screenshot(filename="4_cart.png")

    # Checkout
    pw.click("#checkout-button")
    pw.wait_for_selector(".checkout-form")

    # Fill shipping info
    pw.fill_form([
        {"selector": "#name", "value": "John Doe", "type": "text"},
        {"selector": "#address", "value": "123 Main St", "type": "text"},
        {"selector": "#city", "value": "New York", "type": "text"},
        {"selector": "#zip", "value": "10001", "type": "text"}
    ])

    pw.take_screenshot(filename="5_checkout_filled.png")
```

### Data Collection

```python
with PlaywrightNative() as pw:
    urls = [
        "https://example.com/page1",
        "https://example.com/page2",
        "https://example.com/page3"
    ]

    collected_data = []

    for url in urls:
        pw.navigate(url)
        pw.wait_for_selector(".content")

        # Extract data
        data = pw.evaluate("""
            ({
                title: document.title,
                headings: Array.from(document.querySelectorAll('h1, h2'))
                    .map(h => h.textContent.trim()),
                links: Array.from(document.querySelectorAll('a'))
                    .map(a => a.href)
            })
        """)

        collected_data.append(data['result'])

        # Take evidence screenshot
        pw.take_screenshot(filename=f"page_{len(collected_data)}.png")

    # Process collected data
    for i, data in enumerate(collected_data, 1):
        print(f"\nPage {i}: {data['title']}")
        print(f"Headings: {len(data['headings'])}")
        print(f"Links: {len(data['links'])}")
```

### Testing User Flow

```python
with PlaywrightNative() as pw:
    # Start at homepage
    result = pw.navigate("https://example.com")
    assert result['success'], "Homepage failed to load"
    pw.take_screenshot(filename="step1_homepage.png")

    # Search for product
    pw.type_text("#search", "laptop")
    pw.click("#search-button")
    pw.wait_for_selector(".search-results")
    assert pw.get_text(".result-count")['text'] != "0 results"
    pw.take_screenshot(filename="step2_search_results.png")

    # Click first result
    pw.click(".search-results .product:first-child")
    pw.wait_for_selector(".product-title")
    pw.take_screenshot(filename="step3_product_page.png")

    # Add to cart
    pw.click("#add-to-cart")
    pw.wait_for_selector(".cart-updated")
    cart_count = pw.get_text(".cart-count")
    assert cart_count['text'] == "1"
    pw.take_screenshot(filename="step4_added_to_cart.png")

    print("✓ User flow test passed!")
```

## Error Handling

### Basic Error Checking

```python
with PlaywrightNative() as pw:
    result = pw.navigate("https://example.com")

    if not result['success']:
        print(f"Navigation failed: {result['error']}")
        return

    print(f"Successfully loaded: {result['title']}")
```

### Retry on Failure

```python
with PlaywrightNative() as pw:
    max_retries = 3

    for attempt in range(max_retries):
        result = pw.navigate("https://flaky-site.com")

        if result['success']:
            break

        print(f"Attempt {attempt + 1} failed: {result['error']}")
        if attempt < max_retries - 1:
            print("Retrying...")
            import time
            time.sleep(2)
    else:
        print("All attempts failed!")
```

### Graceful Degradation

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com")

    # Try to click optional element
    result = pw.click(".optional-banner-close")
    if not result['success']:
        print("No banner to close, continuing...")

    # Continue with main flow
    pw.click("#main-content-button")
```

### Timeout Handling

```python
with PlaywrightNative() as pw:
    pw.navigate("https://example.com")

    # Try with short timeout first
    result = pw.wait_for_selector(".dynamic-content", timeout=5000)

    if not result['success']:
        if 'timeout' in result['error'].lower():
            print("Content loading slowly, waiting longer...")
            result = pw.wait_for_selector(".dynamic-content", timeout=30000)

    if result['success']:
        content = pw.get_text(".dynamic-content")
        print(f"Content: {content['text']}")
```

## CLI Examples

### Basic CLI Usage

```bash
# Navigate
python3 playwright_controller.py navigate https://example.com

# Take screenshot
python3 playwright_controller.py screenshot --filename homepage.png

# Get page content
python3 playwright_controller.py content > page.html

# Get element text
python3 playwright_controller.py text "h1"
```

### Scripted CLI Workflow

```bash
#!/bin/bash

# Automated screenshot workflow
SCRIPT="python3 ~/.claude/skills/playwright/scripts/playwright_controller.py"

# Navigate to site
$SCRIPT navigate https://example.com

# Take screenshot
$SCRIPT screenshot --full-page --filename full_page.png

# Click navigation
$SCRIPT click ".nav-link:first-child"

# Wait a moment for page load
sleep 2

# Take another screenshot
$SCRIPT screenshot --filename after_click.png

# Close browser
$SCRIPT close

echo "Screenshots saved!"
```

### Batch Processing

```bash
#!/bin/bash

# Screenshot multiple pages
URLS=(
    "https://example.com/page1"
    "https://example.com/page2"
    "https://example.com/page3"
)

SCRIPT="python3 playwright_controller.py"

for i in "${!URLS[@]}"; do
    echo "Processing ${URLS[$i]}..."
    $SCRIPT navigate "${URLS[$i]}"
    $SCRIPT screenshot --full-page --filename "page_$i.png"
done

$SCRIPT close
echo "All screenshots complete!"
```

## Tips and Tricks

### Wait for Network Idle

```python
# navigate() already waits for network idle
pw.navigate("https://example.com")  # Waits automatically
```

### Check if Element Exists

```python
result = pw.wait_for_selector(".element", timeout=1000)
if result['success']:
    print("Element exists!")
else:
    print("Element not found")
```

### Get Multiple Elements

```python
elements = pw.evaluate("""
    Array.from(document.querySelectorAll('.item')).map(el => ({
        text: el.textContent.trim(),
        class: el.className,
        id: el.id
    }))
""")

for elem in elements['result']:
    print(f"Element: {elem}")
```

### Conditional Actions

```python
# Check if element exists before clicking
has_banner = pw.evaluate("""
    document.querySelector('.banner') !== null
""")

if has_banner['result']:
    pw.click(".banner .close-button")
```

For more examples, see the test files:
- `~/.claude/skills/playwright/tests/test_playwright_controller.py`
- `~/.claude/skills/playwright/tests/test_integration.py`
