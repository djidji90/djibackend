# wallet/checks.py
from django.core.checks import register, Error, Warning, Info
from django.conf import settings


@register
def wallet_system_check(app_configs, **kwargs):
    """
    Verificar que el sistema wallet está correctamente configurado.
    """
    errors = []
    warnings = []
    infos = []
    
    # Verificar que AUTH_USER_MODEL existe
    if not hasattr(settings, 'AUTH_USER_MODEL'):
        errors.append(
            Error(
                'AUTH_USER_MODEL no está configurado',
                hint='Define AUTH_USER_MODEL en settings.py',
                id='wallet.E001',
            )
        )
    
    # Verificar que la app está instalada
    if 'wallet' not in settings.INSTALLED_APPS:
        errors.append(
            Error(
                'La app "wallet" no está en INSTALLED_APPS',
                hint='Agrega "wallet" a INSTALLED_APPS',
                id='wallet.E002',
            )
        )
    
    # Verificar DEBUG en producción (inferido)
    if not settings.DEBUG:
        # En producción, verificar HTTPS
        if not getattr(settings, 'SECURE_SSL_REDIRECT', False):
            warnings.append(
                Warning(
                    'Producción sin HTTPS forzado',
                    hint='Configura SECURE_SSL_REDIRECT = True',
                    id='wallet.W001',
                )
            )
    
    # Info sobre límites
    infos.append(
        Info(
            'Sistema wallet configurado correctamente',
            id='wallet.I001',
        )
    )
    
    return errors + warnings + infos