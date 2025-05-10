# Contributing Guidelines

Thank you for considering contributing to this project! All contributions (bug reports, feature requests, documentation, code improvements) are welcome.

## How to Contribute

1. **Fork** the repository on GitHub
2. **Clone** your fork locally
3. Create a **new branch** for your changes (`git checkout -b your-feature-branch`)
4. **Commit** your changes (see commit message guidelines below)
5. **Push** to your fork (`git push origin your-feature-branch`)
6. Open a **Pull Request** against the main branch

## Code Style

- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) style guidelines
- Document new functions with comments (I tend to avoid Docstrings, but you may use them if it's your preference)

## Commit Messages

- Use present tense ("Add feature" not "Added feature")
- Keep the subject line under 50 characters
- Include a more detailed body when necessary
- Reference issues with `#123` when applicable


## Pull Requests

- Keep PRs focused on a single feature/bugfix
- Include a clear description of changes
- Reference related issues
- Update documentation if needed

## Development Setup

1. Run the `setup` script with `dev` as an argument: `./setup.sh dev`
2. Activate the virtual environment
   ```bash
   source venv/bin/activate
   ```
3. Run `pytest` locally before submitting a pull request
