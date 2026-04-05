# wallet/utils.py - VERSIÓN COMPLETA (agregar al final)

"""
Utilidades para el sistema wallet
"""
from decimal import Decimal 
import qrcode
import base64
from io import BytesIO
import logging
import hashlib
from django.core.cache import cache
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


# ============================================
# QR CODE FUNCTIONS (YA TIENES)
# ============================================

def generate_qr_code(data, size=200):
    """
    Genera un código QR en formato base64.
    """
    try:
        box_size = max(5, size // 20)

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=box_size,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        if img.size[0] != size:
            img = img.resize((size, size))

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        return f"data:image/png;base64,{img_base64}"

    except Exception as e:
        logger.error(f"Error generating QR code: {e}")
        return None


def generate_qr_for_code(code, amount, currency):
    """Genera QR con información del código."""
    qr_data = f"DJIMUSIC://REDEEM?code={code}&amount={amount}&currency={currency}"
    return generate_qr_code(qr_data)


def get_qr_data_url(code, amount, currency):
    """Obtiene URL de datos del QR."""
    return f"DJIMUSIC://REDEEM?code={code}&amount={amount}&currency={currency}"


def calculate_agent_commission(amount, agent_type='standard'):
    """
    Calcula comisión para agente según tipo.
    
    Tipos:
    - standard: 3%
    - premium: 4%
    - vip: 5%
    """
    commission_rates = {
        'standard': Decimal('0.03'),
        'premium': Decimal('0.04'),
        'vip': Decimal('0.05'),
    }
    rate = commission_rates.get(agent_type, Decimal('0.03'))
    return (amount * rate).quantize(Decimal('0.01'))


# ============================================
# IDEMPOTENCY FUNCTIONS (NUEVAS)
# ============================================

def _get_idempotency_key(request, operation, user_id, *args):
    """
    Genera una clave de idempotencia para evitar transacciones duplicadas.
    
    Args:
        request: Django request object
        operation: Nombre de la operación (ej: 'purchase', 'deposit')
        user_id: ID del usuario
        *args: Argumentos adicionales (ej: song_id)
    
    Returns:
        str: Clave de idempotencia
    """
    # Intentar obtener del header
    idempotency_key = request.headers.get('X-Idempotency-Key')
    
    if idempotency_key:
        return idempotency_key
    
    # Generar basada en la operación y usuario
    data = f"{operation}:{user_id}:{':'.join(str(a) for a in args)}"
    return hashlib.sha256(data.encode()).hexdigest()[:32]


def _check_idempotency(key, wallet_id):
    """
    Verificar si ya existe una transacción con esta clave.
    
    Args:
        key: Clave de idempotencia
        wallet_id: ID del wallet
    
    Returns:
        Transaction or None
    """
    cache_key = f"idempotency:{key}:{wallet_id}"
    reference = cache.get(cache_key)
    
    if reference:
        try:
            from .models import Transaction
            return Transaction.objects.get(reference=reference)
        except Transaction.DoesNotExist:
            pass
    
    return None


def _store_idempotency(key, wallet_id, reference):
    """
    Almacenar referencia de transacción para idempotencia.
    
    Args:
        key: Clave de idempotencia
        wallet_id: ID del wallet
        reference: Referencia de la transacción
    """
    cache_key = f"idempotency:{key}:{wallet_id}"
    cache.set(cache_key, reference, timeout=86400)  # 24 horas


# ============================================
# VALIDATION FUNCTIONS (NUEVAS)
# ============================================

def _validate_content_type(request):
    """
    Validar que el Content-Type sea application/json.
    
    Args:
        request: Django request object
    
    Returns:
        Response or None (None significa válido)
    """
    content_type = request.content_type
    
    if content_type != 'application/json':
        return Response(
            {
                'error': 'invalid_content_type',
                'message': 'Se requiere Content-Type: application/json',
                'received': content_type
            },
            status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        )
    
    return None


def _get_client_ip(request):
    """
    Obtiene la IP real del cliente considerando proxies.
    
    Args:
        request: Django request object
    
    Returns:
        str: Dirección IP del cliente
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
    
    return ip


# ============================================
# AMOUNT VALIDATION (NUEVA)
# ============================================

def validate_amount(amount, min_amount=100, max_amount=1000000):
    """
    Valida que el monto esté dentro de los límites.
    
    Args:
        amount: Monto a validar
        min_amount: Monto mínimo permitido
        max_amount: Monto máximo permitido
    
    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        amount_decimal = Decimal(str(amount))
    except Exception:
        return False, "Monto inválido"
    
    if amount_decimal <= 0:
        return False, "El monto debe ser mayor a cero"
    
    if amount_decimal < min_amount:
        return False, f"El monto mínimo es {min_amount} XAF"
    
    if amount_decimal > max_amount:
        return False, f"El monto máximo es {max_amount} XAF"
    
    return True, None