# Gap-closure crawl — GAPCLOSE.md
2026-10-18 · Session `digii2` (recovered; see §0) · Student ukid 1467753 · **Read-only: every form driven to final pre-submit state, NO submit/pay/confirm button ever clicked.**

Bundle under audit:
- React main: `https://cdnprod.digiicampus.com/V2/20261016164843/assets/index-BovLCzws.js` + all 134 lazy chunks in `__vite__mapDeps` (downloaded to scratch).
- Angular main (serves legacy SPA paths): `version-1792169256` bundle `main-f9916fb849.scripts.min.js` (9.3 MB decompressed; served compressed — fetch with `--compressed`).

Raw live responses are kept local only (they contain personal form-prefill
values); reproduce any row with the endpoint + `curl -H "Auth-Token: $TOKEN"`.

---

## 0. Session recovery (changed from last run's spec)
The old recovery recipe (`localStorage.userInfo` only) **no longer boots the authenticated app**. Current truth (from bundle):
- All API calls (`bt` axios) attach header **`Auth-Token` read from the cookie `user=<JWT>`** (`gmt()` → `document.cookie`), NOT from localStorage.
- Route gate `jf` (PrivateRoute): absence of the cookie → **clears all storage (`tSe()`)** and redirects to `/home`, which renders the login shell. Presence → renders the authed app (mounted on the `/*` catch-all at `/V2/`, NOT at `#/home` — `#/home` is the pre-auth landing).
- **Recovery steps that worked**: seed `document.cookie = "user=<JWT>; path=/; domain=.digiicampus.com"` (exact JWT from `.userinfo.json`, byte-verified — a truncated token yields silent 401s), keep `userInfo` in localStorage/sessionStorage, navigate to `https://snuc.digiicampus.com/V2/` (no hash). Angular pages (`/courseRegistration/…`, `/helpCenter/…`) then load with the same cookie.

Legacy route map (from sidebar config, index-C3npnmsV.js): Campus Help Centre → **Angular** `/helpCenter/requests`; Course Registration → **Angular** `/courseRegistration/student`; Book a Venue → **React** `#/multiVenueBooking/newbooking`.

---

## 1. Help Center — new request (service 18) ✅ CLOSED
**Driven live to pre-submit:** `/helpCenter/requests` (list) → **New Request** → service list (`/helpCenter/services`, fires `GET /rest/campusHelpCentre/services/v3` no-params + `?includeMiddlewareService=true`) → category **Hostel Outpass** → **Hostel Day Outpass - Gents (service id 18)** at `/helpCenter/service/18`.

**Schema GETs (UI-driven + curl ✅):**
- `GET /rest/campusHelpCentre/services/18/formDetails` → 200:
  - `formDetails[]`: `{id, name, element (textField/textArea/…), minimum*, maximum*, value, valueReference, elementOptions, operatorType, isEditable, fieldTypeParent, userFieldIdentifier, fixedField, sequence, mandatory}` — svc 18 renders ids 116–121: Name/Mail/Program/Dept/Section auto-filled `USER_DETAILS` (isEditable false, prefilled value) + `Description` (`textArea`, mandatory, editable).
  - `dateRangeDetails[]`: Out Date + Out Time (**id 24, `dateTimeType:"START"`**, `minTime,maxTime:"20:30:00"`, `endMaxDays:1`) and Return Date + Return Time (**id 25, `"END"`, `maxTime:"23:59:59"`), each with `rangeValueId, currentDateTime` snapshot.
  - `attachmentDetails[]`, `slotDetails[]` = `[]` here; `disclaimer:null, paid:false, amount:null, currency…`; braces `selfRequestRight/requestingRight/userFieldIdentifier/visibilitySetting/scheduleRequestEnabled`.
- `GET /api/chc/request/settings` → 200 `{requestForOthersRight:false, bulkRequestRight:false}` (student).
- `GET /rest/campusHelpCentre/requests/v2?perPage=20&selectedStatus=submitted&selectedStatus=pending` → 200 (list; `selectedStatus` repeatable).
- Supporting (bundle, fired on interaction): `POST /api/chc/service/fixedFieldValue` (fixed-field value cache), `GET /api/chc/admin/autoFilled/formDetails?ukid&serviceId` (autofill when raising for others), `GET /rest/campusHelpCentre/existingRequest?serviceId=` (dedupe precheck).

