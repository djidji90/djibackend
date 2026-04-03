# wallet/tests/test_concurrency.py
"""
Tests de concurrencia - Race conditions
"""
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed

from wallet.models import Wallet, Office, OfficeStaff
from wallet.services import OfficeWithdrawalService
from wallet.exceptions import InsufficientFundsError

User = get_user_model()


class ConcurrencyTest(TransactionTestCase):
    """Tests de concurrencia - CRÍTICOS para producción"""
    
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
            manager_name='Test',
            daily_cash_limit=Decimal('5000000.00'),
            max_withdrawal_per_artist=Decimal('200000.00')
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
            position='Cajero',
            daily_operation_limit=Decimal('2000000.00')
        )
    
    def test_concurrent_withdrawals_same_wallet(self):
        """
        TEST CRÍTICO: 10 retiros simultáneos del mismo wallet
        Verifica que no haya sobregiro
        """
        amount = Decimal('150000.00')
        total_attempts = 10
        
        def do_withdrawal(attempt_id):
            try:
                withdrawal = OfficeWithdrawalService.process_withdrawal(
                    artist_id=self.artist.id,
                    amount=amount,
                    office_id=self.office.id,
                    staff_id=self.staff.id,
                    withdrawal_method='cash',
                    id_number_verified='12345678',
                    notes=f'Test {attempt_id}'
                )
                return {'success': True, 'reference': withdrawal.reference}
            except InsufficientFundsError:
                return {'success': False, 'reason': 'insufficient_funds'}
            except Exception as e:
                return {'success': False, 'reason': str(e)}
        
        # Ejecutar en paralelo
        with ThreadPoolExecutor(max_workers=total_attempts) as executor:
            futures = [executor.submit(do_withdrawal, i) for i in range(total_attempts)]
            results = [f.result() for f in as_completed(futures)]
        
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]
        
        # Con saldo de 1,000,000 y retiros de 150,000
        # Máximo 6 retiros exitosos (900,000) o 7 (1,050,000 > saldo)
        self.assertLessEqual(len(successful), 6)
        self.assertGreaterEqual(len(successful), 5)
        
        # Verificar balance final
        self.wallet.refresh_from_db()
        expected_balance = Decimal('1000000.00') - (len(successful) * amount)
        self.assertEqual(self.wallet.available_balance, expected_balance)
        self.assertGreaterEqual(self.wallet.available_balance, 0)
    
    def test_concurrent_withdrawals_different_artists(self):
        """Retiros concurrentes de diferentes artistas - No deben interferir"""
        artists = []
        wallets = []
        
        # Crear 5 artistas
        for i in range(5):
            artist = User.objects.create_user(
                username=f'artist_{i}',
                email=f'artist_{i}@test.com'
            )
            wallet = Wallet.objects.create(
                user=artist,
                available_balance=Decimal('200000.00')
            )
            artists.append(artist)
            wallets.append(wallet)
        
        def withdraw_for_artist(artist_id, wallet_id):
            return OfficeWithdrawalService.process_withdrawal(
                artist_id=artist_id,
                amount=Decimal('50000.00'),
                office_id=self.office.id,
                staff_id=self.staff.id,
                withdrawal_method='cash',
                id_number_verified='12345678'
            )
        
        # Ejecutar retiros concurrentes para cada artista
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(withdraw_for_artist, a.id, w.id)
                for a, w in zip(artists, wallets)
            ]
            results = [f.result() for f in as_completed(futures)]
        
        # Todos deben ser exitosos
        self.assertEqual(len(results), 5)
        
        # Verificar balances
        for wallet in wallets:
            wallet.refresh_from_db()
            self.assertEqual(wallet.available_balance, Decimal('150000.00'))
    
    def test_race_condition_prevention(self):
        """
        Test que verifica que los locks previenen race conditions
        Simula dos retiros casi simultáneos que juntos exceden el saldo
        """
        amount = Decimal('600000.00')  # Dos retiros exceden saldo de 1,000,000
        
        def fast_withdrawal():
            try:
                withdrawal = OfficeWithdrawalService.process_withdrawal(
                    artist_id=self.artist.id,
                    amount=amount,
                    office_id=self.office.id,
                    staff_id=self.staff.id,
                    withdrawal_method='cash',
                    id_number_verified='12345678'
                )
                return True
            except InsufficientFundsError:
                return False
        
        # Ejecutar dos veces muy rápido
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(fast_withdrawal) for _ in range(2)]
            results = [f.result() for f in as_completed(futures)]
        
        # Solo uno debe tener éxito (el primero)
        self.assertEqual(sum(results), 1)
        
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.available_balance, Decimal('400000.00'))