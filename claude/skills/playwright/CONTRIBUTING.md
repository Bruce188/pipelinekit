# Contributing Guide

Thank you for considering contributing to the Playwright Browser Automation Skill! This guide will help you get started.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Testing Guidelines](#testing-guidelines)
- [Code Style](#code-style)
- [Submitting Changes](#submitting-changes)
- [Feature Requests](#feature-requests)
- [Bug Reports](#bug-reports)

## Code of Conduct

This project follows a simple code of conduct:

- Be respectful and constructive
- Focus on what is best for the project
- Show empathy towards other contributors
- Accept constructive criticism gracefully

## Getting Started

### Prerequisites

- Python 3.8 or higher
- Git for version control
- Basic understanding of browser automation concepts
- Familiarity with pytest for testing

### Quick Start

1. **Clone or fork the project**
2. **Set up development environment** (see below)
3. **Make your changes**
4. **Run tests**
5. **Submit your contribution**

## Development Setup

### 1. Install Dependencies

```bash
# Install Playwright
pip3 install playwright
python3 -m playwright install chromium

# Install development dependencies
pip3 install -r requirements-test.txt
```

### 2. Verify Installation

```bash
# Run all tests
python3 -m pytest

# Should see: 62 passed, 98% coverage
```

### 3. Set Up Your Editor

#### VS Code

Recommended extensions:
- Python
- Pylance
- Python Test Explorer

Settings (`.vscode/settings.json`):
```json
{
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,
  "python.linting.enabled": true,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black"
}
```

#### PyCharm

- Enable pytest as test runner
- Configure Python interpreter
- Enable Black formatter

## Project Structure

```
playwright/
├── README.md                    # Main documentation
├── SKILL.md                     # Skill metadata for Claude Code
├── TESTING.md                   # Testing documentation
├── API.md                       # API reference
├── CONTRIBUTING.md              # This file
├── scripts/
│   └── playwright_controller.py # Main implementation (only file to modify)
├── tests/
│   ├── conftest.py             # Pytest fixtures
│   ├── test_playwright_controller.py  # Unit tests
│   └── test_integration.py     # Integration tests
├── requirements-test.txt        # Development dependencies
├── pytest.ini                   # Pytest configuration
└── htmlcov/                     # Coverage reports (generated)
```

### Key Files

- **`scripts/playwright_controller.py`**: Main implementation - this is where most changes go
- **`tests/test_playwright_controller.py`**: Unit tests - add tests for new features here
- **`tests/conftest.py`**: Shared test fixtures
- **`tests/test_integration.py`**: Integration tests with real browser

## Development Workflow

### 1. Choose What to Work On

- Check existing issues
- Look for "good first issue" labels
- Propose new features via issues first
- Ask questions if unsure

### 2. Create a Branch (if using Git)

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

### 3. Make Your Changes

Follow these principles:

1. **Test-Driven Development (TDD)**
   - Write test first
   - Implement feature
   - Verify test passes

2. **Keep Changes Focused**
   - One feature/fix per contribution
   - Don't mix refactoring with features
   - Keep commits atomic

3. **Maintain Code Quality**
   - Follow existing code style
   - Add docstrings to new methods
   - Update type hints

### 4. Write Tests

**Every new feature or bug fix needs tests!**

#### For New Features

```python
# In test_playwright_controller.py

class TestYourNewFeature:
    """Test new feature functionality."""

    def test_feature_success(self, playwright_controller, mock_playwright):
        """Test successful feature execution."""
        # Arrange
        mock_playwright['page'].new_method.return_value = "result"

        # Act
        result = playwright_controller.new_feature()

        # Assert
        assert result["success"] is True
        assert result["data"] == "result"

    def test_feature_error_handling(self, playwright_controller, mock_playwright):
        """Test feature error handling."""
        mock_playwright['page'].new_method.side_effect = Exception("Error")

        result = playwright_controller.new_feature()

        assert result["success"] is False
        assert "error" in result
```

#### For Bug Fixes

```python
def test_bug_fix_regression(self, playwright_controller):
    """Test that bug XYZ doesn't occur."""
    # Test case that would fail before fix
    result = playwright_controller.method_with_bug()
    assert result["success"] is True  # Now passes
```

### 5. Run Tests Locally

```bash
# Run all tests
python3 -m pytest

# Run specific test
python3 -m pytest tests/test_playwright_controller.py::TestClass::test_method

# Run with coverage
python3 -m pytest --cov=scripts --cov-report=term-missing

# Run only unit tests (faster)
python3 -m pytest -m "not integration"
```

**All tests must pass before submitting!**

### 6. Check Code Quality

```bash
# Format with Black
black scripts/playwright_controller.py

# Check with flake8
flake8 scripts/playwright_controller.py --max-line-length=100

# Type checking (optional)
mypy scripts/playwright_controller.py
```

### 7. Update Documentation

If your change affects users:

- Update README.md
- Update API.md for new methods
- Update SKILL.md if changing capabilities
- Add examples for new features

## Testing Guidelines

### Coverage Requirements

- **Minimum**: 80% coverage (enforced by pytest)
- **Target**: 95%+ coverage
- **Current**: 98% coverage

### Test Types

1. **Unit Tests** (required for all features)
   - Fast, mocked tests
   - Test individual methods
   - Test error handling
   - Test edge cases

2. **Integration Tests** (required for complex features)
   - Real browser tests
   - End-to-end workflows
   - Verify real-world usage

### Writing Good Tests

**Do**:
- Test one thing per test
- Use descriptive test names
- Follow Arrange-Act-Assert pattern
- Test both success and error cases
- Use fixtures for common setup

**Don't**:
- Test implementation details
- Create test dependencies
- Skip error testing
- Use hard-coded values where possible
- Leave commented-out code

### Example Test

```python
def test_navigate_success(self, playwright_controller, mock_playwright):
    """Test successful navigation to URL.

    This test verifies that:
    1. Navigation returns success
    2. URL is properly returned
    3. Page title is retrieved
    4. Playwright goto is called once
    """
    # Arrange - set up test data
    test_url = "https://example.com"
    mock_playwright['page'].url = test_url

    # Act - execute the code
    result = playwright_controller.navigate(test_url)

    # Assert - verify expectations
    assert result["success"] is True
    assert result["url"] == test_url
    assert result["title"] == "Example Domain"
    mock_playwright['page'].goto.assert_called_once()
```

## Code Style

### Python Style Guide

Follow PEP 8 with these specifics:

- **Line length**: 100 characters max (not 79)
- **Indentation**: 4 spaces
- **Quotes**: Double quotes for strings
- **Imports**: Grouped (stdlib, third-party, local)
- **Type hints**: Required for public methods

### Method Structure

```python
def method_name(self, required_param: str,
                optional_param: Optional[str] = None) -> Dict[str, Any]:
    """Brief description of what the method does.

    Longer description if needed, explaining behavior,
    side effects, and important notes.

    Parameters:
    - required_param: Description
    - optional_param: Description (default: None)

    Returns:
    Dictionary with:
    - success: bool
    - data: str (if successful)
    - error: str (if failed)
    """
    try:
        self.start()

        # Implementation
        result = self.page.some_action(required_param)

        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### Docstring Format

Use Google-style docstrings:

```python
def example_method(self, param: str) -> Dict[str, Any]:
    """One-line summary.

    More detailed description if needed.

    Args:
        param: Description of parameter

    Returns:
        Dict containing:
        - success (bool): Operation status
        - data (str): Result data

    Raises:
        ValueError: If param is invalid

    Example:
        >>> result = controller.example_method("test")
        >>> print(result['success'])
        True
    """
```

### Error Handling

All public methods should catch exceptions:

```python
def method(self) -> Dict[str, Any]:
    """Method description."""
    try:
        self.start()
        # ... implementation
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### Response Format

Maintain consistent response format:

```python
# Success
{"success": True, "field1": value1, "field2": value2}

# Error
{"success": False, "error": "Error message"}
```

## Submitting Changes

### Before Submitting

Checklist:
- [ ] All tests pass (`python3 -m pytest`)
- [ ] Coverage is 80%+ (`python3 -m pytest --cov=scripts`)
- [ ] Code is formatted (`black scripts/`)
- [ ] No linting errors (`flake8 scripts/`)
- [ ] Documentation updated
- [ ] Examples added for new features
- [ ] Commit messages are clear

### Commit Messages

Follow conventional commits:

```
type(scope): short description

Longer description if needed.

Fixes #123
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `test`: Adding tests
- `refactor`: Code refactoring
- `perf`: Performance improvement
- `chore`: Maintenance tasks

**Examples**:
```
feat(navigation): add support for custom wait conditions

Add optional wait_condition parameter to navigate() method
to support waiting for custom conditions before returning.

Fixes #42

---

fix(screenshots): handle missing directory path

Create parent directories automatically if they don't exist
when saving screenshots.

Fixes #56

---

docs(api): add examples for fill_form method

Add comprehensive examples showing different field types
and usage patterns.
```

### Submission Process

1. **Ensure quality**
   ```bash
   # Run full test suite
   python3 -m pytest -v

   # Check coverage
   python3 -m pytest --cov=scripts --cov-report=term-missing

   # Format code
   black scripts/
   ```

2. **Document changes**
   - Update CHANGELOG (if exists)
   - Update relevant documentation
   - Add code comments for complex logic

3. **Create clear description**
   - What does this change do?
   - Why is this change needed?
   - How was it tested?
   - Any breaking changes?

## Feature Requests

### Before Requesting

1. **Check existing issues** - may already be planned
2. **Consider scope** - does it fit the skill's purpose?
3. **Think about implementation** - is it feasible?

### Creating a Feature Request

Include:

1. **Problem Description**
   - What problem does this solve?
   - Who would benefit?

2. **Proposed Solution**
   - How should it work?
   - Example usage

3. **Alternatives Considered**
   - Other approaches
   - Why this is best

4. **Additional Context**
   - Screenshots, examples
   - Links to relevant docs

**Example**:

```markdown
## Feature Request: Add Drag and Drop Support

### Problem
Currently there's no way to automate drag-and-drop interactions,
which are common in modern web applications.

### Proposed Solution
Add a `drag_and_drop()` method:

```python
pw.drag_and_drop(
    source="#draggable",
    target="#drop-zone"
)
```

### Use Cases
- File upload interfaces
- Kanban boards
- Sortable lists
- Visual editors

### Implementation Notes
- Use Playwright's `drag_to()` method
- Support both selector-based and coordinate-based targets
- Add tests with mock drag events
```

## Bug Reports

### Before Reporting

1. **Search existing issues**
2. **Try latest version**
3. **Verify it's reproducible**
4. **Check if it's a Playwright issue**

### Creating a Bug Report

Include:

1. **Description**
   - What happened?
   - What should have happened?

2. **Reproduction Steps**
   ```python
   1. Create controller
   2. Navigate to URL
   3. Call method X
   4. See error
   ```

3. **Environment**
   - Python version
   - Playwright version
   - OS and version
   - Browser version

4. **Error Output**
   ```
   Full error message and stack trace
   ```

5. **Expected Behavior**
   - What should happen instead?

**Example**:

```markdown
## Bug: Screenshot fails with relative paths

### Description
`take_screenshot()` fails when given a relative path like `./screenshots/test.png`

### Steps to Reproduce
```python
from playwright_controller import PlaywrightNative

with PlaywrightNative() as pw:
    pw.navigate("https://example.com")
    result = pw.take_screenshot("./screenshots/test.png")
    print(result)  # Shows error
```

### Error Output
```
{'success': False, 'error': 'No such file or directory'}
```

### Expected Behavior
Should create `screenshots/` directory and save screenshot.

### Environment
- Python: 3.9.7
- Playwright: 1.40.0
- OS: Ubuntu 22.04
- Chromium: 120.0.6099.28

### Possible Solution
Create parent directories automatically using `Path.mkdir(parents=True)`
```

## Questions?

- Review existing documentation
- Check the test files for examples
- Look at similar implementations in the code
- Ask in issues (label: question)

## Recognition

Contributors will be recognized in:
- CHANGELOG for significant contributions
- README acknowledgments section
- Git commit history

Thank you for contributing! 🎉
