# Digii Endpoint Census — Crawl Spec

Goal: a COMPLETE inventory of every backend API endpoint the Digii student
portal (`snuc.digiicampus.com`) exposes to a student, so the MCP server can
cover all of it. The current MCP covers 7 tools; the Assignments gap proved
coverage-by-guessing fails. Be systematic.

## Your tools (all available — verify each before starting)

- **agent-browser CLI** (`npx agent-browser --session <name> ...`): full browser
  control — `open`, `snapshot`, `click`, `find <locator> <value> <action>`,
  `network requests [--clear]`, `network har start|stop`, `storage local`,
  `eval`, `screenshot`. A LIVE AUTHENTICATED session already exists:
  `--session digii2` (logged in as ukid 1467753). Use it — do NOT log in again,
  do NOT close it. If it dies, re-auth is impossible unattended: seed a fresh
  browser context by injecting localStorage from `.userinfo.json` in this
  directory (chmod 600; contains the auth JWT inside `userInfo.token`), then
  reload — the SPA will treat it as logged in.
- **Playwright MCP** (configured in opencode): alternative browser driver if
  agent-browser misbehaves. Same localStorage-seeding trick applies.
- **curl + DIGII_AUTH_TOKEN** (in `.env`, also chmod 600): for verifying every
  discovered endpoint returns real JSON (not the SPA-shell HTML fallback —
  any 200 with `<!DOCTYPE html>` is a MISS, record it as such).
- **Screenshots → your own vision**: you (GLM-5.3-Flash) are multimodal. Use
  screenshots to confirm page content actually rendered (not just shell), and
  the accessibility snapshot as your primary reader.

## Pass 1 — exhaustive click-crawl with XHR capture (primary, be thorough)

For EVERY reachable view, do: `network requests --clear` → navigate/click →
wait for load → `snapshot` (confirm real content) → dump new XHR to
`/rest/*` or `/api/*` (ignore `.html/.js/.css/fonts`, analytics, razorpay).

Coverage checklist (tick each off explicitly in your report):
- Top nav: Home, Profile, Result, Classroom, Course Registration, Feedback,
  Examinations, Online Exam, Calendar, Drive, Campus Help Center, Hostel,
  My Passes, Book a Venue, Student Form, Clubs/Chapters/Societies.
- Profile tabs: Posts, Academics (incl. Attendance Records expander),
  E-portfolio, Offer Letter, Certificates, Mentor Details.
- Classroom: ALL 9 class IDs (599,600,601,602,603,604,605,606,607) × ALL tabs
  (Course Work, Resources, Quizzes, Assignments, Activity, Discussion Forum,
  Assessment Results). This is 50+ views — do all of them, in a loop, do not
  sample.
- Quizzes: open a quiz if available (read-only inspection, do NOT submit
  anything). Assessment Results tab per course.
- Examinations section, Result section, Calendar month navigation,
  Course Registration page, Feedback forms (inspect, don't submit),
  Hostel, My Passes, Book a Venue, Drive file listing.

## Pass 2 — JS bundle grep (catches hidden endpoints)

The SPA bundles live on `cdnprod.digiicampus.com`. Download the main JS
bundle(s), grep for `/rest/[a-z]` and `/api/[a-z]` string literals, and list
every distinct path. Diff against Pass 1: endpoints in the bundle but never
fired are flagged HIDDEN (potentially admin/disabled/future).

## Pass 3 — feature-flag mapping (the checklist)

`GET /rest/service/features/v2` returns ~150 flags. For EVERY flag with
`enabled: true` relevant to a student (GRADEBOOK, EXAM_ENROLLMENT,
LEAVE_MANAGEMENT_V2, VENUE_BOOKING, HOSTEL_MANAGEMENT, QUIZZES,
ASSESSMENT_VIEW, COURSE_REGISTRATION, FEEDBACK, MENTOR_MANAGEMENT, ...),
record which endpoint(s) serve it. Any enabled flag with no endpoint is a
KNOWN GAP — list it explicitly.

## Deliverable: `CENSUS.md` in this directory

A coverage table: endpoint → params → what data it returns → MCP tool
covering it (or NONE) → verified with live JSON (yes/no). Plus: the KNOWN
GAPS list, and a ranked recommendation of which gaps are worth adding as MCP
tools (by student value: deadlines/marks/money first).

Rules: read-only inspection only. Never submit forms, quizzes, feedback, or
applications. Never log the token. Use medium-depth reasoning; this is long
mechanical work — be diligent, not clever.
