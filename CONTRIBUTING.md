# Contributing to OmniStitch Studio

Thank you for your interest in contributing to **OmniStitch Studio**. Contributions from researchers, imaging engineers, and developers are welcome.

## Code of Conduct
This project adheres to the Contributor Covenant [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## How Can I Contribute?
1. **Reporting Bugs**: Check the GitHub issue tracker before filing a new bug report. Provide detailed reproduction steps and slide metadata.
2. **Suggesting Enhancements**: Open a Feature Request explaining the use case (e.g., support for new microscope formats or GPU-accelerated blending).
3. **Pull Requests**:
    - Fork the repository and create your branch from `master`.
   - Ensure your code follows PEP 8 conventions.
   - Run the test suite:
     ```bash
     python -m unittest discover -s tests
     ```
   - Submit your pull request with a descriptive title and linked issue.

## Development Setup
```bash
git clone https://github.com/Phatjhhoq8/omnistitch-studio.git
cd omnistitch-studio
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   python -m pip install -e .
   omnistitch-studio
```
Open `http://localhost:5000` in your web browser.

## Scientific and Test Expectations

- Add deterministic tests for changes to registration, compositing, project schemas, or export behavior.
- For algorithm changes, include synthetic ground truth or a redistributable data set and report the error metric used.
- Do not include patient-identifying or otherwise restricted image data in issues, tests, or pull requests.
- Distinguish measured results from expectations and document known limitations.
