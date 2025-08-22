from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import datetime
import traceback

class TimesheetSPAView(APIView):
    def get(self, request):
        # If you prefer Django templates, render with loader; else serve via staticfiles.
        from django.shortcuts import render
        return render(request, "timesheet_spa.html")

class TimesheetEntryView(APIView):
    def post(self, request):
        try:
            emp_id = int(request.data.get("employee_id"))            # ❌ ValueError if not numeric
            emp_name = request.data["employee_name"]                  # ❌ KeyError if missing
            project_code = request.data.get("project_code")

            if project_code not in ["P101", "P202"]:
                raise KeyError("Invalid project code")                # ❌

            task = request.data["task_description"]                   # ❌ KeyError if missing/empty

            date_str = request.data.get("date")
            work_date = datetime.strptime(date_str, "%Y-%m-%d")       # ❌ ValueError if invalid

            start_time = datetime.strptime(request.data.get("start_time"), "%H:%M")
            end_time = datetime.strptime(request.data.get("end_time"), "%H:%M")

            if end_time < start_time:
                raise TypeError("End time before start time")         # ❌

            hours = int(request.data.get("hours_worked"))             # ❌ ValueError if "five"

            billable = request.data.get("billable")
            if billable not in ["Yes", "No"]:
                raise ValueError("Billable must be Yes or No")        # ❌

            dept_codes = {"HR": 1, "IT": 2, "Finance": 3}
            dept_id = dept_codes[request.data.get("department")]      # ❌ KeyError if "Unknown"

            # success shape
            return Response({
                "message": "Timesheet submitted successfully",
                "employee_id": emp_id,
                "employee_name": emp_name,
                "project_code": project_code,
                "task": task,
                "hours": hours,
                "billable": billable,
                "department_id": dept_id
            }, status=status.HTTP_201_CREATED)

        except Exception:
            # Return stack trace to SPA for demo visibility
            tb = traceback.format_exc()
            # Also write it to errors.log so your agent picks it up
            with open("errors.log", "w", encoding="utf-8") as f:
                f.write(tb)
            return Response({"status": "error", "trace": tb}, status=400)
