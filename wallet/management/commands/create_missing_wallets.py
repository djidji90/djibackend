# wallet/management/commands/create_missing_wallets.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from wallet.models import Wallet
from wallet.constants import COUNTRY_CURRENCY_MAP
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Crear wallets para usuarios existentes que no tengan'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simular sin crear wallets'
        )
        parser.add_argument(
            '--user-ids',
            nargs='+',
            type=int,
            help='IDs específicos de usuarios'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Mostrar más detalles'
        )
    
    def handle(self, *args, **options):
        User = get_user_model()
        
        # Filtrar usuarios
        if options['user_ids']:
            users = User.objects.filter(id__in=options['user_ids'])
        else:
            users = User.objects.filter(wallet__isnull=True)
        
        total = users.count()
        self.stdout.write(f"📊 Encontrados {total} usuarios sin wallet")
        
        if options['dry_run']:
            self.stdout.write(self.style.WARNING("🧪 MODO SIMULACIÓN - No se crearán wallets"))
        
        created_count = 0
        error_count = 0
        
        for i, user in enumerate(users, 1):
            try:
                # Determinar currency
                currency = 'XAF'
                if hasattr(user, 'country'):
                    currency = COUNTRY_CURRENCY_MAP.get(user.country, 'XAF')
                
                if options['verbose']:
                    self.stdout.write(f"  Procesando {i}/{total}: {user.email} ({currency})")
                
                if not options['dry_run']:
                    wallet = Wallet.objects.create(
                        user=user,
                        currency=currency,
                        is_active=user.is_active
                    )
                    
                    if options['verbose']:
                        self.stdout.write(
                            self.style.SUCCESS(f"    ✅ Creado wallet ID {wallet.id}")
                        )
                
                created_count += 1
                
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f"    ❌ Error con {user.email}: {str(e)}")
                )
        
        # Resumen
        self.stdout.write("\n" + "="*50)
        
        if options['dry_run']:
            self.stdout.write(
                self.style.SUCCESS(
                    f"🧪 SIMULACIÓN: Se crearían {created_count} wallets"
                )
            )
            if error_count:
                self.stdout.write(
                    self.style.WARNING(f"⚠️  {error_count} errores simulados")
                )
            self.stdout.write("💡 Ejecuta sin --dry-run para crear los wallets reales")
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ COMPLETADO: {created_count} wallets creados exitosamente"
                )
            )
            if error_count:
                self.stdout.write(
                    self.style.ERROR(f"❌ {error_count} errores")
                )
            
            # Verificar si quedan pendientes
            still_missing = User.objects.filter(wallet__isnull=True).count()
            if still_missing > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f"⚠️  Aún hay {still_missing} usuarios sin wallet"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS("🎉 Todos los usuarios tienen wallet ahora!")
                )



            # Verificar si quedan pendientes
            # Verificar si quedan pendientes
            # Verificar si quedan pendientes
