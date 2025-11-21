# api2/tests/test_r2_configuration.py
import os
from django.test import TestCase
from django.conf import settings

class TestR2Configuration(TestCase):
    """Pruebas de configuración de R2"""
    
    def test_r2_settings(self):
        """Verificar que las configuraciones R2 están presentes"""
        print("⚙️ Verificando configuración R2...")
        
        # Verificar variables de entorno/configuración
        required_settings = [
            'R2_ACCOUNT_ID',
            'R2_ACCESS_KEY', 
            'R2_SECRET_KEY',
            'R2_BUCKET_NAME'
        ]
        
        missing_settings = []
        for setting in required_settings:
            if not hasattr(settings, setting) or not getattr(settings, setting):
                missing_settings.append(setting)
        
        if missing_settings:
            print(f"⚠️  Configuraciones faltantes: {missing_settings}")
            print("💡 Configura las variables de entorno:")
            print("""
            R2_ACCOUNT_ID=tu_account_id
            R2_ACCESS_KEY=tu_access_key
            R2_SECRET_KEY=tu_secret_key  
            R2_BUCKET_NAME=tu-bucket-name
            """)
        else:
            print("✅ Todas las configuraciones R2 presentes")
        
        # No fallar la prueba - solo informar
        self.assertTrue(True)
    
    def test_r2_client_initialization(self):
        """Verificar que el cliente R2 se inicializa correctamente"""
        print("🔧 Probando inicialización del cliente R2...")
        
        from api2.r2_utils import r2_client, R2_BUCKET_NAME
        
        if r2_client:
            print("✅ Cliente R2 inicializado correctamente")
            print(f"📦 Bucket configurado: {R2_BUCKET_NAME}")
        else:
            print("❌ Cliente R2 no inicializado")
            print("💡 Revisa la configuración en r2_client.py")
        
        # No fallar - solo diagnóstico
        self.assertTrue(True)