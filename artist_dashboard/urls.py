# artist_dashboard/urls.py
"""
URLs para el dashboard del artista.
"""
from django.urls import path
from . import views

urlpatterns = [
    path('summary/', views.DashboardSummaryView.as_view(), name='dashboard-summary'),
    path('sales/', views.SalesOverTimeView.as_view(), name='dashboard-sales'),
    path('top-songs/', views.TopSongsView.as_view(), name='dashboard-top-songs'),
    path('audience/', views.AudienceInsightsView.as_view(), name='dashboard-audience'),
    path('projection/', views.ProjectionView.as_view(), name='dashboard-projection'),
    path('export/', views.ExportDashboardView.as_view(), name='dashboard-export'),
    path('full/', views.FullDashboardView.as_view(), name='dashboard-full'),
]