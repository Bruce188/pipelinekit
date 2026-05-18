# Testing Documentation

Comprehensive guide to the Playwright skill test suite, including how to run tests, interpret coverage reports, and write new tests.

## Test Suite Overview

The Playwright skill includes a robust test suite with **98% code coverage**:

- **57 unit tests**: Fast, mocked tests covering all functionality
- **5 integration tests**: Real browser tests with actual Playwright
- **62 total tests**: Comprehensive coverage of all features

## Test Structure

```
tests/
├── conftest.py                      # Pytest fixtures and configuration
├── test_playwright_controller.py    # Unit tests (57 tests)
└── test_integration.py              # Integration tests (5 tests)
```

### Test Categories

#### Unit Tests (57 tests)

Fast tests using mocked Playwright browser. No actual browser required.

1. **Initialization & Lifecycle** (3 tests)
   - Controller initialization
   - Context manager entry/exit
   - Resource cleanup

2. **Navigation** (5 tests)
   - URL navigation
   - Back/forward navigation
   - Page reload
   - Error handling

3. **Element Interaction** (6 tests)
   - Click (left, right, middle button)
   - Double-click
   - Type text (with/without delay)
   - Hover

4. **Screenshots** (5 tests)
   - Default filename generation
   - Custom filenames
   - Full page screenshots
   - Element-specific screenshots
   - Auto file extension handling

5. **Form Filling** (4 tests)
   - Text inputs
   - Checkboxes
   - Select dropdowns
   - Mixed field types

6. **Content Extraction** (3 tests)
   - Page HTML content
   - Element text
   - Element attributes

7. **Wait Operations** (2 tests)
   - Wait for selector
   - Custom timeout handling

8. **JavaScript Evaluation** (2 tests)
   - Execute JavaScript
   - Error handling

9. **Resource Cleanup** (2 tests)
   - Proper resource release
   - Handling None values

10. **Error Handling** (13 tests)
    - All methods with error scenarios
    - Graceful failure handling

11. **CLI Interface** (10 tests)
    - All CLI commands
    - Argument parsing
    - Unknown command handling

12. **Selector Types** (4 tests)
    - ID selectors
    - Class selectors
    - Element selectors
    - Attribute selectors

#### Integration Tests (5 tests)

Real browser tests using actual Playwright. Requires Playwright installed.

1. **Real Navigation**: Navigate to https://example.com
2. **Real Screenshots**: Capture actual page screenshots
3. **Real Content**: Extract content from live pages
4. **JavaScript Execution**: Run JavaScript on real pages
5. **Complete Workflow**: Full end-to-end test

## Running Tests

### Prerequisites

```bash
# Install test dependencies
pip3 install -r requirements-test.txt
```

### Basic Test Commands

```bash
# Run all tests
python3 -m pytest

# Run with verbose output
python3 -m pytest -v

# Run specific test file
python3 -m pytest tests/test_playwright_controller.py

# Run specific test class
python3 -m pytest tests/test_playwright_controller.py::TestPlaywrightNativeNavigation

# Run specific test
python3 -m pytest tests/test_playwright_controller.py::TestPlaywrightNativeNavigation::test_navigate_success
```

### Test Markers

Tests are organized with markers for selective execution:

```bash
# Run only unit tests (fast, no browser)
python3 -m pytest -m "not integration"

# Run only integration tests (requires Playwright)
python3 -m pytest -m integration

# Run slow tests
python3 -m pytest -m slow
```

### Coverage Reports

```bash
# Run with coverage report in terminal
python3 -m pytest --cov=scripts --cov-report=term-missing

# Generate HTML coverage report
python3 -m pytest --cov=scripts --cov-report=html

# Generate XML coverage report (for CI/CD)
python3 -m pytest --cov=scripts --cov-report=xml

# All coverage formats
python3 -m pytest --cov=scripts --cov-report=term-missing --cov-report=html --cov-report=xml
```

### View Coverage Report

```bash
# macOS
open htmlcov/index.html

# Linux
xdg-open htmlcov/index.html

# Windows
start htmlcov/index.html
```

## Current Coverage

**98.02% coverage** (202 of 206 lines covered)

