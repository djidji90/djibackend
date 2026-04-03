# wallet/tests/test_idempotency.py
"""
Tests de idempotencia - Prevención de duplicados
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed

from wallet.models import Wallet, Office, OfficeStaff, OfficeWithdrawal
from wallet.services import OfficeWithdrawalService

User = get_user_model()


class IdempotencyTest(TestCase):
    """Tests de idempotencia"""
    
    def setUp(self):
        self.artist = User.objects.create_user(
            username='artist',
            email='artist@test.com'
        )
        self.wallet = Wallet.objects.create(
            user=self.artist,
            available_balance=Decimal('1000000.00')
        )
        
        self.office = Office.objects.create(
            name='Oficina Test',
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
    
    def test_idempotency_key_prevents_duplicates(self):
        """Misma idempotency key no crea duplicados"""
        key = "unique-test-key-12345"
        amount = Decimal('50000.00')
        
        # Primera solicitud
        first = OfficeWithdrawalService.process_withdrawal(
            artist_id=self.artist.id,
            amount=amount,
            office_id=self.office.id,
            staff_id=self.staff.id,
            withdrawal_method='cash',
            id_number_verified='12345678',
            idempotency_key=key
        )
        
        # Segunda solicitud (misma key)
        second = OfficeWithdrawalService.process_withdrawal(
            artist_id=self.artist.id,
            amount=amount,
            office_id=self.office.id,
            staff_id=self.staff.id,
            withdrawal_method='cash',
            id_number_verified='12345678',
            idempotency_key=key
        )
        
        # Debe ser el mismo objeto
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.reference, second.reference)
        
        # Solo debe haber un registro
        count = OfficeWithdrawal.objects.filter(idempotency_key=key).count()
        self.assertEqual(count, 1)
        
        # El balance se descontó solo una vez
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.available_balance, Decimal('950000.00'))
    
    def test_different_keys_create_different_withdrawals(self):
        """Claves diferentes crean retiros diferentes"""
        key1 = "key-1"
        key2 = "key-2"
        amount = Decimal('30000.00')
        
        withdrawal1 = OfficeWithdrawalService.process_withdrawal(
            artist_id=self.artist.id,
            amount=amount,
            office_id=self.office.id,
            staff_id=self.staff.id,
            withdrawal_method='cash',
            id_number_verified='12345678',
            idempotency_key=key1
        )
        
        withdrawal2 = OfficeWithdrawalService.process_withdrawal(
            artist_id=self.artist.id,
            amount=amount,
            office_id=self.office.id,
            staff_id=self.staff.id,
            withdrawal_method='cash',
            id_number_verified='12345678',
            idempotency_key=key2
        )
        
        self.assertNotEqual(withdrawal1.id, withdrawal2.id)
        self.assertNotEqual(withdrawal1.reference, withdrawal2.reference)
    
    def test_concurrent_same_key(self):
        """Múltiples solicitudes concurrentes con misma key"""
        key = "concurrent-test-key"
        amount = Decimal('25000.00')
        
        def make_request():
            return OfficeWithdrawalService.process_withdrawal(
                artist_id=self.artist.id,
                amount=amount,
                office_id=self.office.id,
                staff_id=self.staff.id,
                withdrawal_method='cash',
                id_number_verified='12345678',
                idempotency_key=key
            )
        
        # Ejecutar 5 solicitudes concurrentes
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(5)]
            results = [f.result() for f in as_completed(futures)]
        
        # Todas deben devolver la misma referencia
        references = [r.reference for r in results]
        self.assertEqual(len(set(references)), 1)
        
        # Solo debe haber un registro
        count = OfficeWithdrawal.objects.filter(idempotency_key=key).count()
        self.assertEqual(count, 1)