# artist_dashboard/serializers.py
"""
Serializers para el dashboard del artista.
"""
from rest_framework import serializers


class DashboardSummarySerializer(serializers.Serializer):
    """Serializer para resumen del dashboard"""
    total_sales = serializers.IntegerField()
    total_revenue = serializers.FloatField()
    pending_earnings = serializers.FloatField()
    released_earnings = serializers.FloatField()
    unique_listeners = serializers.IntegerField()
    top_song = serializers.DictField(required=False, allow_null=True)
    calculated_at = serializers.DateTimeField()


class SalesPointSerializer(serializers.Serializer):
    """Serializer para punto de ventas"""
    date = serializers.CharField()
    sales = serializers.IntegerField()
    revenue = serializers.FloatField()
    listeners = serializers.IntegerField()


class SalesOverTimeSerializer(serializers.Serializer):
    """Serializer para ventas en el tiempo"""
    period = serializers.CharField()
    start_date = serializers.DateTimeField()
    end_date = serializers.DateTimeField()
    series = SalesPointSerializer(many=True)
    total_sales = serializers.IntegerField()
    total_revenue = serializers.FloatField()


class TopSongSerializer(serializers.Serializer):
    """Serializer para canción top"""
    id = serializers.IntegerField()
    title = serializers.CharField()
    sales = serializers.IntegerField()
    revenue = serializers.FloatField()
    likes = serializers.IntegerField()
    plays = serializers.IntegerField()
    trend = serializers.CharField()


class AudienceInsightSerializer(serializers.Serializer):
    """Serializer para insight de audiencia"""
    key = serializers.CharField()
    value = serializers.CharField()
    count = serializers.IntegerField()
    percentage = serializers.FloatField()


class ProjectionSerializer(serializers.Serializer):
    """Serializer para proyección"""
    daily_average = serializers.FloatField()
    projected_30_days = serializers.FloatField()
    trend_percentage = serializers.FloatField()
    trend_direction = serializers.CharField()
    confidence = serializers.CharField()
    message = serializers.CharField(required=False, allow_blank=True)


class ExportResponseSerializer(serializers.Serializer):
    """Serializer para exportación"""
    csv_data = serializers.CharField()
    filename = serializers.CharField()
    content_type = serializers.CharField()