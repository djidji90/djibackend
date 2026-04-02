# artist_dashboard/permissions.py
"""
Permisos para el dashboard del artista.
"""
from rest_framework import permissions
from api2.models import Song


class IsArtist(permissions.BasePermission):
    """
    Permiso: Solo artistas (usuarios que han subido canciones).
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Un usuario es artista si ha subido al menos una canción
        return Song.objects.filter(uploaded_by=request.user).exists()