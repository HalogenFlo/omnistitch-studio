# Project Governance & Maintainership Policy

## 1. Governance Model
OmniStitch Studio is an open-source project managed under a **Maintainer-Driven Governance Model**. The goal is to provide a transparent and welcoming environment for contributors, researchers, and developers in microscopy and computer vision.

## 2. Roles & Responsibilities

### Primary Maintainer (Project Lead)
- Sets the strategic technical direction and architecture of the project.
- Has final decision-making authority in the event of unresolved consensus.
- Manages security advisories, major semantic releases, and core infrastructure credentials.

### Core Maintainers
- Review, approve, and merge Pull Requests.
- Triage incoming issues and assign milestones.
- Ensure automated test coverage (CI/CD) and performance standards remain intact.
- Enforce the [Code of Conduct](CODE_OF_CONDUCT.md).

### Contributors
- Anyone who submits issues, code contributions, documentation enhancements, or algorithm improvements.
- Contributors who demonstrate consistent, high-quality involvement over time are invited to become Core Maintainers.

## 3. Decision-Making Process
- **Consensus-Seeking**: Technical proposals and architecture changes are discussed publicly on GitHub Issues and Pull Requests.
- **Lazy Consensus**: If no maintainer objects within 72 hours of a non-breaking proposal, it is considered approved.
- **Breaking Changes**: Major changes affecting API endpoints, coordinate contracts, or file schemas require public review. While the project has one maintainer, the primary maintainer records the decision and rationale in an issue or pull request. If two or more maintainers are active, approval from at least two maintainers is required.

## 4. Release Cadence
- **Patch Releases (`x.y.Z`)**: Issued as needed for bug fixes, performance improvements, and security patches.
- **Minor Releases (`x.Y.0`)**: Issued periodically for backwards-compatible new features (e.g., new file format exporters or alignment modes).
- **Major Releases (`X.0.0`)**: Reserved for substantial architectural redesigns or breaking changes.
