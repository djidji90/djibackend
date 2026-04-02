# wallet/management/commands/release_expired_holds.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from wallet.models import Hold
from wallet.services import WalletService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Liberar holds que han expirado automáticamente'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simular sin liberar'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=0,
            help='Liberar holds con más de N días de vencidos'
        )
    
    def handle(self, *args, **options):
        # Calcular fecha límite
        if options['days'] > 0:
            cutoff_date = timezone.now() - timezone.timedelta(days=options['days'])
            holds = Hold.objects.filter(
                is_released=False,
                release_date__lte=cutoff_date
            )
        else:
            holds = Hold.objects.filter(
                is_released=False,
                release_date__lte=timezone.now()
            )
        
        total = holds.count()
        self.stdout.write(f"📊 Encontrados {total} holds para liberar")
        
        if options['dry_run']:
            self.stdout.write(self.style.WARNING("🧪 MODO SIMULACIÓN - No se liberarán"))
            
            # Mostrar muestra
            for hold in holds[:10]:
                self.stdout.write(
                    f"  • {hold.id}: {hold.artist.email} - {hold.amount} XAF "
                    f"(vencido hace {hold.days_until_release * -1} días)"
                )
            
            if total > 10:
                self.stdout.write(f"  ... y {total - 10} más")
            
            return
        
        # Liberar holds
        released = 0
        errors = 0
        
        for hold in holds:
            try:
                WalletService.release_hold(hold.id)
                released += 1
                
                if released % 10 == 0:
                    self.stdout.write(f"  Progreso: {released}/{total}")
                    
            except Exception as e:
                errors += 1
                logger.error(f"Error liberando hold {hold.id}: {str(e)}")
        
        # Resumen
        self.stdout.write("\n" + "="*50)
        self.stdout.write(
            self.style.SUCCESS(f"✅ Liberados: {released} holds")
        )
        if errors:
            self.stdout.write(
                self.style.ERROR(f"❌ Errores: {errors}")
            )
        
        # Verificar pendientes
        still_pending = Hold.objects.filter(
            is_released=False,
            release_date__lte=timezone.now()
        ).count()
        
        if still_pending > 0:
            self.stdout.write(
                self.style.WARNING(f"⚠️  Quedan {still_pending} holds pendientes")
            )