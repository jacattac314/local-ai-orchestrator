# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please report it responsibly.

### How to Report

1. **Do NOT open a public issue** for security vulnerabilities
2. Email security concerns to: [Create a private security advisory](https://github.com/jacattac314/local-ai-orchestrator/security/advisories/new)
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- **Acknowledgment**: Within 48 hours
- **Initial Assessment**: Within 1 week
- **Resolution Timeline**: Depends on severity
  - Critical: 24-72 hours
  - High: 1-2 weeks
  - Medium: 2-4 weeks
  - Low: Next release cycle

### Security Best Practices

When deploying Local AI Orchestrator:

1. **API Authentication**: Always set `ORCHESTRATOR_API_KEY` in production
2. **HTTPS**: Use a reverse proxy with TLS termination
3. **Network Isolation**: Restrict database access to application only
4. **Secrets Management**: Never commit API keys to version control
5. **SSRF Protection**: Configure `ORCHESTRATOR_ALLOWED_DOMAINS`

### Known Security Considerations

| Area | Mitigation |
|------|------------|
| API Keys | Stored in environment variables, not in code |
| SSRF | URL validation with allowlist |
| SQL Injection | SQLAlchemy ORM with parameterized queries |
| Input Validation | Pydantic models for all inputs |

## Acknowledgments

We appreciate responsible disclosure and will acknowledge researchers who report valid vulnerabilities.
