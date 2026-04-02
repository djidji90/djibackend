# artist_dashboard/models.py
"""
Modelos para el dashboard del artista.
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
import uuid


# artist_dashboard/models.py - CORREGIDO

# artist_dashboard/models.py - CORREGIDO

class ArtistStats(models.Model):
    """
    Estadísticas agregadas del artista (cache para rendimiento).
    """
    artist = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='dashboard_stats',
        verbose_name='Artista'
    )
    
    # Totales
    total_sales = models.PositiveIntegerField(
        default=0,
        verbose_name='Total ventas'
    )
    
    total_revenue = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Ingresos totales'
    )
    
    pending_earnings = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Ganancias pendientes'
    )
    
    released_earnings = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Ganancias liberadas'
    )
    
    unique_listeners = models.PositiveIntegerField(
        default=0,
        verbose_name='Oyentes únicos'
    )
    
    # Top canción (permitir NULL)
    top_song_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='ID de canción más vendida'
    )
    
    top_song_title = models.CharField(
        max_length=255,
        blank=True,      # ← PERMITIR VACÍO
        null=True,       # ← PERMITIR NULL
        verbose_name='Canción más vendida'
    )
    
    top_song_sales = models.PositiveIntegerField(
        default=0,
        verbose_name='Ventas de canción top'
    )
    
    # Timestamps
    calculated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Último cálculo'
    )
    
    class Meta:
        verbose_name = 'Estadísticas del artista'
        verbose_name_plural = 'Estadísticas de artistas'
    
    def __str__(self):
        return f"Stats de {self.artist.username}"

class DailyStats(models.Model):
    """
    Estadísticas diarias del artista (para gráficos).
    """
    artist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='daily_stats',
        verbose_name='Artista'
    )
    
    date = models.DateField(
        verbose_name='Fecha'
    )
    
    sales_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Ventas del día'
    )
    
    revenue = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Ingresos del día'
    )
    
    unique_listeners = models.PositiveIntegerField(
        default=0,
        verbose_name='Oyentes únicos del día'
    )
    
    class Meta:
        unique_together = ['artist', 'date']
        ordering = ['-date']
        verbose_name = 'Estadística diaria'
        verbose_name_plural = 'Estadísticas diarias'
    
    def __str__(self):
        return f"{self.artist.username} - {self.date}"


class SongStats(models.Model):
    """
    Estadísticas por canción.
    """
    song_id = models.IntegerField(
        verbose_name='ID de canción'
    )
    
    artist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='song_stats',
        verbose_name='Artista'
    )
    
    title = models.CharField(
        max_length=255,
        verbose_name='Título'
    )
    
    sales_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Ventas'
    )
    
    revenue = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Ingresos'
    )
    
    likes_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Likes'
    )
    
    plays_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Reproducciones'
    )
    
    trend = models.CharField(
        max_length=20,
        choices=[
            ('up', '⬆️ Subiendo'),
            ('down', '⬇️ Bajando'),
            ('stable', '➡️ Estable'),
            ('new', '🆕 Nueva'),
        ],
        default='stable',
        verbose_name='Tendencia'
    )
    
    last_updated = models.DateTimeField(
        auto_now=True,
        verbose_name='Última actualización'
    )
    
    class Meta:
        unique_together = ['artist', 'song_id']
        ordering = ['-sales_count']
        verbose_name = 'Estadística de canción'
        verbose_name_plural = 'Estadísticas de canciones'
    
    def __str__(self):
        return f"{self.title} - {self.sales_count} ventas"


class AudienceInsight(models.Model):
    """
    Insights de audiencia (geográficos, horarios, dispositivos).
    """
    artist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='audience_insights',
        verbose_name='Artista'
    )
    
    insight_type = models.CharField(
        max_length=20,
        choices=[
            ('country', 'Por país'),
            ('city', 'Por ciudad'),
            ('hour', 'Por hora del día'),
            ('device', 'Por dispositivo'),
        ],
        verbose_name='Tipo de insight'
    )
    
    key = models.CharField(
        max_length=100,
        verbose_name='Clave'
    )
    
    value = models.CharField(
        max_length=255,
        verbose_name='Valor'
    )
    
    count = models.PositiveIntegerField(
        default=0,
        verbose_name='Conteo'
    )
    
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Porcentaje'
    )
    
    class Meta:
        unique_together = ['artist', 'insight_type', 'key']
        ordering = ['-count']
        verbose_name = 'Insight de audiencia'
        verbose_name_plural = 'Insights de audiencia'
    
    def __str__(self):
        return f"{self.artist.username} - {self.insight_type}: {self.key} ({self.count})"