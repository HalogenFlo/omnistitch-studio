# Security Policy

## Supported Versions
Security fixes are provided for the following versions of **OmniStitch Studio**:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability
The maintainers of OmniStitch Studio take security reports seriously.

If you discover a security vulnerability or weakness within this project:
1. **Do not create a public GitHub issue.**
2. Open a [private GitHub security advisory](https://github.com/Phatjhhoq8/omnistitch-studio/security/advisories/new).
3. Include the following details:
   - Type of issue (e.g., path traversal, memory exhaustion, buffer overflow, arbitrary file overwrite).
   - Step-by-step instructions to reproduce the vulnerability.
   - A minimal sample payload or script reproducing the issue.
   - Potential impact on client or server environments.

## Response Process
- **Initial Acknowledgment**: Within 48 hours of receiving your report.
- **Triage & Assessment**: Within 5 business days, our maintainers will validate the report and assess its severity.
- **Patch & Advisory**: A security patch will be prepared in a private fork and released alongside a public Common Vulnerabilities and Exposures (CVE) / GitHub Security Advisory after coordinated disclosure.

## Security Practices in OmniStitch Studio
- **Local-First Architecture**: All image processing executes strictly on the user's host/server without phoning home or transmitting biomedical slides to third-party endpoints.
- **Path Traversal Protection**: File and directory inputs are strictly sanitized and restricted to designated workspace bounds.
- **Memory-Budgeted Processing**: Large mosaic operations enforce strict RAM consumption ceilings to prevent denial-of-service (DoS) from resource exhaustion.
