# Contributing to Travel Planner

Thank you for your interest in contributing to the Travel Planner project! This document provides guidelines and instructions for getting involved.

## Getting Started

1. Fork the repository on GitHub
2. Clone your forked repository locally
3. Create a feature branch: `git checkout -b feature/your-feature-name`
4. Make your changes
5. Push to your fork: `git push origin feature/your-feature-name`
6. Create a Pull Request with a clear description

## Development Setup

### Backend Development

```bash
cd server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"  # Install dev dependencies if available

# Set up pre-commit hooks (optional)
pip install pre-commit
pre-commit install
```

### Frontend Development

```bash
cd client
npm install
npm run dev
```

## Code Standards

### Python (Backend)

- Use PEP 8 style guide
- Run `pylint` on your code
- Add type hints where possible
- Document complex functions with docstrings

```bash
pylint src/ main.py
mypy src/ main.py  # If available
```

### TypeScript/React (Frontend)

- Follow ESLint rules (auto-configured via create-react-app)
- Use strict mode TypeScript
- Add JSDoc comments for complex functions
- Components should be functional with hooks

```bash
npm run lint
```

## Testing

### Backend Tests

```bash
cd server
pytest tests/ -v
pytest tests/ --cov=src/  # With coverage
```

### Frontend Tests

```bash
cd client
npm test
npm test -- --coverage
```

## Commit Messages

Use clear, descriptive commit messages:

```
feat: Add WebSocket message routing
fix: Resolve date parsing edge case
docs: Update API endpoint documentation
refactor: Simplify agent initialization
test: Add tests for TravelState validation
```

Prefix types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Code style (formatting, missing semicolons, etc.)
- `refactor`: Code refactoring (no feature changes)
- `perf`: Performance improvements
- `test`: Tests
- `chore`: Build, dependencies, etc.

## Pull Request Process

1. **Update README.md** if you've added new features or changed behavior
2. **Add tests** for any new functionality
3. **Update documentation** for API changes
4. **Ensure all tests pass**: `npm test` and `pytest`
5. **Check for linting issues**: Run linters before submitting
6. **Keep PRs focused**: One feature/fix per PR
7. **Write a clear PR description** explaining:
   - What changes are being made
   - Why these changes are necessary
   - How to test the changes

## Issue Reporting

When reporting bugs, please include:

- Description of the issue
- Steps to reproduce
- Expected behavior
- Actual behavior
- Environment details (OS, Python version, Node version, etc.)
- Screenshots/logs if applicable

## Feature Requests

For feature requests, explain:

- The use case and why it's needed
- How it would be used
- Any implementation suggestions
- Potential impacts on existing features

## Architecture Guidelines

### Adding New Agents

1. Create agent class in `server/src/agents.py`
2. Define specialized tools in `server/src/tools/`
3. Add agent to `TravelPlannerFlow`
4. Update state machine to handle new agent output
5. Test with mock tools first

### Adding New API Endpoints

1. Define request/response models in `server/src/schema.py`
2. Add endpoint to `server/main.py`
3. Handle WebSocket broadcasts if needed
4. Add integration tests
5. Update API documentation

### Adding New Frontend Components

1. Create component in `client/src/components/`
2. Use TypeScript with proper typing
3. Integrate with Zustand store if state needed
4. Use Tailwind for styling (no CSS files unless necessary)
5. Export from component barrel file if applicable

## Security

- Don't commit API keys or secrets
- Use `.env.example` for configuration templates
- Run security checks: `bandit` for Python, `npm audit` for Node
- Report security issues privately (don't create public issues)
- Keep dependencies updated

## Documentation

- Add docstrings to Python functions and classes
- Add JSDoc comments to TypeScript functions
- Update README.md for major changes
- Add inline comments for complex logic
- Keep API documentation up-to-date

## Performance

- Profile code before and after optimization
- Test with realistic data volumes
- Monitor WebSocket message frequency
- Use React DevTools Profiler for UI performance
- Document any performance considerations

## Questions?

- Open an issue with the `question` label
- Check existing discussions/issues
- Review documentation
- Ask in commit comments for context

## Code of Conduct

Be respectful, inclusive, and professional. We welcome diverse perspectives and backgrounds.

Thank you for contributing! 🙏
