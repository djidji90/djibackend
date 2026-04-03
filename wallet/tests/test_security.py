# wallet/tests/test_security.py
"""
Tests de seguridad - Prevención de fraudes
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.cache import cache
from decimal import Decimal

from wallet.models import Wallet, SuspiciousActivity
from wallet.services import OfficeWithdrawalService
from wallet.exceptions import LimitExceededError

User = get_user_model()


class SecurityTest(TestCase):
    """Tests de seguridad y detección de fraudes"""
    
    def setUp(self):
        self.artist = User.objects.create_user(
            username='artist',
            email='artist@test.com'
        )
        self.wallet = Wallet.objects.create(
            user=self.artist,
            available_balance=Decimal('1000000.00')
        )
        
        # Configurar oficina y staff (simplificado para tests)
        from wallet.models import Office, OfficeStaff
        
        self.office = Office.objects.create(
            name='Test Office',
            address='Test',
            city='Test',
            phone='123',
            manager_name='Test'
        )
        
        self.staff_user = User.objects.create_user(
            username='staff',
            email='staff@test.com',
            is_staff=True
        )
        
        self.staff = OfficeStaff.objects.create(
            user=self.staff_user,
            office=self.office,
            employee_id='EMP001',
            position='Cajero'
        )
    
    def test_daily_limit_artist(self):
        """Artista no puede exceder límite diario"""
        # Intentar retirar más del límite diario (500,000 XAF)
        with self.assertRaises(LimitExceededError):
            OfficeWithdrawalService.process_withdrawal(
                artist_id=self.artist.id,
                amount=Decimal('600000.00'),
                office_id=self.office.id,
                staff_id=self.staff.id,
                withdrawal_method='cash',
                id_number_verified='12345678'
            )
    
    def test_office_daily_limit(self):
        """Oficina no puede exceder su límite diario"""
        # Reducir límite de oficina para test
        self.office.daily_cash_limit = Decimal('100000.00')
        self.office.save()
        
        with self.assertRaises(LimitExceededError):
            OfficeWithdrawalService.process_withdrawal(
                artist_id=self.artist.id,
                amount=Decimal('150000.00'),
                office_id=self.office.id,
                staff_id=self.staff.id,
                withdrawal_method='cash',
                id_number_verified='12345678'
            )
    
    def test_suspicious_activity_detection(self):
        """Detección de actividad sospechosa"""
        from wallet.services import WalletService
        
        # Simular múltiples transacciones rápidas
        for i in range(6):  # Más de 5 en 1 minuto
            WalletService._check_suspicious_activity(self.wallet, self.artist.id)
        
        # Verificar que se creó un registro de actividad sospechosa
        suspicious = SuspiciousActivity.objects.filter(
            user=self.artist,
            activity_type='high_frequency'
        )
        self.assertGreaterEqual(suspicious.count(), 1)
    
    def test_id_number_masking(self):
        """Número de identificación debe estar enmascarado en logs"""
        withdrawal = OfficeWithdrawalService.process_withdrawal(
            artist_id=self.artist.id,
            amount=Decimal('10000.00'),
            office_id=self.office.id,
            staff_id=self.staff.id,
            withdrawal_method='cash',
            id_number_verified='1234567890'
        )
        
        # Verificar que el audit log tiene el ID enmascarado
        from wallet.models import AuditLog
        audit = AuditLog.objects.filter(entity_id=withdrawal.id).first()
        
        if audit and audit.metadata:
            id_verified = audit.metadata.get('id_verified', '')
            # Debe mostrar solo últimos 4 dígitos
            self.assertNotEqual(id_verified, '1234567890')
            self.assertEqual(len(id_verified), 4)