**Submit target (bundle, angular `requestFormController`; NOT clicked):**
- **`POST /api/chc/request/v2`** payload:
```json
{ "serviceId": 18, "formDetails": [/* full formDetails array verbatim, value set on each field*/],
  "dateRangeDetails": [/* verbatim; value filled for START date+time and END date+time */],
  "attachmentDetails": [ { "label", "requestFormAttachmentId", "mandatory", "mediaId" } ],
  "slotDetails": [ { "slotId": int, "noOfSeatsBooked": int } ] }
```
- Optional extras: `createdFor:<ukid>` (+ goes to **`POST /api/chc/request/others`** instead), `schedule:{name,scheduleType:"DO_NOT_REPEAT"|"REPEAT",scheduleTime,startDate,endDate?,days?[weekdays],scheduleDate?}` + `isSchedule:true`; fixed dropdown/radioButton fields get `valueReference` = option label.
- Responses per bundle: 200 → `{paid, orderId?, requestId?}` (paid → order redirect); 400 → message toast; **409 → duplicate-request modal**.

---

## 2. Book-a-Venue — New Booking ✅ driven to pre-submit (2/3 steps)
**Driven live:** `#/multiVenueBooking` → **New Booking** → React wizard `#/multiVenueBooking/directBooking` (3 steps: Venue Type & Requirements → Select Venues → Review & Submit).

**Schema GETs captured live (React recorder + curl ✅):**
- `GET /api/venue-booking/bookings/self?page=1&size=12&startDatetime=2026-10-18 00:00:00&endDatetime=…&period=TODAY` → 200
- `GET /api/venue-booking/bookings/infrastructure-types` (no filter) and **`?bookingType=DIRECT`** → 200 (only Classroom id 65 for students)
- `GET /api/venue-booking/booking/rules/self/65` → 200: `{venue:{...}, venueType:{id,name,totalInfrastructureMapped:10}, bookingRules:[{userGroup:{groupType:"Student"}, singleBooking:{allowed:true, bookingType:"DIRECT", adminActionRequired:true}, multiBooking:{allowed:false, …}}]`
- `GET /rest/infrastructure/attributes` → **403** for this student (amenities picker dead)
- Step 2 fires `GET /api/infrastructureVersion/venues?infrastructureTypeId=65&startDatetime=…&endDatetime=…&page=1&size=10` → **403 "You do not have sufficient privileges"** → venue list permanently empty for students → **Step 3 unreachable; pre-submit state = Step 2.**

**Submit target (bundle `NewBookingApi-DTJBcWw9.js` + `index-BSgx10sY.js`/`index-DoNM3XP5.js`; NOT clicked):**
- **`POST /api/venue-booking/bookings`** (direct; = the flow students see):
```json
{ "bookingName": str, "purpose": str, "recurrenceType": "NONE",
  "isVisitor": false | "visitorId": id | "bookingForUkid": ukid,
  "typeSelections": [ { "infrastructureTypeId": 65, "bookingMode": "SINGLE"|"MULTI",
     "startDatetime": "2026-10-20 10:30:00", "endDatetime": "…", "minOccupancy": int,
     "amenityAttributeIds": [ids], 
     "selectedVenues": [ { "infrastructureId", "tariffPerDay",
        "deptRequirements": [ {"departmentId": int, "requirement": str} ] } ] } ] }
```
- Request-mode variant (for users with request rights): **`POST /api/venue-booking/booking-requests`** → `{bookingName, purpose, specialRequest?, recurrenceType, isVisitor?, bookingForUkid?, typeSelections:[{infrastructureTypeId, venueCount, startDatetime, endDatetime, minOccupancy?, amenityAttributeIds?}]}`
- Support family: `PUT /api/venue-booking/bookings/cancel/{id}?reason=`, `GET …/bookings/{id}` (+`/venues`), `GET …/bookings/calendar?venueId=`, `GET /api/infrastructure/types/v2`, `GET /rest/infrastructure/venues`, guests (`…/bookings/guests?search&page&size`), `GET /rest/infrastructure/{id}`.
- **Still blocked:** venue inventory + attributes 403 → no booking can be created from this account (nothing clickable past Step 2). Submit endpoint fully documented.

## 3. Course Registration wizard ✅ step 1 (2–4 data-gated)
- Step 1 tied live to `GET /api/studentCourseRegistration/sessions?activeSessions=…&currentPage=1&perPage=10&searchKey=&studentUkid=1467753` → **400** `{"message":"No course registration session is found"}` (both `activeSessions=false` and `true`; UI shows empty Session ID/Sessions/Term table + the full 4-step banner: View Session → Select Courses → Add to Cart → Register and Generate Slip).
- **Blocked reason:** no registration session exists for this cohort → `sessionId` never obtainable → steps 2–4 un-openable (verified live twice, plus `activeSessions=true`).
- **Full chain from the Angular bundle (`studentCourseRegistrationService`, main-f9916fb849):**
  - `GET /api/studentCourseRegistration/{sessionId}` (session detail)
  - `GET /api/studentCourseRegistration/course/{registrationTypeId}?backlog&specialisationMappingId&sessionId` (Step 2 course list)
  - `PUT /api/studentCourseRegistration/course` (body=course, params sessionId — Step 3 add-to-cart)
  - `DELETE /api/studentCourseRegistration/course/{courseId}` (remove from cart) · `DELETE /api/studentCourseRegistration/course` (clear all)
  - `POST /api/studentCourseRegistration/registration` (params sessionId, body payload — **Step 4 final register**) → slip UI `/courseRegistration/:sessionId/slip/:ukid`
  - `POST /api/studentCourseRegistration/?sessionId=` (create/start session) · `DELETE /api/studentCourseRegistration/{id}?sessionId=` (abandon)

