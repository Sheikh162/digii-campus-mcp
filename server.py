"""Digii Campus MCP Server (CollPoll/Digii student portal, any college).

Wraps the Digii student-portal REST API behind MCP tools: mostly
read-only, plus exactly ONE write — gated outpass filing (preview_outpass /
create_outpass) guarded behind a mandatory `confirmed=true` flag. Everything
else performs no mutation: notifications are list-only (never marked read),
passes/hostel/mentor/help/venue tools are GETs only.
Auth is a JWT passed via the DIGII_AUTH_TOKEN env var (never logged or
hardcoded). Configure your college + student identity with:
  DIGII_BASE_URL  e.g. https://snuc.digiicampus.com (no default college)
  DIGII_UKID      your numeric student id (ukid)
  DIGII_TERM      current term id for attendance (optional, default 32)
See .env.example. Coverage proof: CENSUS.md. Gap analysis: GAPCLOSE.md.
"""

import base64
import json
import os

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

TIMEOUT = 20.0


def _load_dotenv() -> None:
    """Minimal .env loader: fills os.environ only for keys not already set."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, ".env")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("'\"")
            os.environ.setdefault(key, value)


_load_dotenv()

BASE_URL = os.environ.get("DIGII_BASE_URL", "").rstrip("/")
DEFAULT_TERM = int(os.environ.get("DIGII_TERM", "32"))
UKID = int(os.environ.get("DIGII_UKID", "0") or 0)
TOKEN = os.environ.get("DIGII_AUTH_TOKEN", "")

if not BASE_URL:
    raise RuntimeError(
        "DIGII_BASE_URL is not set. Copy .env.example to .env and set "
        "DIGII_BASE_URL (e.g. https://snuc.digiicampus.com), DIGII_UKID, "
        "and DIGII_AUTH_TOKEN."
    )
if not UKID:
    raise RuntimeError(
        "DIGII_UKID is not set. Copy .env.example to .env and set your "
        "numeric student id (ukid)."
    )

mcp = FastMCP("digii-campus")


def _decode_jwt_payload(token: str) -> dict:
    """Decode (unverified) the payload segment of a JWT for identity claims."""
    try:
        seg = token.split(".")[1]
        seg += "=" * (-len(seg) % 4)
        return json.loads(base64.urlsafe_b64decode(seg))
    except Exception:
        return {}


def _get(path: str, params: dict | None = None) -> httpx.Response:
    """GET a JSON endpoint with the Auth-Token header. Raises TOKEN_EXPIRED on 401."""
    headers = {"Auth-Token": TOKEN, "Accept": "application/json"}
    resp = httpx.get(
        BASE_URL + path,
        params=params,
        headers=headers,
        timeout=TIMEOUT,
        follow_redirects=True,
    )
    if resp.status_code in (401, 403):
        raise ToolError(_token_expired_msg(resp.status_code))
    if resp.status_code == 500 and not TOKEN:
        # This API answers 500 (empty body) instead of 401 on a missing token.
        raise ToolError(_token_expired_msg(500))
    resp.raise_for_status()
    return resp


def _json(path: str, params: dict | None = None):
    resp = _get(path, params)
    if resp.status_code == 204 or not resp.content.strip():
        return None
    return resp.json()


def _fmt_bytes(n: float | int | None) -> str:
    if n is None:
        return "unknown"
    n = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} TiB"


def _course_faculty_names(entry: dict, lessons: list[dict]) -> list[str]:
    names: list[str] = []
    for lesson in lessons or []:
        for f in lesson.get("facultyList") or []:
            nm = f.get("facultyName")
            if nm and nm not in names:
                names.append(nm)
    return names


def _trim_course(entry: dict) -> dict:
    """Compact view of one entry from /rest/classes/v2/."""
    lessons = entry.get("lessonsConducted") or []
    class_list = entry.get("classes") or []
    # course-level code/credits are often null; fall back to classList payload
    code = entry.get("courseCode")
    credits = entry.get("courseCredits")
    comp = entry.get("courseComponentName")
    for cl in entry.get("classList") or []:
        if code is None and cl.get("courseCode"):
            code = cl.get("courseCode")
        if credits is None and cl.get("courseCredits") is not None:
            credits = cl.get("courseCredits")
        if comp is None and cl.get("courseComponentName"):
            comp = cl.get("courseComponentName")
    return {
        "courseId": entry.get("courseId"),
        "classId": entry.get("classId"),
        "courseCode": code,
        "courseName": entry.get("courseName"),
        "className": entry.get("className"),
        "credits": credits,
        "faculty": _course_faculty_names(entry, lessons),
        "nextClassStart": entry.get("nextClassStart"),
        "nextClassEnd": entry.get("nextClassEnd"),
    }


def _trim_attendance_stats(stats: dict) -> dict:
    return {
        "present": stats.get("totalPresent"),
        "absent": stats.get("totalAbsent"),
        "doNotConsider": stats.get("totalDoNotConsiderForAttendance"),
        "totalClasses": stats.get("totalClasses"),
        "percentage": round(stats["percentage"], 2) if stats.get("percentage") is not None else None,
        "approvedLeaves": stats.get("approvedLeaves"),
        "unapprovedLeaves": stats.get("unapprovedLeaves"),
    }


def _trim_session_record(rec: dict) -> dict:
    return {
        "status": rec.get("finalStatus") or rec.get("status"),
        "lessonStart": rec.get("lessonStartTime"),
        "lessonEnd": rec.get("lessonEndTime"),
        "markedAt": rec.get("attendanceTimestamp")
        or rec.get("updatedTimestamp"),
    }


@mcp.tool
def get_attendance_summary(term: int = DEFAULT_TERM, detail: bool = False) -> str:
    """Overall attendance percentage plus a per-course breakdown (counts and %).

    Args:
        term: Digii term id (default 32 = current semester).
        detail: If true, also include trimmed per-session records
            (status + lesson times) for each course component.
    """
    data = _json(f"/api/attendance/student/{UKID}/term/{term}") or {}
    out: dict = {"termId": data.get("termId", term)}
    out.update(_trim_attendance_stats(data))
    courses = []
    for ca in data.get("courseAttendance") or []:
        comp_view = []
        for comp in ca.get("components") or []:
            cv = _trim_attendance_stats({k: comp.get(k) for k in
                ("totalPresent", "totalAbsent", "totalDoNotConsiderForAttendance",
                 "totalClasses", "percentage", "approvedLeaves", "unapprovedLeaves")})
            cv.update({
                "componentType": comp.get("courseComponentTypeName"),
                "courseCode": comp.get("courseCode"),
                "className": comp.get("className"),
                "startDate": comp.get("startDate"),
                "endDate": comp.get("endDate"),
            })
            if detail:
                cv["sessions"] = [
                    _trim_session_record(r) for r in (comp.get("attendance") or [])
                ]
            comp_view.append(cv)
        courses.append({
            "courseId": ca.get("courseId"),
            "courseName": ca.get("courseName"),
            "credits": ca.get("courseCredits"),
            "overall": _trim_attendance_stats(ca),
            "components": comp_view,
        })
    out["courses"] = courses
    return json.dumps(out, indent=1)


@mcp.tool
def get_courses() -> str:
    """Enrolled courses with compact fields (code, name, class, faculty, credits,
    next class times)."""
    entries = _json("/rest/classes/v2/") or []
    trimmed = [_trim_course(e) for e in entries]
    return json.dumps(trimmed, indent=1)


@mcp.tool
def get_timetable(days_ahead: int = 7) -> str:
    """Upcoming scheduled lessons across all enrolled courses within the next
    `days_ahead` days (start/end, venue, faculty, requiresAttendance, status)."""
    import datetime as _dt

    today = _dt.date.today()
    horizon = today + _dt.timedelta(days=days_ahead)
    entries = _json("/rest/classes/v2/") or []
    by_course: dict[int, dict] = {}
    for entry in entries:
        code = entry.get("courseCode")
        for cl in entry.get("classList") or []:
            if code is None and cl.get("courseCode"):
                code = cl.get("courseCode")
        lessons = []
        for lesson in entry.get("lessonsConducted") or []:
            start = lesson.get("start") or ""
            day = start[:10]
            if not day:
                continue
            try:
                lday = _dt.date.fromisoformat(day)
            except ValueError:
                continue
            if not (today <= lday <= horizon):
                continue
            faculty = [f.get("facultyName") for f in (lesson.get("facultyList") or [])
                       if f.get("facultyName")]
            lessons.append({
                "start": lesson.get("start"),
                "end": lesson.get("end"),
                "venue": lesson.get("venue") or lesson.get("room"),
                "faculty": faculty,
                "requiresAttendance": lesson.get("requiresAttendance"),
                "isCancelled": lesson.get("isCancelled"),
                "recurrence": lesson.get("recurrence"),
            })
        if lessons:
            by_course[entry.get("classId")] = {
                "courseId": entry.get("courseId"),
                "courseCode": code,
                "courseName": entry.get("courseName"),
                "lessons": sorted(lessons, key=lambda l: l["start"] or ""),
            }
    out = {
        "window": {"from": str(today), "to": str(horizon)},
        "courses": sorted(by_course.values(), key=lambda c: (c["lessons"][0]["start"] or "")),
    }
    return json.dumps(out, indent=1)


@mcp.tool
def get_calendar_events() -> str:
    """Institutional calendar events (holidays, fests, exams) for SNU Chennai."""
    events = _json("/rest/institutionalCalendar/events") or []
    trimmed = [{
        "id": e.get("id"),
        "name": e.get("name"),
        "type": e.get("type"),
        "starts": e.get("starts"),
        "ends": e.get("ends"),
        "startTime": e.get("startTime"),
        "endTime": e.get("endTime"),
        "relatedTo": e.get("relatedTo"),
    } for e in events]
    return json.dumps(trimmed, indent=1)


@mcp.tool
def get_profile() -> str:
    """Compact identity card for the authenticated student (ukid, user type,
    tenant/college, pending stats)."""
    token_claims = _decode_jwt_payload(TOKEN)
    stats = _json("/api/userManagement/stats") or {}
    roles = _json("/rest/service/user/roles")
    access = _json("/api/connectConfiguration/access-summary") or {}
    card = {
        "ukid": token_claims.get("ukid", UKID),
        "userType": token_claims.get("userType"),
        "tenant": token_claims.get("tenantName"),
        "institutionUrl": token_claims.get("institutionUrl"),
        "stats": stats,
        "roles": roles or [],
        "access": {
            "canSearchAny": access.get("canSearchAny"),
            "canMessageAny": access.get("canMessageAny"),
        },
    }
    return json.dumps(card, indent=1)


@mcp.tool
def get_drive_usage() -> str:
    """Human-readable drive storage usage: used vs allocated (and free)."""
    data = _json(f"/api/driveV2/{UKID}/driveSpace") or {}
    used = data.get("used") or 0.0
    allocated = data.get("allocated")
    available = data.get("available")
    free = None
    if allocated is not None and available is not None:
        free = float(available)
    elif allocated is not None:
        free = float(allocated) - used
    out = {
        "used": _fmt_bytes(used),
        "free": _fmt_bytes(free),
        "allocated": _fmt_bytes(allocated),
        "raw": {"used": data.get("used"), "available": data.get("available"),
                "allocated": allocated},
    }
    return json.dumps(out, indent=1)


def _trim_assignment(a: dict) -> dict:
    return {
        "id": a.get("id"),
        "classId": a.get("classId"),
        "name": a.get("name"),
        "description": a.get("description"),
        "startDate": a.get("startDate"),
        "dueDate": a.get("dueDate"),
        "dueDatePassed": a.get("dueDatePassed"),
        "submissionType": a.get("submissionType"),
        "isSubmitted": a.get("isSubmitted"),
        "submittedOn": a.get("submittedOn"),
        "isGraded": a.get("isGraded"),
        "grade": a.get("grade"),
    }


@mcp.tool
def get_assignments(class_id: int | None = None, page: int = 1, per_page: int = 10) -> str:
    """Assignments across enrolled classes (or one class): draft/upcoming/previous
    buckets with due dates and submission state.

    Args:
        class_id: Restrict to one class id (omit for all 9 enrolled classes).
        page: 1-based page per class (server default 1).
        per_page: Assignments per page per class (server default 10).
    """
    classes = _json("/rest/classes/v1/classroom") or []
    if class_id is not None:
        classes = [c for c in classes if c.get("id") == class_id]
        if not classes:
            raise ToolError(f"CLASS_NOT_FOUND: no enrolled class with id {class_id}.")
    out = []
    for c in classes:
        cid = c.get("id")
        entry: dict = {
            "classId": cid,
            "courseCode": c.get("courseCode"),
            "courseName": c.get("courseName"),
            "className": c.get("className"),
        }
        try:
            data = _json(f"/rest/classes/{cid}/users/{UKID}/assignments",
                         params={"page": page, "perPage": per_page}) or {}
        except ToolError as exc:
            if str(exc).startswith("TOKEN_EXPIRED"):
                raise
            entry["error"] = "not accessible (rejected, HTTP 401/403)"
            out.append(entry)
            continue
        entry["totalDraftAssignments"] = data.get("totalDraftAssignments")
        entry["totalUpcomingAssignments"] = data.get("totalUpcomingAssignments")
        entry["totalPreviousAssignments"] = data.get("totalPreviousAssignments")
        res = data.get("res") or {}
        for bucket in ("draftAssignments", "upcomingAssignments", "previousAssignments"):
            entry[bucket] = [
                {**_trim_assignment(a), "className": res.get("className")}
                for a in (res.get(bucket) or [])
            ]
        out.append(entry)
    return json.dumps(out, indent=1)


@mcp.tool
def get_assignment(class_id: int, assignment_id: int) -> str:
    """Full detail for one assignment: description, start/due dates, submission
    state, grade fields, mark limits, student submissions and resource files."""
    d = _json("/rest/assignments/v1/getStudentAssignmentDetails",
              params={"assignmentId": assignment_id, "classId": class_id}) or {}
    if not d.get("id"):
        raise ToolError(
            f"NOT_FOUND: assignment {assignment_id} in class {class_id} returned no data."
        )
    out = {
        "id": d.get("id"),
        "classId": d.get("classId"),
        "className": d.get("className"),
        "sectionName": d.get("sectionName"),
        "name": d.get("name"),
        "description": d.get("description"),
        "type": d.get("type"),
        "submissionType": d.get("submissionType"),
        "startDate": d.get("startDate"),
        "dueDate": d.get("dueDate"),
        "dueDatePassed": d.get("dueDatePassed"),
        "isSubmitted": d.get("isSubmitted"),
        "submittedOn": d.get("submittedOn"),
        "showGrade": d.get("showGrade"),
        "grade": d.get("grade"),
        "isAssignmentGraded": d.get("isAssignmentGraded"),
        "hasFacultyEvaluated": d.get("hasFacultyEvaluated"),
        "maximumMarks": d.get("maximumMarks"),
        "minimumMarks": d.get("minimumMarks"),
        "questionnaireId": d.get("questionnaireId"),
        "submissions": [
            {
                "id": s.get("id"),
                "submittedOn": s.get("submittedOn"),
                "status": s.get("status"),
                "mediaName": s.get("mediaName"),
                "grade": s.get("grade"),
            }
            for s in (d.get("submissions") or [])
        ],
        "resources": [
            {
                "id": r.get("id"),
                "mediaName": r.get("mediaName"),
                "mediaType": r.get("mediaType"),
                "mediaUrl": r.get("mediaUrl"),
            }
            for r in (d.get("resources") or [])
        ],
    }
    return json.dumps(out, indent=1)


@mcp.tool
def get_results(term_id: int | None = None) -> str:
    """Semester results: overall CGPA/percentage rollup + every exam term with
    declaration state (omit term_id), or per-term course grades (with term_id).

    Args:
        term_id: Exam term id (the `examId` from the terms overview, e.g. 5 =
            BTech AY 2023-24 Sem 1) to fetch per-course grades for. Undeclared
            terms still return course rows with null grades.
    """
    if term_id is None:
        data = _json(f"/api/v2/resultDeclaration/student/terms/{UKID}") or {}
        out = {
            "overallCgpa": data.get("overallCgpa"),
            "minorCgpa": data.get("minorCgpa"),
            "overallPercentage": data.get("overallPercentage"),
            "minorPercentage": data.get("minorPercentage"),
            "division": data.get("division"),
            "creditsEarned": data.get("creditsEarned"),
            "totalCredits": data.get("totalCredits"),
            "hasAnyDeclaredResult": data.get("hasAnyDeclaredResult"),
            "terms": [
                {
                    "examId": t.get("examId"),
                    "termId": t.get("termId"),
                    "examName": t.get("examName"),
                    "termName": t.get("termName"),
                    "isRegularDeclared": t.get("isRegularDeclared"),
                    "isBacklogDeclared": t.get("isBacklogDeclared"),
                    "sgpa": t.get("sgpa"),
                    "termCgpa": t.get("termCgpa"),
                    "termPercentage": t.get("termPercentage"),
                    "termDivision": t.get("termDivision"),
                    "termObtainedMarks": t.get("termObtainedMarks"),
                    "termTotalMarks": t.get("termTotalMarks"),
                }
                for t in (data.get("terms") or [])
            ],
        }
        return json.dumps(out, indent=1)
    data = _json(f"/api/v2/resultDeclaration/student/term/{term_id}/{UKID}") or {}
    out = {
        "examId": data.get("examId"),
        "termId": data.get("termId"),
        "examName": data.get("examName"),
        "termName": data.get("termName"),
        "isRegularDeclared": data.get("isRegularDeclared"),
        "isBacklogDeclared": data.get("isBacklogDeclared"),
        "sgpa": data.get("sgpa"),
        "termCgpa": data.get("termCgpa"),
        "termPercentage": data.get("termPercentage"),
        "termDivision": data.get("termDivision"),
        "termRemark": data.get("termRemark"),
        "termObtainedMarks": data.get("termObtainedMarks"),
        "termTotalMarks": data.get("termTotalMarks"),
        "courses": [
            {
                "courseCode": c.get("courseCode"),
                "courseName": c.get("courseName"),
                "courseCredits": c.get("courseCredits"),
                "finalGrade": c.get("finalGrade"),
                "grade": c.get("grade"),
                "gradePoint": c.get("gradePoint"),
                "marks": c.get("marks"),
                "totalMarks": c.get("totalMarks"),
                "hasFailed": c.get("hasFailed"),
                "enrollmentStatus": c.get("enrollmentStatus"),
            }
            for c in (data.get("courses") or [])
        ],
    }
    return json.dumps(out, indent=1)


@mcp.tool
def get_class_assessments(class_id: int) -> str:
    """Gradebook snapshot for one class: the student's assessment component
    results and grades as published (empty when nothing is declared yet)."""
    d = _json("/rest/gradebook/v2/assessmentResult", params={"classId": class_id}) or {}
    if not d:
        raise ToolError(f"NO_DATA: no gradebook record for class {class_id}.")
    student = d.get("student") or {}
    result = d.get("result") or {}
    out = {
        "classId": class_id,
        "student": {
            "ukid": student.get("ukid"),
            "name": student.get("name"),
            "registrationId": student.get("registrationId"),
            "programmeName": student.get("programmeName"),
            "sectionName": student.get("sectionName"),
        },
        "grades": d.get("grades") or [],
        "assessmentComponentResults": [
            {
                "assessmentId": r.get("assessmentId"),
                "componentId": r.get("componentId"),
                "assessmentName": r.get("assessmentName") or r.get("name"),
                "value": r.get("value"),
                "maximumMarks": r.get("maximumMarks"),
                "passingMarks": r.get("passingMarks"),
                "publishTimeStamp": r.get("publishTimeStamp"),
            }
            for r in (d.get("assessmentComponentResults") or [])
        ],
        "result": {
            "maximumMarks": result.get("maximumMarks"),
            "value": result.get("value"),
            "publishMarks": result.get("publishMarks"),
            "publishTimeStamp": result.get("publishTimeStamp"),
        },
    }
    return json.dumps(out, indent=1)


@mcp.tool
def get_feed(n: int = 5) -> str:
    """Latest posts from the campus feed: text, author, timestamp (and booth,
    category)."""
    n = max(1, min(int(n), 25))
    data = _json("/api/feedV3", params={"number": n, "start": 0}) or {}
    posts = data.get("res") or []
    trimmed = []
    for p in posts[:n]:
        try:
            obj = json.loads(p.get("object")) if isinstance(p.get("object"), str) else (p.get("object") or {})
        except Exception:
            obj = {}
        text = obj.get("text") if obj else None
        if not text:
            text = p.get("postText") or p.get("text")
        trimmed.append({
            "id": p.get("id") or obj.get("id"),
            "author": obj.get("postedByName"),
            "authorType": obj.get("postedByType"),
            "timestamp": obj.get("postedTime") or p.get("postedOn"),
            "booth": obj.get("boothName"),
            "category": obj.get("category"),
            "hasAttachment": bool(obj.get("hasAttachment")),
            "text": text,
        })
    return json.dumps(trimmed, indent=1)


def _post_json(path: str, payload: dict) -> httpx.Response:
    """POST a JSON body with the Auth-Token header (gated write use only).

    Mirrors _get()'s TOKEN_EXPIRED mapping; 40x handling is left to the caller
    (the only consumer is create_outpass, which maps 409/400 itself).
    """
    headers = {"Auth-Token": TOKEN, "Accept": "application/json",
               "Content-Type": "application/json"}
    resp = httpx.post(
        BASE_URL + path,
        json=payload,
        headers=headers,
        timeout=TIMEOUT,
        follow_redirects=True,
    )
    if resp.status_code in (401, 403):
        raise ToolError(_token_expired_msg(resp.status_code))
    if resp.status_code == 500 and not TOKEN:
        raise ToolError(_token_expired_msg(500))
    return resp


def _token_expired_msg(status: int) -> str:
    return (
        "TOKEN_EXPIRED: The Digii auth token was rejected "
        f"(HTTP {status}). Get a fresh token: log into "
        "your college portal (<your-college>.digiicampus.com) in your browser, "
        "open DevTools > Application > Local Storage, copy the token inside "
        "userInfo (or the user cookie value), and update DIGII_AUTH_TOKEN "
        "in your .env."
    )


# -------------------------------------------------------------------
# Batch A read tools (mentor, hostel, passes, notifications, CHC, venue)
# -------------------------------------------------------------------

# Notifications mutation policy (DO NOT REMOVE): this server is read-only.
# `PUT /rest/service/readNotificationObjects` ({notificationObjectIds:[…]}) and
# the legacy `POST /rest/feed/seenByUkid/v2` both mark notifications as read
# server-side. GET /rest/service/notifications is intentionally the ONLY
# notifications call we make: every `seen:false` row is a live unread signal
# and the unread count below must keep working across calls; also these are
# the only two write endpoints in the notifications family and firing them
# would consume the user's own notification state from under the app.
@mcp.tool
def get_notifications(limit: int = 10) -> str:
    """Campus notification bell, list-only: unread count + latest rows.

    NOT mutations are performed: notifications are never marked as seen
    (see the policy comment in server.py's implementation for why).

    Args:
        limit: How many of the newest notifications to include (max 50).
    """
    limit = max(1, min(int(limit), 50))
    data = _json("/rest/service/notifications") or {}
    rows = data.get("res") or []
    unread = sum(1 for r in rows if not r.get("seen"))
    trimmed = [{
        "notificationObjectId": r.get("notificationObjectId"),
        "type": r.get("type"),
        "content": r.get("content") or r.get("object"),
        "time": r.get("time"),
        "displayTime": r.get("displayTime"),
        "seen": r.get("seen"),
        "objectType": r.get("objectType"),
        "objectId": r.get("objectId"),
        "parentObjectId": r.get("parentObjectId"),
    } for r in rows[:limit]]
    out = {
        "unreadCount": unread,
        "totalCount": len(rows),
        "shown": len(trimmed),
        "note": "list-only; nothing was marked read",
        "notifications": trimmed,
    }
    return json.dumps(out, indent=1)


@mcp.tool
def get_mentor() -> str:
    """Assigned faculty mentor: name/salutation, contact, department."""
    rows = _json(f"/api/mentorManagement/mentee/mentor/{UKID}") or []
    mentors = [{
        "ukid": m.get("ukid"),
        "name": f"{m.get('salutation') or ''} {m.get('name') or ''}".strip(),
        "email": m.get("email"),
        "phone": m.get("phone"),
        "departmentName": m.get("departmentName"),
        "designationName": m.get("designationName"),
        "registrationId": m.get("registrationId"),
        "photo": m.get("photo"),
    } for m in rows]
    return json.dumps(mentors, indent=1)


@mcp.tool
def get_hostel_summary(days: int = 14) -> str:
    """Hostel snapshot: allotment (hostel/room/status/dates), hostel attendance
    roll for the last `days` days (yes/no per date), and profile hostel data."""
    days = max(1, min(int(days), 31))
    d = _json("/rest/hostel/attendance/current",
              params={"currentPage": 1, "perPage": days}) or {}
    allottee = d.get("allotteeDetails") or {}
    counts: dict[str, int] = {}
    for r in d.get("attendanceDetails") or []:
        st = r.get("attendanceStatus") or "NOT_MARKED"
        counts[st] = counts.get(st, 0) + 1
    # profile-side hostel data (may be empty; tolerate 404)
    profile = None
    try:
        profile = _json(f"/rest/service/users/{UKID}/hostelData")
    except ToolError as exc:
        if str(exc).startswith("TOKEN_EXPIRED"):
            raise
    out = {
        "allotment": {
            "hostel": allottee.get("hostelName"),
            "room": allottee.get("roomNum"),
            "status": allottee.get("status"),
            "startDate": allottee.get("allotmentStartDate"),
            "endDate": allottee.get("allotmentEndDate"),
            "floor": allottee.get("floorName"),
            "bed": allottee.get("bedName"),
        },
        "attendanceWindow": {
            "days": days,
            "markedCounts": counts,
            "dates": [
                {
                    "date": r.get("attendanceForDate"),
                    "status": r.get("attendanceStatus") or "NOT_MARKED",
                    "markedTime": r.get("attendanceMarkedTime"),
                }
                for r in (d.get("attendanceDetails") or [])
            ],
        },
        "profileHostelData": profile,
    }
    return json.dumps(out, indent=1)


_PASS_KEYS = (
    "id", "passId", "requestId", "type", "passType", "status", "statusId",
    "fromDate", "toDate", "outDate", "returnDate", "reason",
    "visitingPlace", "place", "createdOn", "lastUpdatedOn",
    "approvalStatus", "approverName", "active", "passNumber", "gatewayPass",
)


def _trim_pass_row(row: dict) -> dict:
    hit = {k: row[k] for k in _PASS_KEYS if row.get(k) is not None}
    if hit:
        return hit
    # unknown shape: keep the first scalar fields defensively
    scal = {}
    for k, v in row.items():
        if isinstance(v, (str, int, float, bool)):
            scal[k] = v
        if len(scal) >= 14:
            break
    return scal


@mcp.tool
def get_passes(page: int = 1, per_page: int = 10, include_fallback: bool = True) -> str:
    """My-passes console: own pass requests (paged) + hostel identity, plus, when
    the pass console has no rows, the help-centre outpass requests as fallback.

    Args:
        page: 1-based page in the pass console.
        per_page: Rows per page (max 25).
        include_fallback: When the console is empty, also list "Campus Help
            Centre requests (outpass services)" as fallback (the same passes
            filed via CHC).
    """
    per_page = max(1, min(int(per_page), 25))
    d = _json("/api/access/passConsole/user/requests",
              params={"page": page, "perPage": per_page}) or {}
    user = d.get("user") or {}
    hostel = d.get("hostelDetails") or {}
    rows = d.get("data") or []
    out: dict = {
        "hosteller": user.get("accommodationType"),
        "hostel": {"name": hostel.get("hostelName") or hostel.get("currentHostelName"),
                   "room": hostel.get("room") or hostel.get("currentRoomName")},
        "totalCount": d.get("totalCount"),
        "page": page,
        "passes": [_trim_pass_row(r) for r in rows],
    }
    if not rows and include_fallback:
        # pass console empty -> the outpasses were filed through the Campus
        # Help Centre; surface those requests as the pass history.
        try:
            chc = _json("/rest/campusHelpCentre/requests/v2",
                        params={"currentPage": page, "perPage": per_page}) or {}
            reqs = chc.get("requests") or []
            out["fallbackSource"] = "rest/campusHelpCentre/requests/v2"
            out["fallbackRequests"] = [{
                "requestId": r.get("requestId"),
                "service": r.get("serviceTitle"),
                "serviceId": r.get("serviceId"),
                "status": r.get("requestStatus"),
                "actionTaken": r.get("actionTakenName"),
                "actionType": r.get("actionType"),
                "createdOn": r.get("createdOn"),
                "lastUpdatedOn": r.get("lastUpdatedOn"),
            } for r in reqs]
        except ToolError as exc:
            if str(exc).startswith("TOKEN_EXPIRED"):
                raise
            out["fallbackRequests"] = [{"error": "fallback unavailable"}]
    return json.dumps(out, indent=1)


@mcp.tool
def get_help_requests(request_id: int | None = None, page: int = 1,
                      per_page: int = 10, include_services: bool = True) -> str:
    """Campus Help Centre: requestable services + my help requests (paged);
    with `request_id`, full detail for ONE request incl. form values and comments.

    Args:
        request_id: A `requestId` (from this tool or get_passes) to fetch detail
            for — overrides the list view.
        page: 1-based page of the request list.
        per_page: Requests per page (max 25).
        include_services: Include the service catalogue (requestable services)
            in the list view.
    """
    per_page = max(1, min(int(per_page), 25))
    if request_id is not None:
        d = _json(f"/rest/campusHelpCentre/requests/{request_id}/v3") or {}
        if not isinstance(d, dict) or not (d.get("requestId") or d.get("serviceTitle")):
            raise ToolError(f"NOT_FOUND: help request {request_id} returned no data.")
        creator = d.get("createdBy") or {}
        out = {
            "requestId": d.get("requestId"),
            "serviceTitle": d.get("serviceTitle"),
            "status": d.get("requestStatus"),
            "actionTaken": d.get("actionTaken"),
            "actionNote": d.get("actionNote"),
            "createdOn": d.get("createdOn"),
            "lastUpdatedOn": d.get("lastUpdatedOn"),
            "assignedTo": d.get("assignedTo"),
            "createdBy": {"ukid": creator.get("ukid"), "name": creator.get("name")},
            "formValues": [
                {"label": f.get("label"), "value": f.get("value"),
                 "sequence": f.get("sequence")}
                for f in (d.get("formDetails") or [])
            ],
        }
        try:
            comments = _json(f"/rest/campusHelpCentre/requests/{request_id}/comments",
                             params={"start": 0, "number": 25}) or []
            picked = []
            for c in comments:
                picked.append({
                    k: c.get(k) for k in
                    ("name", "authorName", "senderName", "ukid", "comment",
                     "text", "content", "createdOn", "timestamp")
                    if c.get(k) is not None
                } or c)
            out["comments"] = picked
        except ToolError as exc:
            if str(exc).startswith("TOKEN_EXPIRED"):
                raise
            out["comments"] = []
        return json.dumps(out, indent=1)

    out: dict = {}
    if include_services:
        services = _json("/rest/campusHelpCentre/services/v3") or []
        out["services"] = [{
            "serviceId": s.get("service", {}).get("id"),
            "title": s.get("service", {}).get("title"),
            "description": s.get("service", {}).get("description"),
            "paid": s.get("service", {}).get("paid"),
            "amount": s.get("service", {}).get("amount"),
            "serviceDesk": (s.get("serviceDesks") or [{}])[0].get("title"),
        } for s in services]
    data = _json("/rest/campusHelpCentre/requests/v2",
                 params={"currentPage": page, "perPage": per_page}) or {}
    reqs = data.get("requests") or []
    out["page"] = page
    out["requests"] = [{
        "requestId": r.get("requestId"),
        "service": r.get("serviceTitle"),
        "serviceId": r.get("serviceId"),
        "status": r.get("requestStatus"),
        "workcentre": r.get("workcentreName"),
        "actionTaken": r.get("actionTakenName"),
        "actionType": r.get("actionType"),
        "createdOn": r.get("createdOn"),
        "lastUpdatedOn": r.get("lastUpdatedOn"),
    } for r in reqs]
    return json.dumps(out, indent=1)


@mcp.tool
def get_venue_bookings(period: str = "TODAY", page: int = 1, size: int = 12) -> str:
    """My venue bookings (Book-a-Venue): self bookings in the selected period
    window, plus the infrastructure types a student may book direct.

    Args:
        period: TODAY | TOMORROW | NEXT_7_DAYS | PAST (server date-window).
        page: 1-based page.
        size: Rows per page (max 25).
    """
    import datetime as _dt

    period = str(period).upper()
    size = max(1, min(int(size), 25))
    today = _dt.date.today()
    fmt = "%Y-%m-%d %H:%M:%S"
    per: dict[str, tuple[_dt.date, _dt.date]] = {
        "TODAY": (today, today),
        "TOMORROW": (today + _dt.timedelta(days=1), today + _dt.timedelta(days=1)),
        "NEXT_7_DAYS": (today, today + _dt.timedelta(days=7)),
        "PAST": (today - _dt.timedelta(days=365), today - _dt.timedelta(days=1)),
    }
    if period not in per:
        raise ToolError("BAD_PERIOD: period must be one of TODAY, TOMORROW, "
                        "NEXT_7_DAYS, PAST.")
    f, t = per[period]
    params = {
        "page": page, "size": size, "period": period,
        "startDatetime": f.strftime(fmt),
        "endDatetime": t.strftime("%Y-%m-%d") + " 23:59:59",
    }
    d = _json("/api/venue-booking/bookings/self", params=params) or {}
    types = _json("/api/venue-booking/bookings/infrastructure-types",
                  params={"bookingType": "DIRECT"}) or []
    out = {
        "period": period,
        "window": {"from": f.isoformat(), "to": t.isoformat()},
        "totalCount": d.get("totalCount"),
        "page": page,
        "bookings": d.get("data") or [],
        "bookableTypes": [{
            "id": t.get("id"), "type": t.get("type"),
            "singleBookingType": t.get("singleBookingType"),
        } for t in types],
    }
    return json.dumps(out, indent=1)


# -------------------------------------------------------------------
# Gated outpass filing (the ONLY write in this server)
# -------------------------------------------------------------------

_DATE_LEN = 10


def _norm_time(t: str) -> str:
    """Normalize 'HH:MM' -> 'HH:MM:00'; thousands of forms send seconds."""
    t = (t or "").strip()
    parts = t.split(":")
    if len(parts) == 2:
        parts.append("00")
    if len(parts) != 3:
        raise ToolError(f"BAD_TIME: '{t}' is not a valid time (use HH:MM or HH:MM:SS).")
    try:
        h, m, s = (int(p) for p in parts)
    except ValueError:
        raise ToolError(f"BAD_TIME: '{t}' is not a valid time (use HH:MM or HH:MM:SS).")
    if not (0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60):
        raise ToolError(f"BAD_TIME: '{t}' is out of range.")
    return f"{h:02d}:{m:02d}:{s:02d}"


def _norm_date(d: str) -> str:
    import datetime as _dt
    d = (d or "").strip()
    try:
        return _dt.date.fromisoformat(d[:_DATE_LEN]).isoformat()
    except ValueError:
        raise ToolError(f"BAD_DATE: '{d}' is not a valid date (use YYYY-MM-DD).")


def _fetch_outpass_form(service_id: int) -> dict:
    form = _json(f"/rest/campusHelpCentre/services/{service_id}/formDetails")
    if not form or not form.get("formDetails"):
        raise ToolError(
            f"NOT_FOUND: service {service_id} has no form schema "
            "(check the serviceId — list them with get_help_requests).")
    return form


def _build_outpass_payload(
    service_id: int,
    out_date: str, out_time: str,
    return_date: str, return_time: str,
    description: str,
) -> tuple[dict, dict, dict]:
    """Fetch the live form schema and produce the EXACT POST /api/chc/request/v2
    body (GAPCLOSE.md §1 shape). Returns (payload, form, checks)."""
    import datetime as _dt

    form = _fetch_outpass_form(service_id)
    if not all([out_date, out_time, return_date, return_time]):
        raise ToolError("MISSING_PARAM: out_date, out_time, return_date and "
                        "return_time are all required.")
    description = (description or "").strip()
    if not description:
        descnames = ", ".join(
            f.get("name") for f in form["formDetails"] if f.get("isEditable"))
        raise ToolError(f"MISSING_PARAM: description is required "
                        f"(mandatory editable field: {descnames or 'n/a'}).")

    out_date, return_date = _norm_date(out_date), _norm_date(return_date)
    out_time, return_time = _norm_time(out_time), _norm_time(return_time)

    if out_date > return_date:
        raise ToolError("BAD_RANGE: return_date must not precede out_date.")

    checks: dict = {"ok": [], "warnings": []}
    checks["ok"].append(f"description filled ({len(description)} chars)")
    checks["ok"].append(f"window {out_date} {out_time} -> {return_date} {return_time}")

    # verbatim copies of the live schema, values filled per ui conventions
    form_details = json.loads(json.dumps(form["formDetails"]))
    date_ranges = json.loads(json.dumps(form["dateRangeDetails"] or []))

    editable = [f for f in form_details if f.get("isEditable")]
    if not editable:
        raise ToolError("FORM_ERROR: no editable free-text field on this form — "
                        "cannot file via MCP.")
    desc_field = editable[0]
    desc_field["value"] = description

    filled = {"START": {}, "END": {}}
    for row in date_ranges:
        dt = row.get("dateTimeType")
        if dt == "START":
            row["value"] = out_date if row.get("element") == "date" else out_time
            filled["START"][row.get("name")] = row["value"]
        elif dt == "END":
            row["value"] = return_date if row.get("element") == "date" else return_time
            filled["END"][row.get("name")] = row["value"]

    # form-enforced constraints surfaced from the live schema
    start_rows = [r for r in date_ranges if r.get("dateTimeType") == "START"]
    end_rows = [r for r in date_ranges if r.get("dateTimeType") == "END"]
    end_max_days = next(
        (r.get("endMaxDays") for r in start_rows if r.get("endMaxDays")), None)
    if end_max_days is not None:
        delta = (_dt.date.fromisoformat(return_date)
                 - _dt.date.fromisoformat(out_date)).days
        if delta > int(end_max_days):
            raise ToolError(
                f"RANGE_TOO_LONG: this service caps return at {end_max_days} day(s) "
                f"after out_date (you asked for {delta}).")
    for r in start_rows + end_rows:
        if r.get("maxTime") and r.get("value"):
            if r["value"] > r["maxTime"]:
                checks["warnings"].append(
                    f"{r.get('name')}={r['value']} is later than form maxTime "
                    f"{r['maxTime']} — warden side may reject.")

    attachments = form.get("attachmentDetails") or []
    if any(a.get("mandatory") for a in attachments):
        checks["warnings"].append(
            "this service requires attachments, which MCP cannot upload — "
            "filing may fail or the request may lack required documents.")

    payload = {
        "serviceId": service_id,
        "formDetails": form_details,
        "dateRangeDetails": date_ranges,
        "attachmentDetails": [],
        "slotDetails": [],
    }
    checks["ok"].append("payload matches POST /api/chc/request/v2 shape "
                        "(GAPCLOSE.md §1)")
    return payload, form, checks


@mcp.tool
def preview_outpass(service_id: int = 18, out_date: str = "", out_time: str = "",
                    return_date: str = "", return_time: str = "",
                    description: str = "") -> str:
    """PREVIEW ONLY (no mutation): build the EXACT JSON that create_outpass
    would POST to /api/chc/request/v2 for an outpass request and show it with
    a human summary. Nothing is sent to the campus API.

    Args:
        service_id: Help-centre service id (18 = Hostel Day Outpass - Gents).
        out_date: YYYY-MM-DD.
        out_time: HH:MM or HH:MM:SS (form caps the out time for some services).
        return_date: YYYY-MM-DD.
        return_time: HH:MM or HH:MM:SS.
        description: Reason for the pass (the form's mandatory editable field).
    """
    payload, form, checks = _build_outpass_payload(
        service_id, out_date, out_time, return_date, return_time, description)
    dr = {row.get("name"): row.get("value") for row in payload["dateRangeDetails"]}
    human = (f"Outpass '{form.get('serviceName')}' (service {service_id}): "
             f"out {dr.get('Out Date', '')} {dr.get('Out Time', '')}, "
             f"return {dr.get('Return Date', '')} {dr.get('Return Time', '')}; "
             f"description: {description!r}. "
             + ("; ".join(checks["warnings"]) if checks["warnings"] else
                "no warnings."))
    out = {
        "note": "PREVIEW ONLY — no data was sent. Review `payload`, then call "
                "create_outpass with the SAME params and confirmed=true.",
        "wouldPOST": "/api/chc/request/v2",
        "serviceName": form.get("serviceName"),
        "serviceId": service_id,
        "checks": checks,
        "filled": {
            "description": description,
            "dateRange": dr,
            "autoFields": {f.get("name"): f.get("value")
                           for f in payload["formDetails"] if not f.get("isEditable")},
        },
        "payload": payload,
        "summary": human,
    }
    return json.dumps(out, indent=1)


@mcp.tool
def create_outpass(service_id: int = 18, out_date: str = "", out_time: str = "",
                   return_date: str = "", return_time: str = "",
                   description: str = "", confirmed: bool = False) -> str:
    """File an outpass request via POST /api/chc/request/v2. HARDC GATE:

    confirmed MUST literally be true. If it is not true, the tool refuses
    without touching the network — run preview_outpass with the SAME params
    first, review the payload, then call this with confirmed=true.

    Args:
        service_id: Help-centre service id (18 = Hostel Day Outpass - Gents).
        out_date: YYYY-MM-DD.
        out_time: HH:MM or HH:MM:SS.
        return_date: YYYY-MM-DD.
        return_time: HH:MM or HH:MM:SS.
        description: Reason for the pass (mandatory on the form).
        confirmed: Must literally be true to allow the POST. No other value
            (false, "true", 1 with cute casing, etc.) will ever work.
    """
    if confirmed is not True:
        raise ToolError(
            "CONFIRMATION_REQUIRED: create_outpass refuses to file anything "
            "unless confirmed is literally true. Run preview_outpass with the "
            "same (service_id, out_date, out_time, return_date, return_time, "
            "description) first, review its `payload`, then call "
            "create_outpass(..., confirmed=true).")
    payload, form, _checks = _build_outpass_payload(
        service_id, out_date, out_time, return_date, return_time, description)
    resp = _post_json("/api/chc/request/v2", payload)
    if resp.status_code == 409:
        raise ToolError(
            "DUPLICATE_REQUEST: the campus API rejected this as a duplicate "
            "(HTTP 409 — a request already exists for this service/period). "
            "Nothing new was filed; check existing requests with get_help_requests.")
    if resp.status_code == 400:
        try:
            msg = resp.json().get("message")
        except Exception:
            msg = None
        raise ToolError(f"BAD_REQUEST: {msg or resp.text[:300]} — nothing was filed.")
    resp.raise_for_status()
    body = {}
    if resp.content.strip():
        try:
            body = resp.json()
        except Exception:
            body = {}
    paid = bool(body.get("paid"))
    out = {
        "requestId": body.get("requestId") or body.get("id"),
        "status": "PAID_PENDING_PAYMENT" if paid and not body.get("requestId")
                  else "SUBMITTED",
        "paid": paid,
        "orderId": body.get("orderId"),
        "serviceId": service_id,
        "serviceName": form.get("serviceName"),
        "window": {"out": f"{out_date} {out_time}",
                   "return": f"{return_date} {return_time}"},
        "note": "request filed; verify it with get_help_requests",
        "raw": body,
    }
    return json.dumps(out, indent=1)


if __name__ == "__main__":
    mcp.run()  # stdio transport
