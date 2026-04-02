from django.shortcuts import render

# Create your views here.
# artist_dashboard/views.py
"""
Vistas para el dashboard del artista.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.http import HttpResponse
from .services import DashboardService
from .serializers import (
    DashboardSummarySerializer, SalesOverTimeSerializer,
    TopSongSerializer, AudienceInsightSerializer,
    ProjectionSerializer, ExportResponseSerializer
)
from .permissions import IsArtist


class DashboardSummaryView(APIView):
    """
    Obtener resumen del dashboard.
    GET /api/artist/dashboard/summary/
    """
    permission_classes = [IsAuthenticated, IsArtist]
    
    def get(self, request):
        summary = DashboardService.get_summary(request.user)
        serializer = DashboardSummarySerializer(summary)
        return Response(serializer.data)


class SalesOverTimeView(APIView):
    """
    Obtener ventas en el tiempo.
    GET /api/artist/dashboard/sales/?period=week
    period: day, week, month, year
    """
    permission_classes = [IsAuthenticated, IsArtist]
    
    def get(self, request):
        period = request.query_params.get('period', 'week')
        
        if period not in ['day', 'week', 'month', 'year']:
            period = 'week'
        
        sales_data = DashboardService.get_sales_over_time(request.user, period)
        serializer = SalesOverTimeSerializer(sales_data)
        return Response(serializer.data)


class TopSongsView(APIView):
    """
    Obtener canciones más vendidas.
    GET /api/artist/dashboard/top-songs/?limit=5
    """
    permission_classes = [IsAuthenticated, IsArtist]
    
    def get(self, request):
        limit = int(request.query_params.get('limit', 5))
        limit = min(limit, 20)  # Máximo 20
        
        top_songs = DashboardService.get_top_songs(request.user, limit)
        serializer = TopSongSerializer(top_songs, many=True)
        return Response(serializer.data)


class AudienceInsightsView(APIView):
    """
    Obtener insights de audiencia.
    GET /api/artist/dashboard/audience/?type=country&limit=10
    types: country, city, hour, device
    """
    permission_classes = [IsAuthenticated, IsArtist]
    
    def get(self, request):
        insight_type = request.query_params.get('type', 'country')
        limit = int(request.query_params.get('limit', 10))
        limit = min(limit, 20)
        
        if insight_type not in ['country', 'city', 'hour', 'device']:
            insight_type = 'country'
        
        insights = DashboardService.get_audience_insights(
            request.user, insight_type, limit
        )
        serializer = AudienceInsightSerializer(insights, many=True)
        return Response(serializer.data)


class ProjectionView(APIView):
    """
    Obtener proyección de ganancias.
    GET /api/artist/dashboard/projection/
    """
    permission_classes = [IsAuthenticated, IsArtist]
    
    def get(self, request):
        projection = DashboardService.get_projection(request.user)
        serializer = ProjectionSerializer(projection)
        return Response(serializer.data)


class ExportDashboardView(APIView):
    """
    Exportar datos del dashboard a CSV.
    GET /api/artist/dashboard/export/?period=month
    """
    permission_classes = [IsAuthenticated, IsArtist]
    
    def get(self, request):
        period = request.query_params.get('period', 'month')
        
        if period not in ['day', 'week', 'month', 'year']:
            period = 'month'
        
        csv_data = DashboardService.export_to_csv(request.user, period)
        
        response = HttpResponse(csv_data, content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="dashboard_{request.user.username}_{period}.csv"'
        return response


class FullDashboardView(APIView):
    """
    Obtener todos los datos del dashboard en una sola llamada.
    GET /api/artist/dashboard/full/
    """
    permission_classes = [IsAuthenticated, IsArtist]
    
    def get(self, request):
        summary = DashboardService.get_summary(request.user)
        sales = DashboardService.get_sales_over_time(request.user, 'week')
        top_songs = DashboardService.get_top_songs(request.user, 5)
        audience = DashboardService.get_audience_insights(request.user, 'country', 5)
        projection = DashboardService.get_projection(request.user)
        
        return Response({
            'summary': summary,
            'sales_week': sales,
            'top_songs': top_songs,
            'audience_countries': audience,
            'projection': projection
        })