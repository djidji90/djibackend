# wallet/utils.py - VERSIÓN CORRECTA
"""
Utilidades para el sistema wallet
"""
from decimal import Decimal 
import qrcode
import base64
from io import BytesIO
import logging

logger = logging.getLogger(__name__)


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