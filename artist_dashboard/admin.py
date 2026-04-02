# artist_dashboard/admin.py
"""
Panel de administración para el dashboard del artista.
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import ArtistStats, DailyStats, SongStats, AudienceInsight


@admin.register(ArtistStats)
class ArtistStatsAdmin(admin.ModelAdmin):
    list_display = ['artist', 'total_sales', 'total_revenue_display', 'unique_listeners', 'calculated_at']
    list_filter = ['calculated_at']
    search_fields = ['artist__username', 'artist__email']
    readonly_fields = ['calculated_at']
    
    def total_revenue_display(self, obj):
        return f"{obj.total_revenue:,.0f} XAF"
    total_revenue_display.short_description = 'Ingresos'


@admin.register(DailyStats)
class DailyStatsAdmin(admin.ModelAdmin):
    list_display = ['artist', 'date', 'sales_count', 'revenue_display', 'unique_listeners']
    list_filter = ['date', 'artist']
    search_fields = ['artist__username']
    
    def revenue_display(self, obj):
        return f"{obj.revenue:,.0f} XAF"
    revenue_display.short_description = 'Ingresos'


@admin.register(SongStats)
class SongStatsAdmin(admin.ModelAdmin):
    list_display = ['title', 'artist', 'sales_count', 'revenue_display', 'trend']
    list_filter = ['trend', 'artist']
    search_fields = ['title', 'artist__username']
    
    def revenue_display(self, obj):
        return f"{obj.revenue:,.0f} XAF"
    revenue_display.short_description = 'Ingresos'


@admin.register(AudienceInsight)
class AudienceInsightAdmin(admin.ModelAdmin):
    list_display = ['artist', 'insight_type', 'key', 'value', 'count', 'percentage']
    list_filter = ['insight_type', 'artist']
    search_fields = ['artist__username', 'key']