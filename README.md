# Digii Campus MCP Server

Read-only MCP server (Python + FastMCP, stdio transport) wrapping the
Digii/CollPoll student portal REST API — works for **any college** on the
Digii platform (`<your-college>.digiicampus.com`). Exposes attendance,
courses, timetable, calendar, profile, drive usage, the campus feed, mentor,
hostel, passes, notifications, help-centre requests and venue bookings as
trimmed, high-signal MCP tools — plus exactly ONE write: gated outpass filing
(`preview_outpass` + `create_outpass`, refused unless `confirmed=true`).

Coverage proof: CENSUS.md (86 endpoints mapped, 81 live-verified).
Gap analysis: GAPCLOSE.md (form schemas, submit targets, blocked families).

## Setup

One-liner (uvx, recommended) — no clone needed:

```bash
uvx digii-campus-mcp
```

Create a `.env` in your working directory (or export in your shell) as
below, and point your MCP client at the command above instead of a venv
path.

From source:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

```sh
DIGII_BASE_URL=https://<your-college>.digiicampus.com
DIGII_UKID=<your numeric student id>
DIGII_AUTH_TOKEN=<your JWT>
DIGII_TERM=32   # optional, current term id for attendance
```

### Getting the token and ukid

Log into your college portal in your browser. Your ukid is the number in your
profile URL (`/users/<ukid>/...`). For the token, open DevTools, then
Application, then Local Storage, and copy the `token` field inside `userInfo`
(the `user` cookie holds the same JWT). Tokens expire; when a call returns
`TOKEN_EXPIRED`, paste a fresh one. Never commit `.env`.

## Tools

| Tool | Description |
|---|---|
| `get_attendance_summary(term, detail=false)` | Overall attendance percent plus per-course and component breakdown. `detail=true` adds trimmed per-session records. |
| `get_courses()` | Enrolled courses: code, name, class, faculty, credits, next class times. |
| `get_timetable(days_ahead=7)` | Upcoming lessons over the next N days with start and end, venue, faculty, `requiresAttendance`. |
| `get_calendar_events()` | Institutional calendar events (holidays, fests). |
| `get_profile()` | Compact identity card (ukid, user type, tenant, pending stats). |
| `get_drive_usage()` | Human-readable drive used, free, allocated. |
| `get_feed(n=5)` | Latest campus feed posts: text, author, timestamp. |
| `get_assignments(class_id=None, page=1, per_page=10)` | Assignments per class (all classes when `class_id` omitted): draft, upcoming and previous counts, due dates, submission state. |
| `get_assignment(class_id, assignment_id)` | Full assignment detail: description, dates, submission state, grade fields, mark limits, submissions, resource file URLs. |
| `get_results(term_id=None)` | Without `term_id`: overall CGPA and percentage rollup plus all exam terms with declaration state. With `term_id` (the `examId`): per-course grades and marks for that term. |
| `get_class_assessments(class_id)` | Gradebook snapshot for a class: student identity plus published assessment component results and grades (empty until declared). |
| `get_mentor()` | Assigned faculty mentor: name, email, phone, department. |
| `get_hostel_summary(days=14)` | Allotment (hostel, room, status, dates) plus hostel attendance roll for the last N days plus profile hostel data. |
| `get_passes(page=1, per_page=10, include_fallback=true)` | My-passes console rows; when the console is empty, outpass history via the Campus Help Centre requests list as fallback. |
| `get_notifications(limit=10)` | List-only notification bell: unread count plus newest rows. **Never marks anything read** (see note). |
| `get_help_requests(request_id=None, page=1, per_page=10, include_services=true)` | Help-centre service catalogue plus paged request list; with `request_id`, full detail including form values and comments. |
| `get_venue_bookings(period="TODAY", page=1, size=12)` | Own venue bookings in the period window (TODAY, TOMORROW, NEXT_7_DAYS, PAST) plus student-bookable venue types. |
| `preview_outpass(service_id, out_date, out_time, return_date, return_time, description)` | **No-mutation preview**: builds the exact JSON that would be POSTed to `/api/chc/request/v2` (live form schema, values filled) with sanity checks and a human summary. |
| `create_outpass(... plus confirmed)` | **THE ONLY WRITE IN THIS SERVER.** Files the outpass via `POST /api/chc/request/v2` — refused with `CONFIRMATION_REQUIRED` (zero network activity) unless `confirmed` is literally `true`. Run `preview_outpass` with the same params first. Duplicate (HTTP 409) is surfaced as `DUPLICATE_REQUEST`. |

Auth: every request sends header `Auth-Token`. A 401 surfaces a
`TOKEN_EXPIRED` tool error instructing you to refresh the token. Requests are
sequential, 20s timeout, no retries on 4xx, and the token is never logged.

Safety envelope: mutations are limited to the outpass filing pair above.
`preview_outpass` performs GETs only (form schema) and never submits;
`create_outpass` refuses with no HTTP request at all unless `confirmed` is
literally `true`. `get_notifications` is list-only by design — the mark-read
endpoints (`PUT /rest/service/readNotificationObjects`, legacy
`POST /rest/feed/seenByUkid/v2`) are intentionally never called so unread
counts stay authoritative; no other tool writes anything.

### Mandatory client setup: per-tool approval (read this)

Eighteen tools in this server pour untrusted third-party text (feed posts,
assignment descriptions, notification content, help-desk comments) into your
agent's context. A crafted post could instruct the agent to file an outpass,
and the agent would supply `confirmed=true` itself. The server's confirmation
gate stops accidents; it cannot stop a manipulated agent, because the agent
is the party being asked to confirm — and a fraudulent outpass lands on a
real warden's desk under the student's name.

So: configure your MCP client to **auto-approve the 18 read tools and always
require human approval for `create_outpass`** (`preview_outpass` may stay
auto-approved; it performs no mutation). This is mandatory setup, not
optional hardening. Examples:

- Claude Code / OpenCode: add `create_outpass` to the ask/approval list
  (e.g. OpenCode `permission` rules), leave the rest allowed.
- Claude Desktop: set tools to ask-first where supported, or confirm the
  preview output in chat before any `create_outpass` call.
- Any client: never grant blanket write approval to this server; the only
  write it contains is the one that notifies a human authority.

Run locally for a smoke test:

```bash
source .venv/bin/activate
python3 verify.py        # live verification against your portal
python3 server.py        # stdio server
```

## Client configuration

Use your own paths. The server reads `.env` from its own directory, so no
secrets belong in client configs.

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "digii-campus": {
      "command": "/path/to/digii-mcp/.venv/bin/python",
      "args": ["/path/to/digii-mcp/server.py"]
    }
  }
}
```

### OpenCode (`opencode.json`)

```json
{
  "mcp": {
    "digii-campus": {
      "type": "local",
      "command": [
        "/path/to/digii-mcp/.venv/bin/python",
        "/path/to/digii-mcp/server.py"
      ],
      "enabled": true
    }
  }
}
```

### Hermes

```bash
hermes config set mcp_servers.digii-campus \
  '{"command": "/path/to/digii-mcp/.venv/bin/python",
    "args": ["/path/to/digii-mcp/server.py"],
    "timeout": 60}'
```

Restart the client after adding. Do not commit `.env` or any file
containing the token. See CONTRIBUTING.md to add your college's coverage.