## 4. Quiz — `classroomV2/quizQuestionnaire/student` ✅ endpoint live, data-gated
- **Live:** `GET /api/classroomV2/quizQuestionnaire/student/{classId}/list?status=ONGOING&search=&page=1&perPage=15` (classId 606) → **200** `{quizzes:[], totalCount:0, page, perPage}`. `GET /rest/structure/v1/collegeTime` → 200 `{timeZone:"Asia/Kolkata", id:529, currentTime, name}` (server clock for timers).
- Data-gated `400` shapes (live probes with no quiz): `…/606/attempt/history` → "This quiz does not use the questionnaire flow"; `…/quiz/accessCode/student/606` → "Invalid Quiz Id"; group assignment `…/quiz/group/parent/{id}/student/{ukid}/assignment` → 200 empty body.
- **Student API surface (bundle class `w2a`, payload builder `uzt`):**
  | Method | Path |
  |---|---|
  | GET | `/api/classroomV2/quizQuestionnaire/student/{classId}/list` (status, search, quickFilters-, page, perPage) |
  | GET | `…/student/{quizId}/details` · `…/attempt/history` · `…/attempt/current` (404 ⇒ treated as null) |
  | GET | `/api/classroomV2/quiz/accessCode/student/{quizId}` · `…/verifyAccessCode?accessCodeByStudent=` |
  | POST | `…/student/{quizId}/attempt/start` |
  | GET | `…/student/{quizId}/attempt/{attemptId}/questions` |
  | PUT | `…/student/{quizId}/attempt/{attemptId}/response` — payload `{questionnaireQuestionId | questionnaireQuestionNumber, deleteResponse?, answer, multipleCorrectOptions[], fillUps[{subQuestionId, answer}], mtfs[{subQuestionId, mtfAnswerIds[]}], mediaIds[]}` |
  | POST | `…/student/{quizId}/attempt/{attemptId}/submit` |
- Results: `GET /api/classroomV2/quizQuestionnaire/student/result/{classId}/{quizId}/overview` · `…/attempt/{attemptNo}`.
- Group quiz: `GET /api/classroomV2/quiz/group/parent/{objectId}/student/{ukid}/assignment` (deeplink resolver), plus group list under `groupBaseUrl`/api/classroomV2/quiz/group.
- **Still blocked:** `quizzes:[]` → no attempt/submit/live data possible (flag on, no quizzes this term — matches CENSUS gap 1).

## 5. EMS online-exam attempt ✅ documented from bundle (no live attempt)
Bundle class `Its`, base **`/api/ems/student/attempt`**:
- `GET /rest/ems/student/assessments/{assessmentId}` (assessment header/details for the exam player)
- `GET /api/ems/student/attempt/questions/{assessmentId}` (`?proctorSessionId&examSessionLogId` when proctoring) → response shape `{…, studentAssessmentStartTime}` (used for timer)
- `PUT /api/ems/student/attempt/{assessmentId}` — save one response; payload builder `nqt`: `{questionnaireQuestionId, deleteResponse?, answer, multipleCorrectOptions[]|answer[number], fillUps[{subQuestionId, answer}], mtfs[{subQuestionId, mtfAnswerIds[]}], mediaIds[], proctorSessionId?, examSessionLogId?}` (same family as quiz save)
- `PUT /api/ems/student/attempt/{assessmentId}/submit` — final submit (body `{proctorSessionId?, examSessionLogId?}` optional)
- Delete: `PUT …/{assessmentId}` `{questionnaireQuestionId, deleteResponse:true}`
- Proctor security: requests to `/rest/ems/student/assessments/|/rest/ems/student/answerSheet/|/api/ems/student/attempt/` carry header **`X-Current-URL`**; SEB/webcam policy strings enumerated (full-screen watchdog etc.).
- Live probe: `GET /api/ems/student/attempt/questions/1` → **400 "Invalid assessment id"** (endpoint reachable, gated on data). Same story: `/rest/ems/student/answerSheet/`.

