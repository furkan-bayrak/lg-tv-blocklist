# Security Policy

## Reporting a vulnerability

On the repository's [Security Advisories page](https://github.com/furkan-bayrak/lg-tv-blocklist/security/advisories),
select **Report a vulnerability** if available. Do not disclose a suspected
vulnerability in a public issue, pull request, or comment. If the button is
unavailable, the project has no published alternate private reporting channel.
A repository admin can [enable private vulnerability reporting](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository)
under **Settings → Security and quality → Advanced Security → Private
vulnerability reporting**.

Include the affected component and revision or list URL, the tier and checksum
if known, the impact, and only the sanitized evidence needed to explain it.
Do not include credentials or raw traffic captures.

## Scope

This policy covers the annotated sources (`src/`), published lists and checksums
(`lists/`), GitHub Actions workflows that validate, build, and publish them,
and repository scripts and optional rooted-TV hooks. Examples include malicious
list changes that remove intended protection or block legitimate services,
workflow compromise, and tampering with generated lists or checksums. Defects
in LG firmware or third-party resolvers are outside scope unless the security
impact is caused by this repository's code or data.

## Functional issues

Ordinary false positives, expected STRICT side effects, and device or region
compatibility problems are not security vulnerabilities on their own. Use the
[Breakage report (false positive)](https://github.com/furkan-bayrak/lg-tv-blocklist/issues/new?template=02_breakage.md)
for service breakage and [New LG telemetry domain](https://github.com/furkan-bayrak/lg-tv-blocklist/issues/new?template=01_new_domain.md)
for an evidence-backed domain proposal. Both templates open public issues and
are not alternatives to private vulnerability reporting.

## Supported versions

Maintenance targets `main` and the current lists published from it. There are
no separately maintained releases, feature branches, or older snapshots. If an
older download is affected, include its original revision or checksum if known.
