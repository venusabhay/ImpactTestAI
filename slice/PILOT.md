# Running the ImpactTestAI Pilot — Quickstart

You do not need to understand the architecture behind this tool to use it. This page is everything you need.

## What this does

You give it a repository and a change (a branch or a PR). It reads the repository, figures out what the change might affect, checks what evidence exists (tests, CI history), runs whatever real validation it can, and gives you back a plain-language report with a recommendation.

It never modifies your repository. It cannot fix anything, write code, commit, push, or merge. It reads, it validates where it can, and it reports.

## How to run it

1. Go to the **ImpactTestAI** repository on GitHub.
2. Click the **Actions** tab.
3. Select the **"Run Analysis (Pilot)"** workflow on the left.
4. Click **"Run workflow"** and fill in:

   | Field | What to put |
   | --- | --- |
   | `target_repo` | Your repository, as `owner/repo` (e.g. `team-a/payment-service`) |
   | `target_ref` | The change to analyze — a branch name, or `refs/pull/123/head` for PR #123 |
   | `base_ref` | What that change is proposed on top of (usually `main`) |

5. Click **Run workflow**.
6. When it finishes, open the run and download the artifact — named `run-<run-id>`, e.g. `run-20260828T221501Z-3f9a2c11`. It contains three files:
   - `report.md` — the human-readable report. Open it in any text editor, or paste it into GitHub/Slack — it's plain Markdown.
   - `audit.json` — the same information in a structured format, in case anyone wants to inspect it programmatically later.
   - `metadata.json` — a short summary (repository, exact commit analyzed, tool/policy version, decision, risk level) identifying exactly what this run was, for anyone tracking results across many runs.

   The report is also printed to the workflow run's summary page (along with the run ID), so you can often just read it there without downloading anything.

7. **Every run is kept, permanently, on its own** — running the analysis again (even against the exact same repository and commit) never replaces or overwrites a previous run's results. Each run gets its own unique run ID and its own artifact, so you can always go back and compare what the tool said at different points in time. This is worth knowing if you're re-running the same change after a discussion, or checking whether the tool is consistent.

That's it. No local setup, no cloning anything yourself, no command line required.

## What access it needs

- **Public repository:** nothing to set up. It just works.
- **Private repository:** an administrator of the ImpactTestAI repository needs to add one secret, once:
  - Name: `TARGET_REPO_TOKEN`
  - Value: a GitHub personal access token (classic or fine-grained) with **read-only** access to your repository — specifically:
    - Contents: read
    - Actions: read (this is what lets it look at your CI history)
    - Pull requests: read (only needed if you plan to pass a PR ref)
  - **Do not** grant write access to anything. The tool never needs it and will never use it.

If that secret isn't set, the pilot still works for any public repository — it just can't check out private ones.

## What you'll get back

The report answers, in order:

1. What changed
2. What it might affect, and why (with the actual evidence — file names, line numbers)
3. How risky it looks, and how confident the tool actually is (it will tell you outright when it doesn't know something — see below)
4. What CI history says about this area of the code, if any exists
5. What validation it recommends, and why
6. Whether that validation actually ran, and what happened
7. A final recommendation: **proceed**, **need more validation first**, or **escalate to a human** (this last one means: don't proceed without someone looking at it)
8. What it explicitly does *not* know (production usage, historical incidents, etc.) — it will never guess at these

## Important things to know before you run it

- **It only knows what's in your repository.** It has no access to your production systems, your incident history, or your business context unless that's written down in the repo itself. Where it doesn't know something, it says `UNKNOWN` — it never invents a number to fill the gap.
- **It executes your repository's own `npm install`/`npm test`.** Only run this against a repository you'd already trust to run its own CI pipeline — this tool doesn't do anything your CI doesn't already do, but it's worth saying plainly.
- **It discovers your repository's structure from evidence, not a fixed layout**: any directory with a `package.json` is treated as a component, and any `receiver.method(path, ...)` call (`app.get(...)`, `router.post(...)`, `fastify.get(...)`, or any other identifier) is treated as a route registration, regardless of formatting. It has been proven against several real, differently-structured Node.js/Express-style repositories (Express, Koa, Fastify). It is still Node.js/Express-style-convention specific: a repository using a fundamentally different registration style (e.g. NestJS's decorator routing, Fastify's config-object `.route(...)` convention, or a non-Node language) will honestly report that it found no route-level evidence rather than guess — **that's exactly the kind of thing we want to hear about as pilot feedback**, not something to work around quietly.
- **A recommendation of "escalate" or "need more validation" is not a failure of the tool.** It means the tool found something it couldn't confidently clear on its own. That's the intended behavior, not a bug to report.

## We're not trying to prove this is perfect

This is a pilot. We specifically do not want you to hold back a critical opinion because a report looked impressive or because it recommended something inconvenient. If it asked for validation that felt unnecessary, or missed something your normal process would have caught, that's exactly what we need to know — see the feedback template.

## Giving feedback

After you've run it against a few real changes, please fill out [`PILOT_FEEDBACK_TEMPLATE.md`](PILOT_FEEDBACK_TEMPLATE.md) and send it back. Plain business language is exactly what's wanted — you don't need to evaluate it technically.

## If something goes wrong

If the workflow run fails outright (not just "escalate" — an actual red X), that's a bug in the tool, not in your repository. Send us the workflow run link and, if you can, the specific `target_repo`/`target_ref`/`base_ref` you used.
