from django.urls import path
from .views import TimesheetSPAView, TimesheetEntryView, ErrorLogView, get_dashboard_data, dashboard_ui

urlpatterns = [
    path("", TimesheetSPAView.as_view(), name="spa"),
    # path("dashboard/", ErrorLogView.as_view(), name="dashboard"),
    path("dashboard-api/", get_dashboard_data, name="dashboard-api"),
    path("dashboard/", dashboard_ui),  # new UI page
    path("timesheet/", TimesheetEntryView.as_view(), name="api-timesheet"),
]
