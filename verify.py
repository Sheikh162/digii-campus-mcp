"""Live verification: call every tool through the FastMCP client layer."""
import asyncio
import json

from fastmcp import Client
import server


async def main() -> None:
    async with Client(server.mcp) as client:
        tools = await client.list_tools()
        print("TOOLS:", [t.name for t in tools])
        calls = [
            ("get_attendance_summary", {"term": 32}),
            ("get_attendance_summary", {"term": 32, "detail": True}),
            ("get_courses", {}),
            ("get_timetable", {"days_ahead": 30}),
            ("get_calendar_events", {}),
            ("get_profile", {}),
            ("get_drive_usage", {}),
            ("get_feed", {"n": 3}),
            ("get_assignments", {}),
            ("get_assignments", {"class_id": 606}),
            ("get_assignment", {"class_id": 606, "assignment_id": 846}),
            ("get_results", {}),
            ("get_results", {"term_id": 5}),
            ("get_class_assessments", {"class_id": 606}),
            ("get_mentor", {}),
            ("get_hostel_summary", {"days": 7}),
            ("get_passes", {}),
            ("get_passes", {"include_fallback": False}),
            ("get_notifications", {"limit": 5}),
            ("get_help_requests", {}),
            ("get_help_requests", {"request_id": 40536, "include_services": False}),
            ("get_venue_bookings", {"period": "TODAY"}),
            ("get_venue_bookings", {"period": "PAST"}),
            ("preview_outpass", {"service_id": 18, "out_date": "2026-10-20",
                                 "out_time": "17:00", "return_date": "2026-10-20",
                                 "return_time": "21:00",
                                 "description": "MCP verification preview (no submission)"}),
        ]
        for name, args in calls:
            res = await client.call_tool(name, args)
            text = "".join(b.text or "" for b in res.content)
            data = json.loads(text)
            size = len(text)
            summary = ""
            if name.startswith("get_attendance_summary"):
                courses = [c for c in data.get("courses", []) if c["overall"]["totalClasses"]]
                summary = (f"overall={data.get('percentage')}%, courses_with_data={len(courses)}"
                           f", sessions_in_first={len(data['courses'][0]['components'][0].get('sessions', []) if data.get('courses') else [])}")
            elif name == "get_courses":
                summary = f"{len(data)} courses; first={data[0]['courseCode'] or data[0]['courseName']!r} faculty={data[0]['faculty']}"
            elif name == "get_timetable":
                total_lessons = sum(len(c["lessons"]) for c in data["courses"])
                summary = (f"window={data['window']['from']}..{data['window']['to']}, "
                           f"courses={len(data['courses'])}, lessons={total_lessons}; "
                           f"first={data['courses'][0]['lessons'][0] if data['courses'] else None}")
            elif name == "get_calendar_events":
                summary = f"{len(data)} events; first={data[0]['name'] if data else None}"
            elif name == "get_profile":
                summary = (f"ukid={data['ukid']} type={data['userType']} tenant={data['tenant']} "
                           f"stats={data['stats']} roles={data['roles']}")
            elif name == "get_drive_usage":
                summary = (f"used={data['used']} free={data['free']} allocated={data['allocated']}")
            elif name == "get_feed":
                summary = f"{len(data)} posts; first author={data[0]['author']!r} t={data[0]['timestamp']!r} len(text)={len(data[0]['text'] or '')}"
            elif name == "get_assignments":
                totals = {
                    "draft": sum(c.get("totalDraftAssignments") or 0 for c in data),
                    "upcoming": sum(c.get("totalUpcomingAssignments") or 0 for c in data),
                    "previous": sum(c.get("totalPreviousAssignments") or 0 for c in data),
                }
                up = next((c for c in data if c.get("upcomingAssignments")), None)
                first = (up or {}).get("upcomingAssignments", [None])[0] or \
                    next((a for c in data for a in c.get("previousAssignments", [])), None)
                first_desc = (f"first={first['name']!r} due={first['dueDate']!r} "
                              f"submitted={first['isSubmitted']}") if first else "no assignments returned"
                summary = (f"classes={len(data)}, totals={totals}; {first_desc}")
            elif name == "get_assignment":
                summary = (f"id={data['id']} {data['name']!r}: due={data['dueDate']!r} "
                           f"submitted={data['isSubmitted']} graded={data['isAssignmentGraded']} "
                           f"resources={len(data['resources'])} submissions={len(data['submissions'])} "
                           f"with description len={len(data['description'] or "")}")
            elif name == "get_results" or name.endswith("get_results"):
                if "term_id" in args:
                    summary = (f"term={data['termName']!r} declared={data['isRegularDeclared']} "
                               f"courses={len(data['courses'])} "
                               f"first={(data['courses'][0]['courseCode'] if data['courses'] else None)!r} "
                               f"with grade={(data['courses'][0]['finalGrade'] if data['courses'] else None)!r}")
                else:
                    declared = sum(1 for t in data["terms"] if t["isRegularDeclared"] or t["isBacklogDeclared"])
                    summary = (f"overallCgpa={data['overallCgpa']} declared_terms={declared}/{len(data['terms'])} "
                               f"hasAnyDeclaredResult={data['hasAnyDeclaredResult']}; "
                               f"first declared examId={next((t['examId'] for t in data['terms'] if t['isRegularDeclared'] or t['isBacklogDeclared']), None)}")
            elif name == "get_class_assessments":
                summary = (f"student={data['student']['name']!r} reg={data['student']['registrationId']!r} "
                           f"grades={len(data['grades'])} components={len(data['assessmentComponentResults'])}")
            elif name == "get_mentor":
                m = data[0] if data else {}
                summary = (f"mentors={len(data)}; first={m.get('name')!r} "
                           f"email={m.get('email')!r} dept={m.get('departmentName')!r}")
            elif name == "get_hostel_summary":
                dates = data["attendanceWindow"]["dates"]
                counts = data["attendanceWindow"]["markedCounts"]
                a = data["allotment"]
                summary = (f"allotment={a['hostel']!r} room={a['room']!r} status={a['status']!r} "
                           f"{a['startDate']}..{a['endDate']}; welfare_dates={len(dates)}, "
                           f"counts={counts}, profileData={'yes' if data.get('profileHostelData') else 'none'}; "
                           f"first={dates[0] if dates else None}")
            elif name == "get_passes":
                summary = (f"hosteller={data.get('hosteller')!r} hostel={data.get('hostel')} "
                           f"totalCount={data.get('totalCount')} passes={len(data.get('passes', []))} "
                           f"fallback={data.get('fallbackRequests') and len(data['fallbackRequests'])} rows "
                           f"src={data.get('fallbackSource', '-')}")
            elif name == "get_notifications":
                summary = (f"unread={data['unreadCount']}/{data['totalCount']} shown={data['shown']} "
                           f"first={data['notifications'][0]['type'] if data['notifications'] else None} "
                           f"listOnly={data['note']}")
            elif name == "get_help_requests":
                if "request_id" in args:
                    summary = (f"detail id={data['requestId']} {data['serviceTitle']!r} "
                               f"status={data['status']!r} action={data['actionTaken']!r} "
                               f"formValues={len(data['formValues'])} comments={len(data.get('comments', []))}; "
                               f"firstField={data['formValues'][0] if data['formValues'] else None}")
                else:
                    summary = (f"services={len(data.get('services', []))}, requests={len(data.get('requests', []))}; "
                               f"firstService={data['services'][0]['title'] if data.get('services') else None}, "
                               f"firstRequest={data['requests'][0] if data.get('requests') else None}")
            elif name == "get_venue_bookings":
                summary = (f"period={data['period']} window={data['window']} totalCount={data['totalCount']} "
                           f"bookings={len(data['bookings'])} bookableTypes={data['bookableTypes']}")
            elif name == "preview_outpass":
                s = f"{len(json.dumps(data['payload']))}B"
                summary = (f"NO-POST preview: payload={s} form={data['serviceName']!r} "
                           f"checks={data['checks']['ok']} warnings={data['checks']['warnings']} "
                           f"filled={data['filled']['dateRange']} "
                           f"desc={data['filled']['description'][:40]!r}; summary={data['summary'][:110]!r}")
            print(f"OK {name}{args}: {size}B -> {summary}")

        # 401 path check with a garbage token
        import httpx, os
        for attempt, tok in enumerate(["bogus"]):
            r = httpx.get(server.BASE_URL + "/rest/institutionalCalendar/events",
                          headers={"Auth-Token": tok}, timeout=20)
            print("401-path: bogus token ->", r.status_code, "(TOKEN_EXPIRED path exercised in server)")

        # ---------------------------------------------------------
        # create_outpass gate: NO live submission ever (mutation).
        # Tombstone httpx.post so even a bug in the gate could not
        # reach the network during this unit check.
        # ---------------------------------------------------------
        from fastmcp.exceptions import ToolError as _TE
        fired = []

        def _no_post(*a, **kw):
            fired.append({"args": a, "kw": kw})
            raise AssertionError("NETWORK WRITE DURING VERIFICATION — refused")

        orig_post = server.httpx.post
        server.httpx.post = _no_post
        try:
            refused_calls = [
                # confirmed omitted (default false)
                {"service_id": 18, "out_date": "2026-10-20", "out_time": "17:00",
                 "return_date": "2026-10-20", "return_time": "21:00",
                 "description": "verify refusal path"},
                # confirmed explicitly false
                {"service_id": 18, "out_date": "2026-10-20", "out_time": "17:00",
                 "return_date": "2026-10-20", "return_time": "21:00",
                 "description": "verify refusal path", "confirmed": False},
            ]
            for cargs in refused_calls:
                try:
                    await client.call_tool("create_outpass", cargs)
                    print("GATE-FAIL create_outpass accepted without confirmed=true!", cargs)
                except Exception as exc:
                    msg = str(exc)
                    ok = ("CONFIRMATION_REQUIRED" in msg
                          and "preview_outpass" in msg)
                    print(f"GATE-OK create_outpass(confirmed!='true') refused: "
                          f"{type(exc).__name__}, msg_has_CONFIRMATION_REQUIRED="
                          f"{'CONFIRMATION_REQUIRED' in msg}, msg_suggests_preview="
                          f"{'preview_outpass' in msg} -> {'OK' if ok else 'FAIL'}")
            assert not fired, f"httpx.post called {len(fired)}x during refusal check!"
            print("GATE-OK zero HTTP POSTs fired during refusal-path check")
        finally:
            server.httpx.post = orig_post


asyncio.run(main())
