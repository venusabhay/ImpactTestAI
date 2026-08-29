# Preserved Validation Fixtures — `user-management-app` Pilot

These are the exact three changes analyzed in the [Stage 2C cross-repository pilot](../user-management-app-pilot-report.md), exported as patches so they survive independently of the local, unpushed experiment branches they were created on. Do not "fix" these to make a future run look better, and do not add repository- or file-specific special cases to the analyzer to pass them — see [RERUN_ACCEPTANCE_CRITERIA.md](../RERUN_ACCEPTANCE_CRITERIA.md) for why that would make the exercise meaningless.

## What each patch is

- `change-a-api-cache.patch` — adds a 5-second in-memory cache to `protect()` in `user-management-api/middleware/authMiddleware.js`. Mirrors the social-media-mini `/verify` caching change. Ground truth: real, non-trivial security-relevant risk (staleness/authorization-bypass), used by 4 of the API's 8 endpoints.
- `change-b-frontend-validation.patch` — adds client-side password-confirmation validation to `user-management-frontend/src/pages/Register.jsx`. Ground truth: trivial, low-risk, no backend implication.
- `change-c-cross-component-contract.patch` — changes `GET /refresh` in `user-management-api/routes/userRoutes.js` to read the refresh token from the `Authorization` header instead of the `jwt_refresh` cookie, without updating the frontend. Ground truth: a genuine, guaranteed, 100%-reproducible break of the token-refresh flow — the frontend (`user-management-frontend/src/utils/api.js`) still sends only a cookie on this call.

## How to reapply and rerun

```bash
# 1. Get a clean copy of user-management-app at its single baseline commit
git clone <user-management-app> /tmp/rerun-check
cd /tmp/rerun-check

# 2. Apply exactly one patch (each is independent -- do not apply more than one at a time)
git apply /path/to/change-a-api-cache.patch

# 3. Run the analyzer exactly as before
python3 /path/to/slice/analyze_change.py /tmp/rerun-check \
  --against main \
  --github-repo venusabhay/user-management-app \
  --npm-install \
  --out change-a-rerun-report.md
```

Repeat per patch, resetting (`git checkout -- .` or re-cloning) between runs.
