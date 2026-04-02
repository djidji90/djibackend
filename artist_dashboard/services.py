# artist_dashboard/services.py
"""
Servicios para calcular y obtener estadísticas del dashboard.
"""
import logging
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.core.cache import cache

from .models import ArtistStats, DailyStats, SongStats, AudienceInsight

logger = logging.getLogger(__name__)


# artist_dashboard/services.py - CORREGIDO

class DashboardService:
    """
    Servicio para obtener datos del dashboard del artista.
    """
    
    CACHE_TIMEOUT = 300  # 5 minutos
    
    # ========== MÉTODOS PÚBLICOS ==========
    
    @staticmethod
    def get_summary(artist):
        """Obtener resumen del dashboard."""
        cache_key = f"dashboard_summary_{artist.id}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        try:
            stats = ArtistStats.objects.get(artist=artist)
            summary = {
                'total_sales': stats.total_sales,
                'total_revenue': float(stats.total_revenue),
                'pending_earnings': float(stats.pending_earnings),
                'released_earnings': float(stats.released_earnings),
                'unique_listeners': stats.unique_listeners,
                'top_song': {
                    'id': stats.top_song_id,
                    'title': stats.top_song_title,
                    'sales': stats.top_song_sales
                } if stats.top_song_id else None,
                'calculated_at': stats.calculated_at.isoformat()
            }
        except ArtistStats.DoesNotExist:
            # ✅ CORREGIDO: Llamar al método público
            summary = DashboardService.calculate_and_save(artist)
        
        cache.set(cache_key, summary, DashboardService.CACHE_TIMEOUT)
        return summary
    
    # ... otros métodos públicos ...
    
    # ========== MÉTODO PÚBLICO PARA CÁLCULO ==========
    
    @staticmethod
    def calculate_and_save(artist):
        """
        Calcular estadísticas desde cero y guardar.
        ✅ Este es el método que debe llamarse desde el comando
        """
        from wallet.models import Transaction, Hold
        from api2.models import Song, PlayHistory
        from django.db.models import Sum, Count
        from decimal import Decimal
        
        # Calcular totales
        transactions = Transaction.objects.filter(
            wallet__user=artist,
            transaction_type='purchase',
            status='completed',
            metadata__artist_id=artist.id
        )
        
        total_sales = transactions.count()
        total_revenue = transactions.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        total_revenue = abs(total_revenue)
        
        # Calcular ganancias pendientes
        holds = Hold.objects.filter(
            artist=artist,
            is_released=False
        )
        pending_earnings = holds.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        
        # Calcular ganancias liberadas
        released = Hold.objects.filter(
            artist=artist,
            is_released=True
        )
        released_earnings = released.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        
        # Calcular oyentes únicos
        listeners = PlayHistory.objects.filter(
            song__uploaded_by=artist
        ).values('user').distinct().count()
        
        # Calcular top canción
        top_song = transactions.values('metadata__song_id').annotate(
            count=Count('id')
        ).order_by('-count').first()
        
        top_song_id = None
        top_song_title = ''
        top_song_sales = 0
        
        if top_song and top_song['metadata__song_id']:
            top_song_id = top_song['metadata__song_id']
            top_song_sales = top_song['count']
            try:
                song = Song.objects.get(id=top_song_id)
                top_song_title = song.title
            except Song.DoesNotExist:
                pass
        
        # Guardar estadísticas
        stats, created = ArtistStats.objects.update_or_create(
            artist=artist,
            defaults={
                'total_sales': total_sales,
                'total_revenue': total_revenue,
                'pending_earnings': pending_earnings,
                'released_earnings': released_earnings,
                'unique_listeners': listeners,
                'top_song_id': top_song_id,
                'top_song_title': top_song_title,
                'top_song_sales': top_song_sales,
            }
        )
        
        return {
            'total_sales': stats.total_sales,
            'total_revenue': float(stats.total_revenue),
            'pending_earnings': float(stats.pending_earnings),
            'released_earnings': float(stats.released_earnings),
            'unique_listeners': stats.unique_listeners,
            'top_song': {
                'id': stats.top_song_id,
                'title': stats.top_song_title,
                'sales': stats.top_song_sales
            } if stats.top_song_id else None,
            'calculated_at': stats.calculated_at.isoformat()
        }