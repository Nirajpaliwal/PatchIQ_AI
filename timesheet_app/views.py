from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import datetime, timedelta
import traceback

class TimesheetSPAView(APIView):
    def get(self, request):
        # If you prefer Django templates, render with loader; else serve via staticfiles.
        from django.shortcuts import render
        return render(request, "timesheet_spa.html")

class TimesheetEntryView(APIView):
    def post(self, request):
        try:
            emp_id = int(request.data.get("employee_id"))
            emp_name = request.data["employee_name"]
            project_code = request.data.get("project_code")

            if project_code not in ["P101", "P202"]:
                raise KeyError("Invalid project code")

            task = request.data["task_description"]
            manager_email = request.data["manager_email"]

            date_str = request.data.get("date")
            work_date = datetime.strptime(date_str, "%Y-%m-%d")

            start_time_str = request.data.get("start_time")
            end_time_str = request.data.get("end_time")

            # Combine the work_date with the parsed times to get full datetime objects
            start_datetime = datetime.combine(work_date.date(), datetime.strptime(start_time_str, "%H:%M").time())
            end_datetime = datetime.combine(work_date.date(), datetime.strptime(end_time_str, "%H:%M").time())

            # If the end time is chronologically earlier than the start time on the same day,
            # it implies the end time is on the next day. Adjust end_datetime accordingly.
            if end_datetime < start_datetime:
                end_datetime += timedelta(days=1)

            # Ensure end time is strictly after start time
            if end_datetime <= start_datetime:
                raise TypeError("End time must be after start time")

            hours = int(request.data.get("hours_worked"))

            billable = request.data.get("billable")
            if billable not in ["Yes", "No"]:
                raise ValueError("Billable must be Yes or No")

            dept_codes = {"HR": 1, "IT": 2, "Finance": 3}
            dept_id = dept_codes[request.data.get("department")]

            # success shape
            return Response({
                "message": "Timesheet submitted successfully",
                "employee_id": emp_id,
                "employee_name": emp_name,
                "project_code": project_code,
                "task": task,
                "hours": hours,
                "billable": billable,
                "department_id": dept_id,
                "manager_email": manager_email,
            }, status=status.HTTP_201_CREATED)

        except Exception:
            # Return stack trace to SPA for demo visibility
            tb = traceback.format_exc()
            # Also write it to errors.log so your agent picks it up
            with open("errors.log", "w", encoding="utf-8") as f:
                f.write(tb)
            return Response({"status": "error", "trace": tb}, status=400)