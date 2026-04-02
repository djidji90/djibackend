# wallet/apps.py
from django.apps import AppConfig


class WalletConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'wallet'
    verbose_name = 'Sistema de Monedero'
    
    def ready(self):
        """
        Inicializar la app: señales y checks.
        """
        # Importar señales
        import wallet.signals
        
        # Registrar checks del sistema
        from django.core.checks import register, Tags
        from wallet.checks import wallet_system_check
        
        register(wallet_system_check, Tags.security, Tags.models)
        
        print(f"✅ {self.verbose_name} - App lista y señales registradas")