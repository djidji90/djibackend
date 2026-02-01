# tests/test_upload_urls.py
from django.test import TestCase
from django.urls import reverse, resolve
from api2.views import (
    DirectUploadRequestView, UploadConfirmationView,
    DirectUploadStatusView, UploadCancellationView,
    UserUploadQuotaView, UploadAdminDashboardView,
    UploadStatsView, CleanupExpiredUploadsView,
    CheckOrphanedFilesView
)

class UploadURLTests(TestCase):
    
    def test_direct_upload_request_url_resolves(self):
        """Verifica que la URL de solicitud de upload resuelve correctamente"""
        url = reverse('direct-upload-request')
        self.assertEqual(url, '/api2/upload/direct/request/')
        
        resolved = resolve(url)
        self.assertEqual(resolved.func.view_class, DirectUploadRequestView)
    
    def test_upload_confirmation_url_resolves(self):
        """Verifica que la URL de confirmación resuelve correctamente"""
        url = reverse('direct-upload-confirm', args=['550e8400-e29b-41d4-a716-446655440000'])
        self.assertEqual(
            url, 
            '/api2/upload/direct/confirm/550e8400-e29b-41d4-a716-446655440000/'
        )
        
        resolved = resolve(url)
        self.assertEqual(resolved.func.view_class, UploadConfirmationView)
    
    def test_upload_status_url_resolves(self):
        """Verifica que la URL de estado resuelve correctamente"""
        url = reverse('direct-upload-status', args=['550e8400-e29b-41d4-a716-446655440000'])
        self.assertEqual(
            url,
            '/api2/upload/direct/status/550e8400-e29b-41d4-a716-446655440000/'
        )
        
        resolved = resolve(url)
        self.assertEqual(resolved.func.view_class, DirectUploadStatusView)
    
    def test_upload_quota_url_resolves(self):
        """Verifica que la URL de cuota resuelve correctamente"""
        url = reverse('user-upload-quota')
        self.assertEqual(url, '/api2/upload/quota/')
        
        resolved = resolve(url)
        self.assertEqual(resolved.func.view_class, UserUploadQuotaView)
    
    def test_admin_dashboard_url_resolves(self):
        """Verifica que la URL del dashboard admin resuelve correctamente"""
        url = reverse('upload-admin-dashboard')
        self.assertEqual(url, '/api2/admin/uploads/')
        
        resolved = resolve(url)
        self.assertEqual(resolved.func.view_class, UploadAdminDashboardView)
    
    def test_all_upload_urls_exist(self):
        """Verifica que todas las URLs del sistema de upload existen"""
        urls_to_test = [
            ('direct-upload-request', []),
            ('user-upload-quota', []),
            ('upload-admin-dashboard', []),
            ('upload-stats', []),
            ('cleanup-expired-uploads', []),
            ('check-orphaned-files', []),
        ]
        
        for name, args in urls_to_test:
            try:
                url = reverse(name, args=args)
                self.assertIsNotNone(url)
            except Exception as e:
                self.fail(f"URL {name} no encontrada: {str(e)}")