# artist_dashboard/management/commands/update_dashboard_stats.py - CORREGIDO

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from artist_dashboard.services import DashboardService
from artist_dashboard.tasks import update_all_artist_stats

User = get_user_model()


class Command(BaseCommand):
    help = 'Actualiza estadísticas del dashboard de artistas'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--artist',
            type=str,
            help='Username del artista (opcional)'
        )
        parser.add_argument(
            '--async',
            action='store_true',
            help='Ejecutar como tarea Celery asíncrona'
        )
    
    def handle(self, *args, **options):
        if options['artist']:
            try:
                artist = User.objects.get(username=options['artist'])
                
                if options['async']:
                    from artist_dashboard.tasks import update_artist_stats
                    update_artist_stats.delay(artist.id)
                    self.stdout.write(
                        self.style.SUCCESS(f"Tarea encolada para {artist.username}")
                    )
                else:
                    try:
                        # ✅ CORREGIDO: Usar método público
                        DashboardService.calculate_and_save(artist)
                        self.stdout.write(
                            self.style.SUCCESS(f"✅ Estadísticas actualizadas para {artist.username}")
                        )
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f"❌ Error actualizando {artist.username}: {e}")
                        )
                    
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Artista {options['artist']} no encontrado")
                )
        else:
            if options['async']:
                update_all_artist_stats.delay()
                self.stdout.write(
                    self.style.SUCCESS("Tarea encolada para todos los artistas")
                )
            else:
                count = 0
                errors = 0
                artists = User.objects.filter(uploaded_songs__isnull=False).distinct()
                
                for artist in artists:
                    try:
                        # ✅ CORREGIDO: Usar método público
                        DashboardService.calculate_and_save(artist)
                        count += 1
                        if count % 10 == 0:
                            self.stdout.write(f"Procesados {count} artistas...")
                    except Exception as e:
                        errors += 1
                        self.stdout.write(
                            self.style.ERROR(f"❌ Error con {artist.username}: {e}")
                        )
                
                self.stdout.write(
                    self.style.SUCCESS(f"✅ Estadísticas actualizadas para {count} artistas")
                )
                if errors:
                    self.stdout.write(
                        self.style.WARNING(f"⚠️ {errors} errores")
                    )