## 6. Mentor Hub v1 ✅ CLOSED — live and verified (5 endpoints, all 200)
**Hard finding:** not served by snuc.digiicampus.com. Gateway is **`https://aimentor.digiicampus.com`**, axios instance `ZU/pl` with
`Authorization: Bearer <JWT>` (**Bearer**, unlike main API!), `X-College-ID: 529`, `withCredentials`, `Content-Type: application/json`. (Also `bi.digiicampus.com` → `https://aimentorqa.digiicampus.com`.)

| Endpoint (GET unless noted) | ✅ Status | Shape |
|---|---|---|
| `/api/v1/mentor/conversations` | 200 | `{"conversations":[]}`; detail `GET/{id}`, `DELETE/{id}` |
| `/api/v1/mentor/terms` | 200 | `{version:2, sections:[{title,text}…]}` |
| `/api/v1/mentor/privacy` | 200 | `{version:1, sections:[…]}` |
| `/api/v1/mentor/access` | 200 | `{allowed:false, terms_accepted:false, terms_version:2, accepted_at:null, credits_remaining:20, credits_limit:20, credits_resets_at:"2026-10-19T00:00:00Z", credits_period:"day", web_search_available:false}` — neutrals: **20/20 credits/day**, onboarding not consented |
| `/api/v1/mentor/requests` | 200 | `{"requests":[]}`; create = `POST {topic, note}` |

Also in bundle (documented, not replayed — mutations/stream): `POST /api/v1/mentor/consent`; `POST /api/v1/mentor/feedback {subject_type, subject_id, rating, note?}`; memories `GET /memories`, `GET /memories/saved/{ukid}`, save/update; chat **SSE** `POST /api/v1/mentor/ask/stream` (body `{question, conversation_id?, search_web?}`, `credentials:include`) and `GET /api/v1/mentor/turns/{conversationId}/stream?after=`.
- Note: `curl https://snuc.digiicampus.com/api/v1/mentor/…` returns the Angular HTML shell (200) — wrong host (/api/v1/mentor is not routed on snuc.digiicampus.com); the aimentor gateway is the real one.
- **Still blocked:** `allowed:false` until `consent` POST — deliberately not fired (mutation).

## 7. gradebookStatus ✅ CLOSED
- `GET /api/gradebookStatus/` → **200 (live)** array:
  `{id, name ("Missing"/"Exp"/"Malpractice"/"Absent"…), meaning, colorCode, allowGrading, considerMinMarks, attendanceStatus, approvedLeave, fairnessStatus, createdTimestamp, modifiedTimestamp, editAllowed}`
- Consumers: `rest/gradebook/v2/assessmentResult?classId=` rows `grades[]` attach `gradebookStatus {name, colorCode}` per assessment; the student assessment-result view maps each column chip to these entries.
- Write side (faculty-only, bundle-documented, never replayed): `PUT /api/gradebookStatus/assessmentStatus/` with body `{classId, searchKey, allStudentsAllPages, assessmentId, gradebookStatusId, studentUkids}`; status values also drive the gradebook export columns (`assessmentMarks[].gradebookStatus`).

## 8. Notifications ✅ schema closed (no notification opened)
- `GET /rest/service/notifications` → 200 `{res:[{notificationObjectId, ukid, typeId, type:"SESSION_CREATED"…, object, objectType:"CLASSROOM_V2", objectId, parentObjectType, parentObjectId, metaDataMap, id, content, time, displayTime:"11 hrs", seen:false}]}` — 12 live rows sampled; unread count = `.filter(n=>!n.seen).length` (bell badge).
- Mark-as-seen = **mutation, NOT clicked/replayed**: `PUT rest/service/readNotificationObjects {notificationObjectIds:[…]}` (single/multi). Legacy `POST rest/feed/seenByUkid/v2` still exists but the notification panel uses readNotificationObjects.

---

## Verdict per target
| # | Target | Status |
|---|---|---|
| 1 | CHC svc-18 new-request submit | ✅ schema live + POST `/api/chc/request/v2` + payload fully decoded |
| 2 | Book-a-Venue New Booking | ✅ pre-submit driven (Step 2/3 hard-403 hardware + doc); POST `/api/venue-booking/bookings` + payload |
| 3 | Course Registration wizards | ✅ step 1 live; steps 2–4 chain fully documented; hardcoded data-block (no session) |
| 4 | quizQuestionnaire + group/quiz/access-code | ✅ list live (200 empty) + all attempt/submit shapes decoded |
| 5 | `ems/student/attempt` | ✅ lifecycle fully decoded incl. proctor fields & X-Current-URL header |
| 6 | mentor hub v1 | ✅ CLOSED — live gateway + 5 GETs verified, SSE contract decoded |
| 7 | gradebookStatus | ✅ CLOSED — 200 live + ties to gradebook/assessment mapping |
| 8 | notifications | ✅ CLOSED — full row schema |
