# api2/tests/test_basic.py
from django.test import TestCase

class TestBasic(TestCase):
    def test_basic_math(self):
        """Test básico para verificar que las pruebas funcionan"""
        self.assertEqual(1 + 1, 2)
    
    def test_basic_string(self):
        """Otro test básico"""
        self.assertTrue("hello".startswith("h"))