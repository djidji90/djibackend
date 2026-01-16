# test_r2.py
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tuproyecto.settings')
django.setup()

from api2.r2_client import r2_client, test_r2_connection, get_r2_config

if __name__ == "__main__":
    print("🔍 Probando configuración R2...")
    
    # Mostrar configuración
    config = get_r2_config()
    print("\n📋 Configuración actual:")
    for key, value in config.items():
        print(f"   {key}: {value}")
    
    # Probar conexión
    print("\n🔌 Probando conexión a R2...")
    result = test_r2_connection()
    print(f"   Estado: {result['status']}")
    print(f"   Mensaje: {result['message']}")
    
    if result['status'] == 'success':
        print(f"   Bucket existe: {result.get('bucket_exists', 'N/A')}")
        print(f"   Buckets disponibles: {', '.join(result.get('available_buckets', []))}")