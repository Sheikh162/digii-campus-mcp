# Digii Endpoint Census — CENSUS.md
Generated: 2026-10-18 · Example values from SNU Chennai (ukid, names, rooms below are the author's own; replace with yours).

Infrastructure note: API base is `https://snuc.digiicampus.com`, auth header is **`Auth-Token: <JWT>`**
(NOT `Authorization: Bearer` — Bearer returns 401). Unauthenticated JSON errors use the same shape as app errors
(`{"timestamp","status","error","message","path"}`), so verify auth by 200-with-data, not merely 200.

---

## 0. Tool verification (start of run)

| Tool | Status |
|---|---|
| agent-browser session `digii2` | ✅ alive & authenticated (snapshot showed logged-in user). Broken once mid-run by bot-protection after a rapid 9-class crawl loop (sign-in page appeared). Recovered per spec: `agent-browser storage local set userInfo "$(cat .userinfo.json)"` + reload → app treated it as logged in. ✅ recovered. |
| Playwright MCP | ✅ reachable (25 tools, incl. `browser_network_requests`). Its own browser instance is logged out; usable as capture fallback only after localStorage seeding (not needed). |
| curl + DIGII_AUTH_TOKEN | ✅ works with `Auth-Token` header → `GET /rest/service/features/v2` → 200, real JSON (207 flags). `Bearer` header = 401. |
| agent-browser `network har` | ❌ broken (records 0 requests). Used `network requests` instead (cumulative per session; dedupe offline). |

Rule note on pacing: every top-nav click does a full page load (the app is /V2/#/... routed but external hash-set triggers reload); per-page XHR captured via `network requests`, diffed globally.

---

## 1. Pass 1 coverage checklist (exhaustive click-crawl)

Top nav (all 16 crawled; ✅ = fired data endpoints, snapshot-confirmed rendered):
- ✅ Home (feed) · ✅ Profile · ✅ Result · ✅ Classroom · ✅ Course Registration
- ✅ Feedback · ✅ Examinations · ✅ Online Exam · ✅ Calendar · ✅ Drive
- ✅ Campus Help Center · ✅ Hostel · ✅ My Passes · ✅ Book a Venue · ✅ Student Form
- ✅ Clubs, Chapters & Societies

Profile tabs (clicked each, XHR captured):
- ✅ Posts · ✅ Academics (incl. "Attendance Records" expander — expands UI, uses already-loaded data, no extra XHR)
- ✅ E-portfolio · ✅ Offer Letter · ✅ Certificates · ✅ Mentor Details

Classroom: 9 class IDs mapped via `rest/classes/v1/classroom` →
599 BM4001 · 600 CS4001 · 601 CS4005 · 602 CS4663 · 603 HS4001 · 604 CS4852 · 605 CS4999 · 606 CS4003 (DevOps) · 607 CS4801
- ✅ Opened **all 9**: `rest/classes/{id}/users/1467753/assignments`, `.../lessons`, `classPermission/{id}`, `classroom/quizzes/v1/?classId={id}`, `gradebook/v2/assessmentResult?classId={id}`, `classroomDiscussions/?classId={id}` fired for each accessible class.
- ❌ **607 (CS4801) not accessible**: `rest/classes/classPermission/607` → **401** (redirects to home; student not enrolled). NOT a coverage miss.
- ✅ **606 tab crawl in V2 view** (drawer: Course Work / Resources / Quizzes / Assignments / Activity / Discussion Forum / Assessment Results — all clicked, XHR diffed; only V2-specific endpoints were new: `classroomV2/class/606/module`, `classroomV2/class/606/sessions/{id}`, `api/nomenclature/labels`; other tabs reuse load-time data).
- ✅ Assignments drill-in: opened "CIA 2 - CI/CD Pipeline using AWS" (#/classroom/606/student/assignment/846) → **`rest/assignments/v1/getStudentAssignmentDetails?assignmentId={id}&classId={id}`** — this was THE gap that motivated the spec.
- Quizzes: `classroom/quizzes/v1/?classId=` returns an error-envelope/empty for all 9 classes (no quizzes active this term). No quiz to open (read-only, none submitted). Quiz-taking endpoints (bundle) flagged HIDDEN below.
- Extra data page found in the classroom hamburger menu: **Course Attendance** (`/profile/{ukid}/attendance`), **Academic Fee** `/studentFees/details`, **Wallet** `/wallet`, **Invoices And Credit Notes** `/invoiceAndCreditNote` — crawled as bonus.

Other interactions (all read-only; nothing submitted):
- ✅ Result term nav (`/api/v2/resultDeclaration/student/term/{termId}/{ukid}`, terms list available)
- ✅ Calendar next-month → same `lessons` endpoint with new `from`/`to` (7-day window, tz +05:30)
- ✅ Course Registration wizard rendered (Step 1-4); table headers only — **no active sessions** for this student
- ✅ Feedback → "No Active Feedback Sessions Found" (list errors/empty)
- ✅ Campus Help Center → request list (3 real outpass requests), request detail `/helpCenter/request/{id}` — *Pass 4 (GAPCLOSE.md §1): New Request fully driven to pre-submit for service 18 (formDetails schema live; submit `POST /api/chc/request/v2` decoded from bundle, never clicked).*
- ✅ Hostel → attendance table (allotment record with room and date range)
- ✅ My Passes → accommodation card (hosteller status, Cancel Pass disabled), history "No data"
- ✅ Book a Venue → Today/Tomorrow/Later/Past tabs (param variants) + infrastructure types — *Pass 4 (GAPCLOSE.md §2): "New Booking" driven to pre-submit Step 2/3 (venue inventory + admin steps 403 for student; submit `POST /api/venue-booking/bookings` payload decoded from bundle, never clicked).*
- ✅ Drive → file listing rendered; folder "Courses" opened → `drive/folder?folderId={id}`
- ✅ Clubs → no memberships + "View All" empty (college has none in `/api/v1/ccs?archived=false&page=0&pageSize=12`)
- ⚠️→✅ Notifications bell → data endpoint captured (`rest/service/notifications` + full row schema closed in Pass 4, GAPCLOSE.md §8); intentionally did NOT open individual notifications (mark-read `PUT rest/service/readNotificationObjects` = mutation, identified from bundle, never fired).

---

## 2. Verified live-JSON endpoint table

Legend: **MCP**: current server.py tool covering it (get_attendance_summary, get_courses, get_timetable, get_calendar_events, get_profile, get_drive_usage, get_feed, get_assignments, get_assignment, get_results, get_class_assessments, get_mentor, get_hostel_summary, get_passes, get_notifications, get_help_requests, get_venue_bookings, preview_outpass/create_outpass) or **NONE**. "✅ curl" = GET'd directly, real JSON data (not the SPA HTML shell / not just an error envelope). Codes noted where ≠200.

### Classroom / academics (core student value)
| Endpoint (template) | Params | Returns | MCP | curl ✅ |
|---|---|---|---|---|
| GET `/rest/classes/v1/classroom` | — | all 9 enrolled classes (id, code, name, type) | get_courses | ✅ 200 |
| GET `/rest/classes/v2/` | — | 500 KB class master data | get_courses (partially) | ✅ 200 (non-JSON-stream) |
| GET `/rest/classes/{classId}/users/{ukid}/assignments` | classId, ukid, (opt `page`,`perPage`) | assignments: draft/upcoming counts, due dates, submission state | get_assignments | ✅ 200 (4591B) |
| GET `/rest/assignments/v1/getStudentAssignmentDetails` | assignmentId, classId | full assignment: title, description, start/due date, submissionType, isSubmitted, grade, resources (media URLs) | get_assignment | ✅ 200 (assignment 846) |
| GET `/rest/classes/{classId}/users/{ukid}/lessons` | classId, ukid | coursework/lesson calendar data (53 KB for 606) | get_courses (partially) | ✅ 200 |
| GET `/rest/classes/v2/lessons` | classIds (repeatable), from, to | class timetable; calendar `(2026-09-27…11-08)` window | get_timetable | ✅ 200 (23 KB) |
| GET `/rest/classes/{classId}` | classId | class detail `{res}` | NONE | ✅ 200 |
| GET `/rest/classes/classPermission/{classId}` | classId | permission flags `{res}` | NONE | ✅ 200 |
| GET `/rest/classes/v1/students/{classId}` | classId | roster (student self → 400 wrong-mode in browser) | NONE | ✅ 200 but error-envelope |
| GET `/rest/classroomV2/class/{classId}/module` | classId | 5 classroom modules | NONE | ✅ 200 |
| GET `/rest/classroomV2/class/{classId}/sessions/{sessionId}` | classId, sessionId | lesson/session + faculty + slot detail | get_timetable (partially) | ✅ 200 |
| GET `/rest/classroom/quizzes/v1/` | classId | quiz list — **400/empty this term** | NONE | ✅ 200 error-envelope |
| GET `/rest/classroomDiscussions/` | classId, page, perPage, searchKey, sortBy | threads + canUserCreateDiscussionForum | NONE | ✅ 200 |
| GET `/rest/gradebook/v2/assessmentResult` | classId | per-student assessment result record (name/rollNo base here; marks rows when declared) | get_class_assessments | ✅ 200 |

### Result / exams
| Endpoint | Params | Returns | MCP | curl |
|---|---|---|---|---|
| GET `/api/v2/resultDeclaration/student/terms/{ukid}` | ukid | overallCGPA, minorCGPA, overallPercentage, division, creditsEarned + terms | get_results | ✅ 200 (3 KB) |
| GET `/api/v2/resultDeclaration/student/term/{termId}/{ukid}` | termId(=5), ukid | per-term declared exams, subject grades | get_results(term_id) | ✅ 200 (10 KB) |
| GET `/api/ems/enrollment/session/student/registration/` | — | 4 exam-enrollment session metadata | NONE | ✅ 1404B |
| GET `/api/ems/enrollment/session/student/registration/{id}` | id(=3) | per-session enrollment | NONE | ✅ 200 (empty list) |
| GET `/rest/ems/student/assessments` | — | previous/today/upcoming assessments (Online Exam page) | NONE | ✅ 105B |

### Attendance
| Endpoint | Params | Returns | MCP | curl |
|---|---|---|---|---|
| GET `/api/attendance/student/{ukid}/term/{termId}` | ukid, termId(=32) | **149 KB**: totalPresent/Absent/percentage per course + approvedLeaves | get_attendance_summary | ✅ 200 |
| GET `/api/attendance/status` | — | 6 status rows | get_attendance_summary | ✅ 200 |
| GET `/api/attendance/settings` | — | participation % rules | NONE | ✅ 200 |
| GET `/api/terms/programmeBatchTerms` | batch(=2023), programme(=3) | term list (termId 32 etc.) | (used internally) | ✅ 200 |

### Profile / mentor / certificates
| Endpoint | Params | Returns | MCP | curl |
|---|---|---|---|---|
| GET `/api/userManagement/basicDetails` | — | ukid, name, profilePic, userType | get_profile | ✅ 200 |
| GET `/api/offerLetter/student` | — | offer letter — error envelope (no data) | NONE | ✅ 200(err) |
| GET `/api/certificates/published/{ukid}` | ukid | published certificates (empty) | NONE | ✅ 200 ([]) |
| GET `/api/mentorManagement/mentee/mentor/{ukid}` | ukid | mentor (1940B, 1 record) | get_mentor | ✅ 200 |
| GET `/rest/users/{ukid}/profile/personalDetails` | ukid | name, email, phone, DOB, socials | get_profile | ✅ 200 |
| GET `/rest/users/{ukid}/profile/{education,skills,projects,awards,certifications,workExperience,languageList,interestedIndustries,interestedProfessions}` | ukid | e-portfolio (all empty/[]; languageList = 507 languages) | get_profile (name only) | ✅ 200 |
| GET `/rest/service/users/{ukid}/{hostelData,researchData}` | ukid | hostel/research profile data (empty; `hostelData` returned an empty body 2026-10-18) | get_hostel_summary (profileHostelData) | ✅ 200/[] |

### Campus life / admin consoles
| Endpoint | Params | Returns | MCP | curl |
|---|---|---|---|---|
| GET `/rest/institutionalCalendar/events` | — | 6 institutional events | get_calendar_events | ✅ 200 |
| GET `/rest/service/colleges/workingHours` | — | working hours | NONE | ✅ 200 |
| GET `/rest/service/users/{ukid}/drive` (+`drive/folder?folderId=`) | ukid, folderId | Drive files (32 KB tree) | get_drive_usage | ✅ 200 |
| GET `/api/driveV2/{ukid}/driveSpace` | ukid | used/available/allocated | get_drive_usage | ✅ 200 |
| GET `/rest/hostel/attendance/current` | currentPage, perPage | allottee + hostel attendance days | get_hostel_summary | ✅ 200 (3.7 KB) |
| GET `/api/access/passConsole/user/requests` | page, perPage | pass requests (hostel outpass console) | get_passes (+ CHC requests/v2 fallback when console empty) | ✅ 200 (2.8 KB, totalCount present) |
| GET `/api/venue-booking/bookings/infrastructure-types` | — | types (1 = classroom) | NONE | ✅ 200 |
| GET `/api/venue-booking/bookings/self` | page, size, startDatetime, endDatetime, period(TODAY/PAST/TOMORROW/NEXT_7_DAYS) | own bookings `{totalCount,data}` | get_venue_bookings | ✅ 200 (0) |
| GET `/api/v1/ccs/my` · `/api/v1/ccs` | archived, page, pageSize | clubs membership/directory (empty) | NONE | ✅ 200 ([]) |
| GET `/rest/campusHelpCentre/services/v3` | includeMiddlewareService | 7 requestable services | get_help_requests (services block) | ✅ 200 (7.7 KB) |
| GET `/rest/campusHelpCentre/requests/v2` | currentPage, perPage | my requests (10 as of 2026-10-18) | get_help_requests (list; get_passes fallback source) | ✅ 200 |
| GET `/rest/campusHelpCentre/requests/{id}/v3` + `/comments?start=0&number=` | requestId | detail + comments | get_help_requests(request_id) | ✅ 200 |
| GET `/api/chc/request/settings` · `/api/chc/middleware/service?action=` | action | request settings/middleware | NONE | ✅ 200 |
| GET `/rest/admission/userrecords/{ukid}` · `actionStatuses?ukid=` | ukid | Student Form console data | NONE | ✅ 200 |
| GET `/rest/structure/v1/departmentsHierarchy` | — | department tree | NONE | ✅ 200 |

### Feed / platform plumbing
| Endpoint | Params | Returns | MCP | curl |
|---|---|---|---|---|
| GET `/api/feedV3` | number(=20), start | home feed | get_feed | ✅ 200 (12 KB) |
| POST `/rest/service/getMyPosts`, `getFeed` | body | feed posts | get_feed | browser 200 |
| GET `/rest/service/notifications` | — | notifications (4.7 KB) | get_notifications (list-only, unread count; mark-read never fired — see below) | ✅ 200 |
| POST `/rest/feed/seenByUkid/v2` | body | mark seen (**mutation — not replayed via curl**) | NONE | browser 200 |
| GET `/rest/service/cards`, `externalLinks`, `collegeConfig?url=`, `features/v2`, `user/roles`(204), websocket `getWebsocketUrl` | — | shell config / flags | NONE | ✅ 200 |

### Fees (money) — ⛔ blocked for this account
| Endpoint | Params | Returns | MCP | curl |
|---|---|---|---|---|
| GET `/rest/fees/studentFees/details`, `/rest/fees/configuration` | — | **403 Forbidden** | NONE | ✅ 403 |
| GET `/api/finance/v2/gst/userDetails?entity=STUDENT_FEE` | studentUkid, pageNumber | **403** | NONE | ✅ 403 |
| wallet `/wallet`, `/feeconsole`, `/invoiceAndCreditNote` pages | — | no new data endpoints fired; fee API family is account-restricted | NONE | — |

### 400/401 (documented, not coverage failures)
- `/rest/classes/classPermission/607` → 401 (class 607 CS4801 not accessible/enrollable)
- `/api/feedback/student/sessions` (browser 400; curl 200 error-envelope) — no active sessions
- `/api/studentCourseRegistration/sessions?activeSessions=false&…` — same (no registrations)
- `/api/offerLetter/student` — no offer letter on file
- endpoints returning Spring error envelopes still carry `path` info; treat `{"status":404/400}` bodies as EMPTY, not data.

---

## 3. Pass 2 — JS bundle grep

Bundle: `https://cdnprod.digiicampus.com/V2/20261016164843/assets/index-BovLCzws.js` (18.9 MB, single main bundle).
- Distinct `/api|/rest` literals: **328** (vs 86 endpoint templates actually fired by the student UI).
- All 328 paths: `bundle_paths.txt`; flagged HIDDEN (in bundle, never fired): `hidden.txt` (317).

Student-relevant HIDDEN endpoints (flagged, ordered by likely student value):
1. `/rest/assignments/v1/getStudentAssignmentDetails` — ✅ resolved & verified live (needs assignmentId+classId from list endpoint; assignments list itself IS fired).
2. `/api/classroomV2/quizQuestionnaire/student` (`/result`, `/group`, `quiz/evaluation`) — quiz-taking payload endpoints — *Pass 4 (GAPCLOSE.md §4): student list GET live-verified 200-empty; full attempt/response/submit lifecycle + `uzt` payload decoded (class `w2a`)*.
3. `/api/ems/student/attempt` (+`/attempt/`) — online exam attempt lifecycle — *Pass 4 (GAPCLOSE.md §5): decoded from bundle (class `Its`, builder `nqt`, `X-Current-URL` header); `GET …/attempt/questions/1` live-probed → 400 "Invalid assessment id" (reachable, data-gated)*.
4. `/api/academicFee/v2/student`, `/…/payment`, `/…/instalmentPlan`, `/api/dues/v2/studentManagement/*` — fee/dues self-service (all fee UI 403 for this account: parent-linked payment needed).
5. `/api/v1/mentor/{requests,conversations,feedback,memories,terms}` — mentor hub v1 — *Pass 4 (GAPCLOSE.md §6): CLOSED — real gateway is `aimentor.digiicampus.com` (Bearer + X-College-ID), 5 GETs live-verified 200*.
6. `/api/gradebookStatus(/assessmentStatus)` — quiz/assessment status rollups — *Pass 4 (GAPCLOSE.md §7): CLOSED — live 200 array of 5 status rows; faculty write side decoded*.
7. `/rest/ems/student/assessments/` + `/rest/ems/student/answerSheet/` — per-assessment fallback/answer sheets.
8. Everything else (admin/faculty/accounting/asset/SSO...) — out of student scope.

Diff verdict: NO student-reachable feature in the bundle is missing from Pass 1 except the quiz-money-mentor families above (disabled by data/flags, not by miss).

## 4. Pass 3 — feature flags (207 total; 67 enabled)

Full enabled list: `enabled_flags.txt` (67). Mapping of student-relevant enabled flags → serving endpoints:

| Flag (enabled) | Serving endpoint(s) found | Status |
|---|---|---|
| ATTENDANCE_VIEW / ATTENDANCE_EXCEPTION / ATTENDANCE_NOTIFICATION | `api/attendance/student/{ukid}/term/{term}` (+settings/status, chc middleware) | ✅ covered |
| ASSESSMENT_VIEW / GRADEBOOK / ASSIGNMENT_GRADEBOOK_MARKS | `rest/gradebook/v2/assessmentResult?classId=`, `assignments`, getStudentAssignmentDetails, resultDeclaration | ✅ covered |
| CLASSROOM / CLASSROOM_V2 / CURRICULUM_V2 | classes/*, classroomV2/* | ✅ covered |
| CLASSROOM_QUIZ_V2 / TIMED_CLASSROOM_QUIZ / CLASSROOM_GROUP_QUIZ / CLASSROOM_QUIZ_ACCESS_CODE | `rest/classroom/quizzes/v1/?classId=` (400/empty) + HIDDEN quizQuestionnaire endpoints | ⚠️ list now live-verified (200 empty); attempt family bundle-decoded — see GAPCLOSE.md §4 |
| DISCUSSION_FORUM | `rest/classroomDiscussions/` | ✅ covered |
| FEED | feedV3, getFeed, getMyPosts, notifications | ✅ covered |
| FEEDBACK | `api/feedback/student/sessions` (empty) | ⚠️ gap only because no active sessions |
| COURSE_REGISTRATION | `api/studentCourseRegistration/sessions` (wizard renders; 400 "No course registration session is found" live) | ⚠️ no live data (steps 2–4 data-gated); full wizard service chain decoded — see GAPCLOSE.md §3 |
| EXAMINATION_MANAGEMENT / EXAM_ENROLLMENT / EMS_ASSESSMENTS / EMS_ONLINE_ASSESSMENTS | resultDeclaration*, ems/enrollment/*, ems/student/assessments | ✅ covered |
| HOSTEL_MANAGEMENT / HOSTEL_ATTENDANCE | `rest/hostel/attendance/current`, `users/{ukid}/hostelData`, passConsole | ✅ covered |
| LEAVE_MANAGEMENT / LEAVE_MANAGEMENT_V2 | passConsole requests + campusHelpCentre outpass services | ✅ covered |
| MENTOR_MANAGEMENT | `api/mentorManagement/mentee/mentor/{ukid}`; hub-v1 HIDDEN → ✅ CLOSED Pass 4 (aimentor gateway live, GAPCLOSE.md §6) | ✅ core covered |
| VENUE_BOOKING | venue-booking/bookings/{self,infrastructure-types} | ✅ covered; Pass 4: booking rules GET + submit POSTs decoded (GAPCLOSE.md §2) |
| ACCESS_MANAGEMENT | access/passConsole | ✅ covered |
| CAMPUS_HELP_CENTRE | campusHelpCentre/* | ✅ covered; Pass 4: svc-18 formDetails live + submit POST decoded (GAPCLOSE.md §1) |
| CLUBS_AND_CHAPTERS | api/v1/{ccs/my,ccs} | ✅ (empty at college) |
| COURSE_PLANNER, OBE*, TRANSCRIPT_MANAGEMENT, STAFF/STUDENT_MANAGEMENT, CREATE_CLASS, QUESTION_BANK, ANALYTICS, ASSET_MANAGEMENT, EXAM_RESULTS_EDIT, EMS_* (upload/config/qb), SSO, REPORT_V2, SEND_EMAIL, QR_CODE, PROCTOR_WEBCAM, ONLINE_EXAM_PROCTORING | — no student-facing endpoint fired for these (admin/faculty-side) | ℹ️ not student-reachable (by design or enrollment state) |

**ENABLED flags with NO student endpoint exercised**: COURSE_PLANNER, QUESTION_BANK, EXAM_RESULTS_EDIT, OBE (+dashboard/attainment), TRANSCRIPT_MANAGEMENT, LICENSE_DASHBOARD, STAFF_MANAGEMENT, STUDENT_MANAGEMENT, CHC_DASHBOARD, CLASS_SWAP, CANCEL_CLASS, CREATE_SESSION_WITHOUT_SLOT, COURSE_PLANNER, CLASSROOM_PREVIOUS_TERM_DATA (admin/feature plumbing). Listed as KNOWN GAPS (informational).

## 5. Known gaps & ranked recommendations

**Explicit KNOWN GAPS**
1. Quizzes: endpoints exist; **zero quizzes live this term**; bundle-only quiz-taking API (`quizQuestionnaire/*`, `ems/student/attempt`) unreachable and unverified with data — *Pass 4: endpoints are live and reachable (`…/student/606/list` → 200 empty; `…/attempt/questions/1` → 400 data-gated), full attempt lifecycle + payloads decoded — see GAPCLOSE.md §4–5. Console only if quizzes appear.*
2. Fees: every fee/dues/self-pay endpoint **403** for this account (student role not the payer). Money data ≠ accessible, regardless of MCP.
3. Feedback, Course Registration, Offer Letter, Certificates, Clubs: live endpoints return empty/error (no opportunity/state) — not MCP-able now — *Pass 4: course-reg 400 confirmed for `activeSessions=false` AND `true`; the full 4-step wizard service chain is decoded from the Angular bundle for a future session — GAPCLOSE.md §3.*
4. Result per-term detail works only for declared terms (term/5 declared; others "Not Declared").
5. Class 607 CS4801 unreachable (401 permission) by design.
6. *(Pass 4 additions)* AI mentor hub: live at the aimentor gateway but gated on `POST /api/v1/mentor/consent` (`access.allowed=false`) — a mutation, deliberately not fired — GAPCLOSE.md §6. Book-a-Venue creation: venue inventory + attributes 403 for students → submit decoded but nothing reachable past Step 2 — GAPCLOSE.md §2. Venue booking submit payload in GAPCLOSE.md is decoded-only (no POST replayed). All mutations (chc/request/v2, readNotificationObjects, gradebookStatus write) remain never-replayed by design.

**Ranked MCP additions (student value: deadlines / marks / money)**
1. 🔴 **get_assignments(classId?) & get_assignment(classId, assignmentId)** — `/rest/classes/{c}/users/{ukid}/assignments` (+page/perPage) + `/rest/assignments/v1/getStudentAssignmentDetails`. Verified live; delivers titles, due dates ("Submission Pending", "Oct 30, 2026"), submission state. THE proven gap. **✅ ADDED to server.py + verified live (2026-10-18): get_assignments (9 classes, 0 draft/4 upcoming/23 previous; page+perPage pass-through upstream-observed 607 p2 psz=5 totalPagesPrev=4) & get_assignment(606,846).**
2. 🔴 **get_results(termId?)** — `/api/v2/resultDeclaration/student/terms/{ukid}` + `/term/{t}/{ukid}`: CGPA/percentage/grades per term. Verified live. **✅ ADDED to server.py + verified live (2026-10-18): overview 4 terms / 0 declared / hasAnyDeclaredResult=false; term/5 5 course rows (MA1001 etc.), grades null until declared.**
3. 🔴 **get_class_assessments(classId)** — `/rest/gradebook/v2/assessmentResult?classId=` & assessment records (marks as they publish). Verified live (sparse this term). **✅ ADDED to server.py + verified live (2026-10-18): class 606 → student identity rows OK, grades/components [] (nothing published yet) — tool surfaces it compactly as designed.**
4. 🟠 **get_mentor()** — `/api/mentorManagement/mentee/mentor/{ukid}`. Verified live. **✅ ADDED + live-verified: 1 mentor record with name, email and phone.**
5. 🟠 **get_hostel_summary()** — `/rest/hostel/attendance/current` + `users/{ukid}/hostelData`. Verified live. **✅ ADDED + live-verified: allotment record with date range; 7-day roll surfaced per-date; empty profile hostelData correctly surfaced as none.**
6. 🟠 **get_passes()** — `/api/access/passConsole/user/requests` (pass status/history) + help-centre outpass requests as fallback. Verified live. **✅ ADDED + live-verified: console totalCount=0 (hosteller card surfaced from the same response); fallback lists recent CHC outpass requests, all closed/Approved.**
7. 🟡 **get_notifications()** — `/rest/service/notifications`. Verified live (read-only). **✅ ADDED + live-verified: unread=10/12; list-only (mark-read never wired, in-code policy comment).**
8. 🟡 **get_help_requests() / get_help_services()** — campusHelpCentre services/v3 + requests/v2 (+detail). Verified live. **✅ ADDED as get_help_requests + live-verified: 7 services + 10 requests; detail id 40536 → closed/Approved with 6 form values, 0 comments.**
9. 🟡 **get_venue_bookings()** — bookings/self + infrastructure-types. Verified live. **✅ ADDED + live-verified: TODAY and PAST windows → totalCount=0; bookableTypes=[{65, Classroom, DIRECT}].**

Plus the gated write (Pass 5, 2026-10-18): **preview_outpass / create_outpass** — see the §6 table row for 🔒 POST `/api/chc/request/v2`. preview (no-mutation) live-verified; create's refusal path unit-verified; the POST itself never fired.
10. ⚪ **quiz/get_exams()** — quizzes & EMS attempt endpoints: implement only when school activates quizzes/exams (would 404/empty now).
11. ⚪ fee wallets — cannot be served until account pays directly (403).

**Not recommended**: admin-console endpoints (roles/adminRights/departmentsHierarchy/student rosters) — student-scoped, noise for the MCP.

## 6. Pass 4 — gap-closure verification (2026-10-18, GAPCLOSE.md)

Same legend as §2. Rows marked 🔒 are submit/mutation targets **decoded from the JS bundles only — never fired live** (read-only rule). Row shapes source: `gapclose_raw.json`.

### Forms & booking flows (Pass 4)
| Endpoint (template) | Params | Returns | MCP | curl ✅ |
|---|---|---|---|---|
| GET `/rest/campusHelpCentre/services/{serviceId}/formDetails` | serviceId(=18) | dynamic form schema: `formDetails[]` (fields ids 116–121, `element` types, `fieldTypeParent:"USER_DETAILS"`, `userFieldIdentifier`, `mandatory`, `isEditable`, `sequence`), `dateRangeDetails[]` (Out/Return, ids 24=START/25=END, min/maxTime, endMaxDays, rangeValueId, currentDateTime), `attachmentDetails[]`, `slotDetails[]`, `disclaimer/paid/amount/currency`, request-rights braces | preview_outpass / create_outpass (schema fetch) — see next row | ✅ 200 (3.9 KB) |
| 🔒 POST `/api/chc/request/v2` | body | svc submit: `{serviceId, formDetails[], dateRangeDetails[], attachmentDetails[{label,requestFormAttachmentId,mandatory,mediaId}], slotDetails[{slotId,noOfSeatsBooked}]}` → 200 `{paid,orderId?,requestId?}`; 400 toast; 409 duplicate modal | **create_outpass (GATED WRITE, confirmation-gate): fired only with confirmed=true; preview_outpass builds + checks this exact payload (values filled against live formDetails) with NO POST; confirmed=false refusal path unit-verified with an httpx.post tombstone (0 network writes); 409 → `DUPLICATE_REQUEST`** | 20 live calls; POST never replayed during verification by design |
| 🔒 POST `/api/chc/request/others` | body(+`createdFor`) | raise-for-others variant (needs `requestForOthersRight`, which is false for student) | NONE | bundle-only |
| 🔒 POST `/api/chc/service/fixedFieldValue` | body | fixed-field value cache (fires on service-page interaction) | NONE | bundle-only |
| GET `/rest/campusHelpCentre/existingRequest?serviceId=` | serviceId | dedupe precheck | NONE | bundle-only |
| GET `/api/venue-booking/booking/rules/self/{typeId}` | typeId(=65) | rules: `venueType{id,name,totalInfrastructureMapped:10}` + per-`userGroup.groupType:"Student"` `singleBooking{allowed:true,bookingType:"DIRECT",adminActionRequired:true}`, `multiBooking.allowed:false` | NONE | ✅ 200 |
| GET `/api/venue-booking/bookings/infrastructure-types?bookingType=DIRECT` | bookingType | student-bookable types: only `{id:65,"Classroom"}` (vs 1/classroom unfiltered) | NONE | ✅ 200 |
| GET `/api/infrastructureVersion/venues` | infrastructureTypeId, startDatetime, endDatetime, page, size | **403** "You do not have sufficient privileges" — student venue inventory empty → Step 3 unreachable | NONE | ✅ 403 |
| GET `/rest/infrastructure/attributes` | — | amenity attributes for the Step-1 requirements picker — **403** for student (picker renders dead) | NONE | ✅ 403 |
| 🔒 POST `/api/venue-booking/bookings` | body | direct booking: `{bookingName, purpose, recurrenceType:"NONE", isVisitor|bookingForUkid, typeSelections[{infrastructureTypeId, bookingMode:"SINGLE"\|"MULTI", startDatetime, endDatetime, minOccupancy, amenityAttributeIds, selectedVenues[{infrastructureId, tariffPerDay, deptRequirements[{departmentId,requirement}]}]}]}` | NONE | bundle-only |
| 🔒 POST `/api/venue-booking/booking-requests` | body | request-mode variant: `typeSelections[{infrastructureTypeId, venueCount, startDatetime, endDatetime, minOccupancy, amenityAttributeIds}]` | NONE | bundle-only |
| 🔒 PUT `/api/venue-booking/bookings/cancel/{id}?reason=` | id, reason | cancel own booking | NONE | bundle-only |

### Course registration (Angular service chain, bundle `main-f9916fb849`)
| Endpoint | Params | Returns | MCP | curl ✅ |
|---|---|---|---|---|
| GET `/api/studentCourseRegistration/sessions` | activeSessions(false\|true), currentPage, perPage, searchKey, studentUkid | **400** `{"message":"No course registration session is found"}` both modes — no `sessionId` ever obtainable | NONE | ✅ 400 (both) |
| GET `/api/studentCourseRegistration/{sessionId}` | sessionId | session detail (Step 1: View Session) | NONE | bundle-only |
| GET `/api/studentCourseRegistration/course/{registrationTypeId}` | sessionId, backlog, specialisationMappingId | Step 2 course list | NONE | bundle-only |
| 🔒 PUT `/api/studentCourseRegistration/course` | sessionId, body=course | Step 3 add-to-cart | NONE | bundle-only |
| 🔒 DELETE `/api/studentCourseRegistration/course/{courseId}` · `/course` | sessionId | remove from cart / clear all | NONE | bundle-only |
| 🔒 POST `/api/studentCourseRegistration/registration` | sessionId, body | Step 4 final register → slip `/courseRegistration/:sessionId/slip/:ukid` | NONE | bundle-only |
| 🔒 POST `/api/studentCourseRegistration/` · DELETE `/{id}` | sessionId | start / abandon session | NONE | bundle-only |

### Quiz & EMS attempt families (bundle-decoded; data-gated)
| Endpoint | Params | Returns | MCP | curl ✅ |
|---|---|---|---|---|
| GET `/api/classroomV2/quizQuestionnaire/student/{classId}/list` | status(ONGOING…), search, page, perPage | `{quizzes[], totalCount, page, perPage}` — 0 live quizzes | NONE | ✅ 200 ([]) |
| GET `…/quiz/accessCode/student/{quizId}` | quizId | access-code gate for locked quizzes | NONE | ✅ 400("Invalid Quiz Id") |
| GET `…/quiz/group/parent/{objectId}/student/{ukid}/assignment` | objectId, ukid | group-quiz deeplink resolver | NONE | ✅ 200 (empty) |
| 🔒 GET `…/student/{quizId}/details` · `/attempt/history` · `/attempt/current` | — | quiz detail; attempt history; current attempt (404 ⇒ null) | NONE | bundle-only (history probe 400 "does not use the questionnaire flow") |
| 🔒 POST `…/student/{quizId}/attempt/start` / POST `…/attempt/{attemptId}/submit` | — | start/end attempt lifecycle | NONE | bundle-only |
| GET `…/student/{quizId}/attempt/{attemptId}/questions` | attemptId | question paper | NONE | bundle-only |
| 🔒 PUT `…/attempt/{attemptId}/response` | body(`uzt`) | save answer: `{questionnaireQuestionId\|…Number, deleteResponse?, answer, multipleCorrectOptions[], fillUps[{subQuestionId,answer}], mtfs[{subQuestionId,mtfAnswerIds[]}], mediaIds[]}` | NONE | bundle-only |
| GET `/api/classroomV2/quizQuestionnaire/student/result/{classId}/{quizId}/overview` · `/attempt/{no}` | classId, quizId | results after evaluation | NONE | bundle-only |
| GET `/api/ems/student/attempt/questions/{assessmentId}` | assessmentId (+proctorSessionId, examSessionLogId) | exam paper + `studentAssessmentStartTime` (timer) | NONE | ✅ 400("Invalid assessment id") = reachable, data-gated |
| 🔒 PUT `/api/ems/student/attempt/{assessmentId}` · `…/{assessmentId}/submit` | body(`nqt`) | save/submit exam (same answer family incl. `proctorSessionId`); requires `X-Current-URL` header on the 3 EMS URL prefixes | NONE | bundle-only |
| GET `/rest/structure/v1/collegeTime` | — | server clock `{timeZone:"Asia/Kolkata", id:529, currentTime, name}` — used to time quiz/EMS windows | NONE | ✅ 200 |

### AI mentor gateway v1 (host **`https://aimentor.digiicampus.com`** — `Authorization: Bearer <JWT>` + `X-College-ID: 529`; the only host where Bearer works)
| Endpoint | Returns | MCP | curl ✅ |
|---|---|---|---|
| GET `/api/v1/mentor/conversations` (+detail/DELETE `{id}`) | `{"conversations":[]}` | NONE | ✅ 200 |
| GET `/api/v1/mentor/terms` | `{version:2, sections[{title,text}], notice}` | NONE | ✅ 200 |
| GET `/api/v1/mentor/privacy` | `{version:1, sections[…]}` | NONE | ✅ 200 |
| GET `/api/v1/mentor/access` | `{allowed:false, terms_accepted:false, credits_remaining:20, credits_limit:20, credits_period:"day", credits_resets_at, web_search_available:false, credits_enforced:true}` | NONE | ✅ 200 |
| GET `/api/v1/mentor/requests` | `{"requests":[]}`; create = `POST {topic, note}` | NONE | ✅ 200 |
| 🔒 POST `/api/v1/mentor/consent` · POST `/ask/stream` (SSE, body `{question, conversation_id?, search_web?}`) · GET `/turns/{conversationId}/stream?after=` (SSE) | consent gate + streaming chat | NONE | bundle-only |

### Gradebook status & notifications (schema closures)
| Endpoint | Params | Returns | MCP | curl ✅ |
|---|---|---|---|---|
| GET `/api/gradebookStatus/` | — | live array of 5 rows `{id, name("Missing"/"Exp"/"Malpractice"/"Absent"/"Absent Condoned"), meaning, colorCode, allowGrading, considerMinMarks, attendanceStatus, approvedLeave, fairnessStatus, editAllowed}` | NONE | ✅ 200 |
| 🔒 PUT `/api/gradebookStatus/assessmentStatus/` | body | faculty-only write `{classId, searchKey, allStudentsAllPages, assessmentId, gradebookStatusId, studentUkids}` | NONE | bundle-only |
| GET `/rest/service/notifications` | — | full row schema: `{notificationObjectId, ukid, typeId, type("SESSION_CREATED"…), object, objectType:"CLASSROOM_V2", objectId, parentObjectType, parentObjectId, metaDataMap, id, content, time, displayTime, seen}` — 12 live rows; unread = `!seen` count | get_notifications (list-only; unread badge preserved) | ✅ 200 (schema closed Pass 4) |
| 🔒 PUT `rest/service/readNotificationObjects` | body | mark-seen `{notificationObjectIds:[…]}` (mutation — supersedes legacy `POST rest/feed/seenByUkid/v2` for the notifications panel) | **never wired, by policy** — get_notifications documents in-code why the ONLY notifications call made is the list GET (mutating seen-state would destroy the unread signal for the app itself) | never-replayed by design |

---
*Raw captures: `net_*.txt`, `post_*.txt`, `snap_*.txt`, `all_seen.txt` (145 URLs incl. dupes), `bundle_paths.txt`, `hidden.txt`, `enabled_flags.txt`, `verified.txt`, plus Pass 4: `GAPCLOSE.md` (narrative + decoded payloads), `gapclose_raw.json` (live curl bodies for every ✅ Pass 4 row) — all in this directory.*
