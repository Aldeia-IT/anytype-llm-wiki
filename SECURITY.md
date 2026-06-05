# Security Policy

We take the security of `anytype-llm-wiki` seriously and appreciate the efforts
of the community to responsibly disclose vulnerabilities. This document explains
which versions receive security fixes, how to report a vulnerability, and what to
expect after you report one.

## Supported Versions

`anytype-llm-wiki` is currently in its preview (`0.x`) phase. Security fixes are
applied to the most recent release line.

| Version | Supported          |
| ------- | ------------------ |
| 0.5.x   | :white_check_mark: Current preview line, receives security fixes |
| < 0.5.0 | :x: Not supported  |

As the project matures, this table will be updated to reflect the versions that
are actively maintained.

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues,
discussions, or pull requests.** Public disclosure before a fix is available can
put users at risk. Use one of the private channels below instead.

### Primary: GitHub Security Advisories (preferred)

We use GitHub's private vulnerability reporting. This keeps the report
confidential between you and the maintainers until a fix is ready and a
coordinated disclosure can be made.

To submit a report:

1. Open the repository on GitHub.
2. Go to the **Security** tab.
3. Select **Report a vulnerability** (under "Reporting" / "Advisories").
4. Fill in the advisory form with as much detail as you can.

A helpful report typically includes:

- A clear description of the vulnerability and its potential impact.
- The affected version(s) and component(s) (for example, the MCP server,
  `semantic_search`, `wiki-bootstrap`, or `doctor`).
- Step-by-step instructions to reproduce the issue.
- Any proof-of-concept code, configuration, or logs (please redact secrets such
  as `ANYTYPE_API_KEY`).
- Suggested remediation, if you have one.

### Backup: email

If GitHub Security Advisories is not an option for you, please contact the
maintainers via the email address listed on the
[Aldeia-IT GitHub organization profile](https://github.com/Aldeia-IT). When using
email, please indicate that the message concerns a security vulnerability so it
can be routed and prioritized appropriately.

## Our Commitment and Response Process

When you report a vulnerability through one of the channels above, you can expect:

- **Acknowledgement within 72 hours** of receiving your report.
- **Triage and an initial assessment within 14 days**, including our view of the
  severity and the likely next steps.
- Regular updates on remediation progress until the issue is resolved.

We follow a **coordinated disclosure** approach: we ask that you give us a
reasonable opportunity to investigate and release a fix before any public
disclosure, and we will work with you on disclosure timing. Once a fix is
available, we are happy to **publicly credit reporters** who wish to be
acknowledged. If you prefer to remain anonymous, we will respect that.

## Regulatory Context

This policy also reflects the vulnerability-handling and reporting expectations
of the EU Cyber Resilience Act (Regulation (EU) 2024/2847). The Act establishes
obligations for products with digital elements, including coordinated
vulnerability handling and the reporting of actively exploited vulnerabilities;
its Article 14 reporting obligations apply from 11 September 2026. By maintaining a
clear private reporting channel, defined response timelines, and a coordinated
disclosure process, the project takes coordinated vulnerability handling
seriously and aligns with these expectations.

## Scope

This policy covers the `anytype-llm-wiki` source code maintained in this
repository. Vulnerabilities in third-party dependencies or in upstream services
(for example, Anytype, Qdrant, or Ollama) should be reported to their respective
maintainers; if you are unsure, feel free to contact us and we will help point
you in the right direction.

Thank you for helping keep `anytype-llm-wiki` and its users safe.
