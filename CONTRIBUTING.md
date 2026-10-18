# Contributing

This server targets every college on the Digii/CollPoll platform. The REST
contract (`/rest/...`, `/api/...`) is Digii-wide; what varies per college is
the subdomain, the auth provider, the enabled feature flags, and student ids.
All of that lives in `.env` — no college-specific code should be needed, but
coverage must be verified per college.

## Adding your college (no code)

1. Copy `.env.example` to `.env`; set `DIGII_BASE_URL`, `DIGII_UKID`,
   `DIGII_AUTH_TOKEN` (README has the how).
2. Run `python3 verify.py`. Every `OK` line is a tool proven live against
   your portal.
3. Report back: which tools return `OK`, which return `TOKEN_EXPIRED`
   (auth issue, not a bug), which return 403 (your role is gated — e.g. fees
   are payer-linked at most colleges), and which return empty (no live data,
   e.g. no quizzes this term).

## Extending coverage (the census method)

Guessing endpoint paths fails (the SPA serves its HTML shell with HTTP 200
for unknown paths, so a 200 proves nothing). The method that produced
CENSUS.md:

1. **Click-crawl with XHR capture.** Drive the portal in a browser with
   network logging: for every nav item, every tab, every course, clear the
   log, click, wait, dump new XHR to `/rest/*` or `/api/*`. Anything the UI
   shows, the API serves — complete by construction for visible features.
   Drive every form to its final pre-submit state and capture the schema
   GETs; never click submit — find the POST target in the JS bundle instead.
2. **Bundle grep.** The SPA bundles on `cdnprod.digiicampus.com` contain
   every API path string. Diff bundle literals against fired XHR: unfired
   paths are hidden, admin, disabled, or future surface.
3. **Feature-flag mapping.** `GET /rest/service/features/v2` is the app's
   own feature inventory. Every enabled student flag should map to at least
   one endpoint and one tool; unmapped flags are tracked as known gaps.

Then add a row per endpoint to the coverage table (endpoint, params, data
returned, covering tool or NONE, live-verified yes or no) and rank missing
tools by student value: deadlines first, then marks, then money.

## Rules

- Read-only inspection by default. The only write in this server is the
  confirmation-gated outpass pair; any new write tool must follow the same
  preview-plus-explicit-confirm pattern and be covered by a refusal-path
  test in `verify.py` that fires zero network writes.
- Never commit `.env`, tokens, ukids, or personal data. Census captures
  must be scrubbed of identifiers before submitting.
- `verify.py` must pass end to end before any PR: every tool live-called,
  every gate refusal-pathed.
