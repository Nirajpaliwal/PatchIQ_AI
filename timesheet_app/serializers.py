from rest_framework import serializers

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()

class TimesheetSerializer(serializers.Serializer):
    employee_id = serializers.CharField()
    date = serializers.DateField()
    project = serializers.CharField()
    tasks = serializers.ListField(child=serializers.CharField())
    hours_worked = serializers.FloatField()
    overtime_hours = serializers.FloatField(required=False)
    comments = serializers.CharField(required=False, allow_blank=True)
