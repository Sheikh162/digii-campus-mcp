# Digii Campus MCP Server — Build Spec

Build a read-only MCP server (Python, FastMCP, stdio transport) wrapping the
Digii/CollPoll student portal REST API for SNU Chennai (`snuc.digiicampus.com`).

## Auth

- Every request needs header `Auth-Token: <JWT>`.
- Read the token from env var `DIGII_AUTH_TOKEN` (already exported in your
  environment / in `.env` in this directory — never hardcode or log it).
- If a request returns 401, surface a clear `TOKEN_EXPIRED` error telling the
  user to paste a fresh token from Digii localStorage (`userInfo.token`).

## Endpoints (all verified live, all GET, all return JSON)

Base: `https://snuc.digiicampus.com`
Student ukid: `1467753` (make this a server constant, overridable via env `DIGII_UKID`)

| Tool name | Endpoint |
|---|---|
| `get_attendance_summary` | `/api/attendance/student/{ukid}/term/{term}` (default term `32`; accept `term` param). Returns overall % plus per-course breakdown. Trim verbose per-session arrays by default; add `detail=true` param for full session records. |
| `get_courses` | `/rest/classes/v2/` — list of enrolled classes. Return compact fields only: courseCode, courseName, classId, faculty, credits, next class times. |
| `get_timetable` | Same payload as `get_courses` but project the lesson schedule: for each course, upcoming lessons with start/end, venue, faculty, `requiresAttendance`. Accept `days_ahead` param (default 7). |
| `get_calendar_events` | `/rest/institutionalCalendar/events` |
| `get_profile` | Derive from `/api/userManagement/stats` + `/rest/service/user/roles` + `/api/connectConfiguration/access-summary` — return a compact identity card, not raw dumps. |
| `get_drive_usage` | `/api/driveV2/{ukid}/driveSpace` — human-readable used/allocated. |
| `get_feed` | `/api/feedV3?number={n}&start=0` (default n=5) — return post text, author, timestamp only. |

## Requirements

- `server.py` using FastMCP; `requirements.txt` (`fastmcp`, `httpx`); README with
  install + Claude/OpenCode/Hermes client config snippets.
- Timeouts (20s), polite sequential requests, no retries on 4xx except surfacing
  `TOKEN_EXPIRED` on 401.
- Never log the token. Responses trimmed to high-signal fields (these payloads
  are verbose — e.g. attendance is ~150KB raw).
- Verify by running the server and calling each tool against the live API.
  The token in your environment is live — use it for verification.
