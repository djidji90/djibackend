"""
python manage.py update_playlists
Actualiza las playlists curadas según su algoritmo y frecuencia.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import F
from api2.models import CuratedPlaylist, CuratedPlaylistSong, Song
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Actualiza playlists curadas automáticas'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Forzar actualización aunque no estén desactualizadas')
        parser.add_argument('--slug', type=str, help='Actualizar solo una playlist por slug')

    def handle(self, *args, **options):
        force = options.get('force', False)
        slug  = options.get('slug')

        qs = CuratedPlaylist.objects.filter(is_active=True).exclude(algorithm='manual')
        if slug:
            qs = qs.filter(slug=slug)

        updated = 0
        for playlist in qs:
            if not force and not playlist.is_outdated:
                self.stdout.write(f"  Saltando (al día): {playlist.name}")
                continue

            self.stdout.write(f"Actualizando: {playlist.name}")
            try:
                songs = self._get_songs(playlist)
                if len(songs) < playlist.min_songs:
                    self.stdout.write(f"  Pocas canciones ({len(songs)} < {playlist.min_songs}), saltando")
                    continue

                self._replace_songs(playlist, songs)
                CuratedPlaylist.objects.filter(pk=playlist.pk).update(
                    last_calculated_at=timezone.now(),
                    song_count=len(songs),
                )
                updated += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ {len(songs)} canciones"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ {e}"))
                logger.error(f"Error actualizando playlist {playlist.id}: {e}")

        self.stdout.write(self.style.SUCCESS(f"\nListo: {updated} playlists actualizadas"))

    # ------------------------------------------------------------------

    def _get_songs(self, playlist):
        algo = playlist.algorithm
        if algo == 'trending':
            return self._trending(playlist)
        if algo == 'new_releases':
            return self._new_releases(playlist)
        if algo == 'top_genre':
            return self._top_genre(playlist)
        if algo == 'hybrid':
            return self._trending(playlist)   # híbrido = trending como base
        return []

    def _base_qs(self, playlist):
        qs = Song.objects.filter(is_public=True)
        if playlist.target_genres:
            qs = qs.filter(genre__in=playlist.target_genres)
        if playlist.target_country:
            # Filtro por país si el modelo Song lo soporta en el futuro
            pass
        return qs

    def _trending(self, playlist):
        """Canciones más populares por plays + likes."""
        qs = self._base_qs(playlist).filter(plays_count__gt=0)
        # Score simple sin Count() extra para evitar problemas de anotación mixta
        qs = qs.order_by('-plays_count', '-likes_count')
        return list(qs[:playlist.max_songs])

    def _new_releases(self, playlist):
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(days=7)
        qs = self._base_qs(playlist).filter(created_at__gte=cutoff).order_by('-created_at')
        return list(qs[:playlist.max_songs])

    def _top_genre(self, playlist):
        if not playlist.target_genres:
            return []
        qs = self._base_qs(playlist).order_by('-plays_count', '-likes_count')
        return list(qs[:playlist.max_songs])

    def _replace_songs(self, playlist, songs):
        """DELETE + bulk_create atómico."""
        from django.db import transaction
        with transaction.atomic():
            CuratedPlaylistSong.objects.filter(playlist=playlist).delete()
            CuratedPlaylistSong.objects.bulk_create([
                CuratedPlaylistSong(
                    playlist=playlist,
                    song=song,
                    position=i,
                    score=float(song.plays_count),
                )
                for i, song in enumerate(songs)
            ])