### Covered Lines: 202
- All navigation methods
- All element interaction methods
- All screenshot methods
- All form filling methods
- All content extraction methods
- All wait operations
- All JavaScript evaluation
- All error handling paths
- All CLI commands
- Context manager functionality

### Uncovered Lines: 4 (lines 17-19, 301)
- Import error handling (lines 17-19)
- `if __name__ == "__main__"` guard (line 301)

These lines are intentionally not covered as they handle edge cases:
- Import failure when Playwright not installed
- Direct script execution guard

## Test Configuration

### pytest.ini

```ini
[pytest]
minversion = 7.0
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Test markers
markers =
    unit: Unit tests (fast, no external dependencies)
    integration: Integration tests (require real browser)
    slow: Slow-running tests

# Coverage settings
addopts =
    -ra
    --strict-markers
    --tb=short
    -v
    --cov=scripts
    --cov-report=term-missing
    --cov-report=html:htmlcov
    --cov-report=xml
    --cov-fail-under=80
```

### Key Settings

- **Minimum version**: pytest 7.0+
- **Test discovery**: Automatic in `tests/` directory
- **Coverage threshold**: 80% (currently at 98%)
- **Traceback style**: Short for readability
- **Strict markers**: Prevents typos in test markers

## Fixtures

### conftest.py Fixtures

#### `mock_playwright`
Provides a fully mocked Playwright instance for unit tests.

```python
def test_example(mock_playwright):
    # mock_playwright contains:
    # - mock_playwright['playwright']
    # - mock_playwright['browser']
    # - mock_playwright['context']
    # - mock_playwright['page']
```

#### `playwright_controller`
Creates a PlaywrightNative instance with mocked dependencies.

```python
def test_example(playwright_controller):
    result = playwright_controller.navigate("https://example.com")
    assert result["success"] is True
```

#### `sample_html`
Provides sample HTML for testing content extraction.

```python
def test_example(sample_html):
    # sample_html contains a full HTML document
    # with form elements, buttons, etc.
```

#### `temp_screenshot_dir`
Creates a temporary directory for screenshot tests.

```python
def test_example(temp_screenshot_dir):
    screenshot_path = temp_screenshot_dir / "test.png"
    # Use for screenshot testing
```

## Writing New Tests

### Unit Test Template

```python
class TestNewFeature:
    """Test new feature functionality."""

    def test_feature_success(self, playwright_controller, mock_playwright):
        """Test successful feature execution."""
        # Arrange
        mock_playwright['page'].some_method.return_value = "expected"

        # Act
        result = playwright_controller.new_feature()

        # Assert
        assert result["success"] is True
        assert result["data"] == "expected"
        mock_playwright['page'].some_method.assert_called_once()

    def test_feature_error_handling(self, playwright_controller, mock_playwright):
        """Test feature error handling."""
        # Arrange
        mock_playwright['page'].some_method.side_effect = Exception("Error")

        # Act
        result = playwright_controller.new_feature()

        # Assert
        assert result["success"] is False
        assert "error" in result
        assert "Error" in result["error"]
```

### Integration Test Template

```python
@pytest.mark.integration
class TestNewFeatureIntegration:
    """Integration tests for new feature."""

    def test_real_feature(self, check_playwright_installed):
        """Test feature with real browser."""
        from playwright_controller import PlaywrightNative

        with PlaywrightNative() as pw:
            pw.navigate("https://example.com")
            result = pw.new_feature()

            assert result["success"] is True
            # Additional real-world assertions
```

### Best Practices

1. **Arrange-Act-Assert Pattern**
   - Arrange: Set up test conditions
   - Act: Execute the code under test
   - Assert: Verify the results

2. **Descriptive Test Names**
   - Use clear, descriptive names: `test_navigate_success`
   - Include scenario in name: `test_click_with_different_buttons`

3. **One Assertion Per Concept**
   - Test one thing at a time
   - Use multiple tests for different scenarios

4. **Mock External Dependencies**
   - Mock browser for unit tests
   - Use real browser only for integration tests

5. **Test Error Paths**
   - Always test error handling
   - Verify error messages are helpful

6. **Use Fixtures**
   - Leverage existing fixtures
   - Create new fixtures for repeated setup

