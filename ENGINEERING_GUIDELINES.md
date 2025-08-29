Here is a concise version of the Python engineering guidelines designed to keep all critical points while being easy for an LLM or anyone else to quickly comprehend and apply:

***

# Python Engineering Guidelines (Concise)## Core Principles- Use **type annotations everywhere** to ensure clarity and safety.
- Follow **PEP 8** style and use **Black** for formatting.
- Use **Ruff** for linting to catch issues early.
- Prefer **explicit** code and **document** complex logic.
- Fail **fast** with strict input validation and meaningful errors.

## Development Setup- Use **Python 3.11+**.
- Use **UV** for dependency and environment management.
- Use **cookiecutter** template for consistent project structure.

## Type Safety & Validation- Strictly type all functions and data structures.
- Use **Pydantic** for runtime data validation.
- Prefer **dataclasses with slots** for immutable data containers.
- Enable strict **MyPy** settings.

## Testing & TDD- Follow **Red-Green-Refactor** cycle of TDD.
- Use **pytest** with a goal of >85% coverage.
- Write focused, parametric, and async tests as needed.
- Use **mocking** for external dependencies.

## Project Structure- Clear separation: `models/`, `services/`, `repositories/`, `utils/`.
- Tests in dedicated `tests/` folder, mirroring source.
- Minimal logic in `__init__.py`.

## Async Programming- Use **async/await** exclusively in async code.
- Always use context managers for resource cleanup.
- Control concurrency with semaphores in async functions.

## Git & Automation- Use **pre-commit hooks** for formatting, linting, type checks, security scans.
- Always run hooks before commit.

## Common Pitfalls to Avoid- No mutable default arguments.
- No bare `except:` — always catch specific exceptions.
- No `eval()` or unsafe dynamic code.
- No blocking calls inside async functions.

## Performance Tips- Profile before optimizing.
- Use generators for large or streaming data.
- Use `__slots__` to save memory in classes.

***

This document captures the modern best practices for Python development, balancing brevity and completeness for easy understanding, enforcement, and automated processing.

If desired, I can provide this content as a ready-to-use markdown file for direct use.
