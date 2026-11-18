---
name: Breakage report (false positive)
about: Something stopped working after using the list
title: '[Breakage] '
labels: breakage
assignees: ''
---

**App / feature and exact symptom / error**

**Environment**
- TV model:
- Exact firmware / webOS build (or unknown):
- TV service country / region:
- Blocker and version:
- Exact list URL / tier / format:
- `# Updated:` header or source revision:
- Downloaded artifact commit permalink or SHA-256 (optional, or unknown):
- Localized lists, regex, hosts file, other filters / exceptions:
- For localized files: target region and input artifact commit or SHA-256 (if known):

**Reproduction**
- Activity and time of failure:
- Minimal sanitized queried/blocked hostnames and timestamps:
- Suspected rule (unknown is acceptable):

**Did a narrow exception restore the feature?**
- [ ] Yes
- [ ] No
- [ ] Not tested

Change only the suspected rule if feasible, keeping other protection unchanged.
Explain which scope was allowed; do not open a whole service zone just to test
a single hostname. If no rule is identified, report that rather than broadly
disabling protection without a bounded diagnostic and rollback.

- Cache clear / expiry and retest steps:
- Cold boot versus standby/wake outcome, if relevant:
- Rollback steps and result:

**Before posting:** minimal sanitized text only, not full raw captures or
credentials. Remove tokens, MACs, SSIDs, public IPs and identifiable client
details. State unknown/not tested instead of guessing.