## Common Testing Patterns

### Testing Successful Operations

```python
def test_operation_success(self, playwright_controller, mock_playwright):
    """Test successful operation."""
    result = playwright_controller.some_method()

    assert result["success"] is True
    assert "expected_field" in result
```

### Testing Error Handling

```python
def test_operation_error(self, playwright_controller, mock_playwright):
    """Test operation error handling."""
    mock_playwright['page'].method.side_effect = Exception("Test error")

    result = playwright_controller.some_method()

    assert result["success"] is False
    assert "error" in result
```

### Testing With Parameters

```python
@pytest.mark.parametrize("param,expected", [
    ("value1", "result1"),
    ("value2", "result2"),
    ("value3", "result3"),
])
def test_with_params(self, playwright_controller, param, expected):
    """Test with different parameters."""
    result = playwright_controller.method(param)
    assert result["data"] == expected
```

### Testing CLI Commands

```python
@patch('sys.argv', ['script.py', 'command', 'arg1'])
@patch('playwright_controller.PlaywrightNative')
@patch('builtins.print')
def test_cli_command(self, mock_print, mock_controller_class):
    """Test CLI command."""
    from playwright_controller import main

    mock_controller = MagicMock()
    mock_controller.__enter__ = Mock(return_value=mock_controller)
    mock_controller.__exit__ = Mock(return_value=False)
    mock_controller_class.return_value = mock_controller

    main()

    mock_controller.method.assert_called_once_with('arg1')
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ${{ vars.BLACKSMITH_RUNNER || 'blacksmith-4vcpu-ubuntu-2204' }}
    steps:
      - uses: actions/checkout@v2   # No Blacksmith drop-in — using upstream actions/checkout
      - uses: useblacksmith/setup-python@v6
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          pip install -r requirements-test.txt
          pip install playwright
          python -m playwright install chromium

      - name: Run tests
        run: python -m pytest --cov=scripts --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v2   # No Blacksmith drop-in — using upstream codecov/codecov-action
```

## Troubleshooting Tests

### "Playwright not installed" in Integration Tests

```bash
# Install Playwright for integration tests
pip3 install playwright
python3 -m playwright install chromium
```

### Tests Failing Randomly

- Check for test interdependencies
- Ensure proper mocking in unit tests
- Verify fixtures are properly isolated

### Coverage Not Reaching 80%

```bash
# Generate detailed coverage report
python3 -m pytest --cov=scripts --cov-report=term-missing

# Look for uncovered lines in report
# Add tests for missing coverage
```

### Integration Tests Timeout

```bash
# Increase timeout in pytest.ini
# Or skip integration tests
python3 -m pytest -m "not integration"
```

## Test Performance

### Typical Test Times

- **Unit tests**: ~0.7 seconds (57 tests)
- **Integration tests**: ~5-10 seconds (5 tests)
- **Total suite**: ~6-11 seconds

### Optimizing Test Speed

1. **Run unit tests during development**
   ```bash
   python3 -m pytest -m "not integration"
   ```

2. **Run specific test files**
   ```bash
   python3 -m pytest tests/test_playwright_controller.py
   ```

3. **Use pytest-xdist for parallel execution**
   ```bash
   pip install pytest-xdist
   python3 -m pytest -n auto
   ```

## Test Metrics

### Current Metrics (as of v1.0.0)

- **Total Tests**: 62
- **Unit Tests**: 57
- **Integration Tests**: 5
- **Code Coverage**: 98.02%
- **Test Execution Time**: ~0.7s (unit only)
- **Lines Covered**: 202/206
- **Branches Covered**: N/A (not measured)

## Contributing Tests

When contributing new features:

1. **Write tests first** (TDD approach)
2. **Ensure 80%+ coverage** for new code
3. **Add both unit and integration tests** where applicable
4. **Update this documentation** if adding new test patterns
5. **Run full test suite** before submitting

## References

- **Pytest Documentation**: https://docs.pytest.org/
- **Playwright Python**: https://playwright.dev/python/
- **Coverage.py**: https://coverage.readthedocs.io/
- **pytest-cov**: https://pytest-cov.readthedocs.io/
