# wallet/permissions.py - VERSIÓN CORREGIDA
"""
Permisos personalizados para el sistema wallet.
"""
from rest_framework import permissions
import logging

logger = logging.getLogger(__name__)


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Permiso: Solo el dueño puede modificar, otros solo lectura.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        if hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'wallet'):
            return obj.wallet.user == request.user

        return False


class IsWalletOwner(permissions.BasePermission):
    """
    Permiso: Solo el dueño del wallet puede acceder.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Caso: Diccionario con wallet_id
        if isinstance(obj, dict) and 'wallet_id' in obj:
            from .models import Wallet
            try:
                wallet = Wallet.objects.get(id=obj['wallet_id'])
                return wallet.user == request.user
            except Wallet.DoesNotExist:
                return False

        # Caso: Modelo con atributo user directo
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        # Caso: Modelo con relación wallet
        if hasattr(obj, 'wallet'):
            return obj.wallet.user == request.user
        
        # Caso específico: Transaction
        if hasattr(obj, 'transaction_type') and hasattr(obj, 'wallet'):
            return obj.wallet.user == request.user
        
        return False


class IsArtist(permissions.BasePermission):
    """
    Permiso: Solo artistas (usuarios que han subido canciones).
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        try:
            from api2.models import Song
            return Song.objects.filter(uploaded_by=request.user).exists()
        except Exception:
            # Si api2 no está disponible, verificar por propiedad en user
            return getattr(request.user, 'is_artist', False)


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Permiso: Admin puede todo, otros solo lectura.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_staff


class CanWithdrawFunds(permissions.BasePermission):
    """
    Permiso: Puede retirar dinero (artistas verificados o admin).
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_staff:
            return True

        try:
            from api2.models import Song
            has_songs = Song.objects.filter(uploaded_by=request.user).exists()
        except Exception:
            has_songs = getattr(request.user, 'is_artist', False)

        is_verified = getattr(request.user, 'can_withdraw', False)

        return has_songs and is_verified


# ============================================================================
# PERMISOS PARA AGENTES
# ============================================================================

class IsAgent(permissions.BasePermission):
    """
    Permiso: Solo agentes verificados y activos.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        from .models import Agent
        try:
            agent = Agent.objects.get(user=request.user)
            if not agent.is_active:
                logger.warning(f"Agent {request.user.id} intentó acceder pero está inactivo")
                return False
            if not agent.verified:
                logger.warning(f"Agent {request.user.id} intentó acceder pero no está verificado")
                return False
            return True
        except Agent.DoesNotExist:
            return False


class IsAgentOrAdmin(permissions.BasePermission):
    """
    Permiso: Agente (activo) o administrador.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_staff:
            return True

        from .models import Agent
        try:
            agent = Agent.objects.get(user=request.user)
            if not agent.is_active:
                logger.warning(f"Agent {request.user.id} intentó acceder pero está inactivo")
                return False
            return True
        except Agent.DoesNotExist:
            return False
        
# wallet/permissions.py - AGREGAR AL FINAL

# ============================================================================
# PERMISOS PARA OFICINA (RETIROS)
# ============================================================================

class IsOfficeStaff(permissions.BasePermission):
    """
    Permiso: Solo personal de oficina autenticado y activo.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        from .models import OfficeStaff
        try:
            staff = OfficeStaff.objects.get(user=request.user, is_active=True)
            return True
        except OfficeStaff.DoesNotExist:
            logger.warning(f"Office staff access denied for user {request.user.id}")
            return False


class IsOfficeStaffOrAdmin(permissions.BasePermission):
    """
    Permiso: Personal de oficina (activo) o administrador.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_staff:
            return True
        
        from .models import OfficeStaff
        try:
            staff = OfficeStaff.objects.get(user=request.user, is_active=True)
            return True
        except OfficeStaff.DoesNotExist:
            return False