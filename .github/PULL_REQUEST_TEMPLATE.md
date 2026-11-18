## Summary

<!-- What changed, and why? One sentence is enough. -->

## Type of change

- [ ] Domain addition
- [ ] Domain removal
- [ ] Domain correction
- [ ] Documentation
- [ ] Tooling

## Related issue

<!-- Use Refs #123 if relevant. Do not use automatic issue-closing keywords. -->

## Evidence and verification

See the [domain evidence methodology](https://github.com/furkan-bayrak/lg-tv-blocklist/blob/main/docs/methodology.md#from-data-to-tiers).

<!-- For domain changes, separate attributed TV contact, purpose, and
compatibility when blocking the actual scope. Link evidence or include minimal
sanitized excerpts. DNS resolution and TLS identity alone don't show purpose
or TV compatibility. For blocking tests, include the rules, features checked,
result, and date. Say unknown or not tested where appropriate.
For other changes, describe only how you verified the change. -->

## SAFE/STRICT impact

See the [format-scope table](https://github.com/furkan-bayrak/lg-tv-blocklist/blob/main/docs/overview.md#format-scope).

<!-- For changes to list behavior, state the tier, action, affected rule scope
(exact name, suffix/zone, or regex), and known feature risks. STRICT adds to
SAFE; zones are STRICT-only. A new SAFE entry or promotion requires established
ad/telemetry purpose and a documented blocking test at the actual scope. A new
weak STRICT entry needs attributed contact, attributed purpose evidence, or an
explicit linked sibling-coverage rationale. Delete this section and Device
context if neither applies. -->

## Device context

<!-- When relevant: TV model, exact firmware/webOS build, TV service region,
blocker and version, and list format. Keep unknown details explicit. -->

## Testing and validation

Use the applicable checks in the [contribution guide](https://github.com/furkan-bayrak/lg-tv-blocklist/blob/main/CONTRIBUTING.md#verification).

- [ ] Domain changes: edited annotated `src/` files, not generated `lists/`.
- [ ] Source or script changes: ran `python3 scripts/build.py check` and `python3 -m unittest discover -s scripts -p 'test_[bclnv]*.py'`.
- [ ] If relevant: ran the publication, dnsmasq, or hook checks in the guide.
- [ ] Documentation changes: previewed Markdown and checked updated links.

<!-- Record results and limits. Remove inapplicable checklist items. -->
