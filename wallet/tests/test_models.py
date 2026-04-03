# wallet/tests/test_models.py
"""
Tests de modelos - Validación de estructura y constraints
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from decimal import Decimal

from wallet.models import Wallet, Transaction, Office, OfficeStaff, OfficeWithdrawal

User = get_user_model()


class WalletModelTest(TestCase):
    """Tests para el modelo Wallet"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='test123'
        )
    
    def test_create_wallet(self):
        """Crear wallet correctamente"""
        wallet = Wallet.objects.create(
            user=self.user,
            available_balance=Decimal('1000.00')
        )
        self.assertEqual(wallet.user.email, 'test@test.com')
        self.assertEqual(wallet.available_balance, Decimal('1000.00'))
        self.assertEqual(wallet.pending_balance, Decimal('0.00'))
    
    def test_wallet_str_method(self):
        """Test método __str__"""
        wallet = Wallet.objects.create(user=self.user)
        self.assertIn(self.user.email, str(wallet))
    
    def test_total_balance_property(self):
        """Test propiedad total_balance"""
        wallet = Wallet.objects.create(
            user=self.user,
            available_balance=Decimal('1000.00'),
            pending_balance=Decimal('500.00')
        )
        self.assertEqual(wallet.total_balance, Decimal('1500.00'))
    
    def test_can_afford_method(self):
        """Test método can_afford"""
        wallet = Wallet.objects.create(
            user=self.user,
            available_balance=Decimal('1000.00')
        )
        self.assertTrue(wallet.can_afford(Decimal('500.00')))
        self.assertFalse(wallet.can_afford(Decimal('1500.00')))
    
    def test_daily_limit_property(self):
        """Test propiedad daily_limit"""
        wallet = Wallet.objects.create(
            user=self.user,
            custom_daily_limit=Decimal('10000.00')
        )
        self.assertEqual(wallet.daily_limit, Decimal('10000.00'))
        
        # Sin custom limit, usa default
        wallet2 = Wallet.objects.create(user=self.user)
        self.assertIsNotNone(wallet2.daily_limit)


class TransactionModelTest(TestCase):
    """Tests para el modelo Transaction"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='testuser')
        self.wallet = Wallet.objects.create(user=self.user)
    
    def test_create_transaction(self):
        """Crear transacción correctamente"""
        tx = Transaction.objects.create(
            wallet=self.wallet,
            amount=Decimal('100.00'),
            balance_before=Decimal('1000.00'),
            balance_after=Decimal('1100.00'),
            transaction_type='deposit',
            description='Test deposit'
        )
        self.assertIsNotNone(tx.reference)
        self.assertTrue(tx.reference.startswith('TX'))
        self.assertEqual(tx.amount, Decimal('100.00'))
    
    def test_transaction_str_method(self):
        """Test método __str__"""
        tx = Transaction.objects.create(
            wallet=self.wallet,
            amount=Decimal('100.00'),
            balance_before=Decimal('1000.00'),
            balance_after=Decimal('1100.00'),
            transaction_type='deposit'
        )
        self.assertIn(tx.reference, str(tx))
    
    def test_transaction_properties(self):
        """Test propiedades is_income, is_expense, absolute_amount"""
        tx_income = Transaction.objects.create(
            wallet=self.wallet,
            amount=Decimal('100.00'),
            balance_before=Decimal('1000.00'),
            balance_after=Decimal('1100.00'),
            transaction_type='deposit'
        )
        self.assertTrue(tx_income.is_income)
        self.assertFalse(tx_income.is_expense)
        self.assertEqual(tx_income.absolute_amount, Decimal('100.00'))
        
        tx_expense = Transaction.objects.create(
            wallet=self.wallet,
            amount=Decimal('-50.00'),
            balance_before=Decimal('1000.00'),
            balance_after=Decimal('950.00'),
            transaction_type='purchase'
        )
        self.assertTrue(tx_expense.is_expense)
        self.assertEqual(tx_expense.absolute_amount, Decimal('50.00'))
    
    def test_balance_consistency_constraint(self):
        """Test que la consistencia de balance se valida"""
        with self.assertRaises(ValueError):
            Transaction.objects.create(
                wallet=self.wallet,
                amount=Decimal('100.00'),
                balance_before=Decimal('1000.00'),
                balance_after=Decimal('2000.00'),  # Inconsistente
                transaction_type='deposit'
            )


class OfficeModelTest(TestCase):
    """Tests para el modelo Office"""
    
    def setUp(self):
        self.office = Office.objects.create(
            name='Oficina Central',
            address='Calle Principal 123',
            city='Malabo',
            phone='+240 123 456 789',
            manager_name='Juan Pérez'
        )
    
    def test_create_office(self):
        """Crear oficina correctamente"""
        self.assertEqual(self.office.name, 'Oficina Central')
        self.assertEqual(self.office.city, 'Malabo')
        self.assertTrue(self.office.is_active)
    
    def test_office_str_method(self):
        """Test método __str__"""
        self.assertIn('Oficina Central', str(self.office))
        self.assertIn('Malabo', str(self.office))
    
    def test_daily_cache_reset(self):
        """Test reset de cache diario"""
        self.office.today_withdrawn_cached = Decimal('1000.00')
        self.office.last_cache_date = None
        self.office.save()
        
        self.office.reset_daily_cache_if_needed()
        self.assertEqual(self.office.today_withdrawn_cached, Decimal('0.00'))