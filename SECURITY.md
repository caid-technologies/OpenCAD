# Security Policy

OpenCAD is an open-source project and welcomes responsible security reports.

## Supported Versions

Security fixes are applied to the default branch first. Point releases are created as needed.

## Reporting a Vulnerability

Do not open public issues for vulnerabilities.

Send a private report with:
- Affected component (`opencad.kernel`, `opencad.solver`, `opencad.tree`, `opencad_agent`, or `opencad_viewport`)
- Reproduction steps and impact
- Proof-of-concept details (minimal)
- Suggested mitigation if available

Until a dedicated security inbox is published, use repository maintainer contact channels and mark the message as `SECURITY`.

## Security Baseline

- API docs can be disabled with `OPENCAD_ENABLE_DOCS=false`.
- CORS is controlled with `OPENCAD_CORS_ALLOW_ORIGINS` and should be restricted in production.
- Keep OpenCAD services behind a reverse proxy with TLS and authentication/authorization.
- Do not commit `.env` files, tokens, or private datasets.

## Disclosure Process

1. Report received and acknowledged.
2. Triage and severity assessment.
3. Patch development and validation.
4. Coordinated disclosure with release notes.
