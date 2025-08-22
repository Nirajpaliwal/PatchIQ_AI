from django.urls import path
from .views import TimesheetSPAView, TimesheetEntryView

urlpatterns = [
    path("", TimesheetSPAView.as_view(), name="spa"),
    path("api/timesheet/", TimesheetEntryView.as_view(), name="api-timesheet"),
]
