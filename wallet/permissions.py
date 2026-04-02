# wallet/permissions.py
"""
Permisos personalizados para el sistema wallet.
"""
from rest_framework import permissions


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
        if isinstance(obj, dict) and 'wallet_id' in obj:
            from .models import Wallet
            try:
                wallet = Wallet.objects.get(id=obj['wallet_id'])
                return wallet.user == request.user
            except Wallet.DoesNotExist:
                return False
        
        if hasattr(obj, 'user'):
            return obj.user == request.user
        if hasattr(obj, 'wallet'):
            return obj.wallet.user == request.user
        return False


class IsArtist(permissions.BasePermission):
    """
    Permiso: Solo artistas (usuarios que han subido canciones).
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        from api2.models import Song
        return Song.objects.filter(uploaded_by=request.user).exists()


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
        
        from api2.models import Song
        has_songs = Song.objects.filter(uploaded_by=request.user).exists()
        is_verified = getattr(request.user, 'can_withdraw', False)
        
        return has_songs and is_verified


# ============================================================================
# PERMISOS PARA AGENTES (NUEVOS)
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
            return agent.is_active and agent.verified
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
            return agent.is_active
        except Agent.DoesNotExist:
            return False