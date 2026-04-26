# wallet/constants.py
"""
Constantes del sistema wallet.
Todas las configuraciones centralizadas aquí.
"""
from decimal import Decimal

# --- TIPOS DE TRANSACCIÓN ---
TRANSACTION_TYPES = [
    ('deposit', 'Recarga'),
    ('purchase', 'Compra'),
    ('refund', 'Reembolso'),
    ('release', 'Liberación a artista'),
    ('gift_sent', 'Regalo enviado'),
    ('gift_received', 'Regalo recibido'),
    ('adjustment', 'Ajuste manual'),
    ('fee', 'Comisión plataforma'),
    ('withdrawal', 'Retiro'),
]

# --- ESTADOS DE TRANSACCIÓN ---
TRANSACTION_STATUS = [
    ('pending', 'Pendiente'),
    ('completed', 'Completada'),
    ('failed', 'Fallida'),
    ('cancelled', 'Cancelada'),
    ('refunded', 'Reembolsada'),
]

# --- MOTIVOS DE RETENCIÓN (HOLD) ---
HOLD_REASONS = [
    ('song_purchase', 'Compra de canción'),
    ('album_purchase', 'Compra de álbum'),
    ('event_ticket', 'Venta de entrada'),
    ('merch_sale', 'Venta de merchandising'),
    ('gift', 'Regalo'),
]

# --- CATEGORÍAS DE CANCIONES Y PRECIOS (GESTIONADOS POR PLATAFORMA) ---
SONG_CATEGORIES = [
    ('standard', 'Estándar', Decimal('100.00')),
    ('hit', 'Éxito/Sencillo popular', Decimal('100.00')),
    ('premium', 'Premium', Decimal('250.00')),
    ('classic', 'Clásico', Decimal('250.00')),
]

# Diccionario para acceso rápido
SONG_PRICE_MAP = {cat[0]: cat[2] for cat in SONG_CATEGORIES}
SONG_CATEGORY_CHOICES = [(cat[0], cat[1]) for cat in SONG_CATEGORIES]

# --- MONEDAS SOPORTADAS ---
CURRENCIES = [
    ('XAF', 'Franco CFA (XAF)'),
    ('EUR', 'Euro (EUR)'),
    ('USD', 'Dólar USD'),
]

# --- PAÍSES Y MONEDA POR DEFECTO ---
COUNTRY_CURRENCY_MAP = {
    'GQ': 'XAF',
    'CM': 'XAF',
    'GA': 'XAF',
    'CG': 'XAF',
    'ES': 'EUR',
    'FR': 'EUR',
    'IT': 'EUR',
    'PT': 'EUR',
    'US': 'USD',
    'GB': 'USD',
}

# --- NOMBRES EMOCIONALES PARA UI ---
WALLET_NAMES = {
    'es': {
        'balance': 'Mis Apoyos',
        'pending': 'En camino',
        'available': 'Disponible',
        'total_deposited': 'Total apoyado',
        'total_spent': 'Total invertido en música',
    },
    'pt': {
        'balance': 'Meus Apoios',
        'pending': 'A caminho',
        'available': 'Disponível',
        'total_deposited': 'Total apoiado',
        'total_spent': 'Total investido',
    },
    'fr': {
        'balance': 'Mes Soutiens',
        'pending': 'En route',
        'available': 'Disponible',
        'total_deposited': 'Total soutenu',
        'total_spent': 'Total investi',
    }
}

# --- LÍMITES DE SEGURIDAD ---
LIMITS = {
    'MAX_BALANCE': Decimal('1000000.00'),
    'MAX_DAILY_DEPOSIT': Decimal('500000.00'),
    'MAX_DAILY_PURCHASE': Decimal('200000.00'),
    'MIN_DEPOSIT': Decimal('100.00'),
    'MAX_PENDING_BALANCE': Decimal('500000.00'),
    'HOLD_DAYS': 7,
    'MAX_DEPOSIT': Decimal('500000.00'),
    'MAX_DAILY_LIMIT': Decimal('500000.00'),
    'MAX_WITHDRAWAL': Decimal('500000.00'),
}

# --- COMISIONES ---
COMMISSIONS = {
    'PLATFORM': Decimal('0.50'),
    'ARTIST': Decimal('0.50'),
}

# --- CÓDIGOS DE ERROR ---
ERROR_CODES = {
    'INSUFFICIENT_FUNDS': 'ERR001',
    'INVALID_AMOUNT': 'ERR002',
    'WALLET_NOT_FOUND': 'ERR003',
    'HOLD_NOT_FOUND': 'ERR004',
    'HOLD_ALREADY_RELEASED': 'ERR005',
    'HOLD_NOT_RELEASABLE': 'ERR006',
    'PURCHASE_FAILED': 'ERR007',
    'UNAUTHORIZED': 'ERR008',
    'LIMIT_EXCEEDED': 'ERR009',
    'CURRENCY_MISMATCH': 'ERR010',
}