# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest `main` | ✅ |
| Older releases | ❌ |

## Reporting a Vulnerability

If you discover a vulnerability, **do not open a public issue**. Instead, use GitHub's **private security advisory** channel:

- Go to the **Security** tab of this repository on GitHub
- Click **Report a vulnerability**
- Include: reproducible steps, affected version, expected impact

We acknowledge receipt within **48 hours** and provide a triage status within **72 hours** of acknowledgement.

## CVE Response SLA

| Severity | Patch / mitigation target |
|----------|---------------------------|
| Critical | 48 hours |
| High     | 7 days   |
| Medium   | 30 days  |
| Low      | 90 days  |

Targets are from the date of confirmed triage. Issues outside the project's scope are closed with a rationale.

## Scope

In scope:
- Application code in this repository
- Dependency vulnerabilities surfaced by automated scanning
- Infrastructure-as-code (Dockerfile, GitHub workflows) in this repository

Out of scope:
- Vulnerabilities in third-party services (Razorpay, Groq, etc.) — report to the vendor
- Self-DoS via known-heavy operations (e.g. extremely large text input)
- Best-practice findings without a concrete impact path

## Automated Scanning

This repository runs:
- **CodeQL** — static analysis (`security-extended` query suite, weekly)
- **Renovate** — automated dependency PRs (weekly, with security alerts off-schedule)
- **`pip-audit`** — dependency vulnerability checks on every PR
- **Trivy** — Docker image vulnerability scan on every PR
- **GitHub Dependency Review** — blocks PRs introducing known-vulnerable deps
- **`detect-secrets`** — pre-commit secret scanning
- **`bandit`** — pre-commit Python security linting

## Acknowledgements

We do not currently offer a bug bounty. Responsible disclosure is acknowledged in release notes upon request.
