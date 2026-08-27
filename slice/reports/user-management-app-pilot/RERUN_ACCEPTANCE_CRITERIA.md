# Rerun Acceptance Criteria — `user-management-app` Fixtures

This is the business-approved acceptance test for the next architecture-discovery capability, agreed at the close of the Stage 2C cross-repository pilot. Once engineering improves architecture discovery (see [`user-management-app-pilot-report.md`](user-management-app-pilot-report.md)'s *Required Product Changes*), rerun the exact three preserved fixtures in [`fixtures/`](fixtures/) — unchanged — and evaluate against this criterion.

## Hard constraint on how this must be satisfied

**Do not "fix" the three pilot reports manually. Do not add special rules such as:**

```text
if Register.jsx changed → ...
if /refresh changed → ...
if user-management-app → ...
```

**That would make the experiment meaningless.** The goal is to improve the underlying, general-purpose discovery mechanism — route detection, service/component boundary discovery, dependency/call-relationship discovery — and then rerun these unchanged fixtures as a check on that general improvement, not to special-case these three specific files or this specific repository to pass.

## Acceptance criterion

```text
Change B: trivial frontend change (Register.jsx password confirmation)
→ low / appropriate impact
→ (this must remain true — it is already correct today; do not regress it)

Change C: cross-component contract break (/refresh header vs. cookie)
→ detects the affected components (both the changed backend route AND
  the frontend's dependency on its old contract)
→ recommends meaningful validation
→ does NOT look equivalent to Change B in the resulting report

Change A: API-layer caching/security change (protect() middleware)
→ continues to detect the caching/security concern
  (this already works today via diff-pattern scanning; a future version
  must not regress it while fixing the impact/dependency detection that
  currently fails around it)
```

The single most important pass/fail signal is the **B vs. C distinction**: today, both produce byte-for-byte identical `RISK`/`WHY`/`DECISION` sections. A future version passes this criterion only if a reader of the two reports, without prior knowledge of the codebase, can tell from the report alone that Change C is materially more consequential than Change B.

## Why this is the right test

Per the business record of this pilot: architecture discovery is now understood to be a separate capability from decision policy. The decision policy (never fabricate probability, never silently approve an unvalidated change) already generalized correctly across both `social-media-mini` and `user-management-app` and should not need to change again for this to pass. This criterion isolates and tests only the discovery layer that didn't generalize — improving it should not require touching `RiskAssessment`'s probability handling, the `ESCALATE`/`REQUIRE_ADDITIONAL_VALIDATION`/`ACCEPT` decision rules, or design8.md/design9.md.
