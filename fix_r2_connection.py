# C:\Users\HP\Desktop\ddjiback\fix_r2_connection.py
"""
Script para diagnosticar y solucionar conexión a R2
SIN dependencias externas (solo usa lo que ya tienes)
"""

import os
import sys
import django

sys.path.append('C:\\Users\\HP\\Desktop\\ddjiback')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

import socket
import subprocess
from django.conf import settings

def fix_r2_connection():
    print("\n" + "="*60)
    print("DIAGNÓSTICO DE CONEXIÓN R2")
    print("="*60)
    
    # 1. Verificar endpoint actual
    endpoint = settings.AWS_S3_ENDPOINT_URL
    print(f"\nEndpoint actual: {endpoint}")
    
    # Extraer hostname
    hostname = endpoint.replace('https://', '').replace('http://', '').split('/')[0]
    print(f"Hostname: {hostname}")
    
    # 2. Probar resolución DNS con socket (built-in)
    print("\n1. Probando resolución DNS...")
    try:
        ip = socket.gethostbyname(hostname)
        print(f"   ✅ Resuelve a: {ip}")
    except socket.gaierror as e:
        print(f"   ❌ Error: {e}")
        
        # Intentar con ping (Windows)
        print("\n   Intentando con ping...")
        try:
            result = subprocess.run(
                ['ping', '-n', '1', hostname],
                capture_output=True,
                text=True,
                timeout=5
            )
            if 'TTL=' in result.stdout or 'tiempos' in result.stdout.lower():
                print("   ✅ Ping exitoso (aunque DNS falló)")
            else:
                print("   ❌ Ping también falló")
        except Exception:
            pass
        
        # Solución para Windows
        print("\n" + "="*60)
        print("SOLUCIÓN PARA WINDOWS")
        print("="*60)
        print("\nAgrega esta línea a C:\\Windows\\System32\\drivers\\etc\\hosts:")
        
        # Intentar obtener IP usando nslookup
        try:
            result = subprocess.run(
                ['nslookup', hostname],
                capture_output=True,
                text=True,
                timeout=5
            )
            # Buscar IP en la salida
            import re
            ips = re.findall(r'\d+\.\d+\.\d+\.\d+', result.stdout)
            if ips:
                print(f"\n   {ips[0]} {hostname}")
            else:
                print(f"\n   [BUSCAR_IP] {hostname}")
        except:
            print(f"\n   [BUSCAR_IP] {hostname}")
        
        print("\n   Pasos:")
        print("   1. Abre Notepad como Administrador")
        print("   2. Abre: C:\\Windows\\System32\\drivers\\etc\\hosts")
        print("   3. Agrega la línea de arriba")
        print("   4. Guarda y reinicia")
        return False
    
    # 3. Probar conectividad HTTP
    print("\n2. Probando conectividad HTTP...")
    try:
        import requests
        response = requests.get(f"https://{hostname}", timeout=10, verify=False)
        print(f"   ✅ Conexión HTTP exitosa (status: {response.status_code})")
    except Exception as e:
        print(f"   ❌ Error HTTP: {e}")
        
        # Probar con IP directamente
        if 'ip' in locals():
            try:
                response = requests.get(f"https://{ip}", timeout=10, verify=False)
                print(f"   ✅ Conexión por IP exitosa (status: {response.status_code})")
                print(f"\n   Sugerencia: Agrega al archivo hosts:")
                print(f"   {ip} {hostname}")
            except Exception as e2:
                print(f"   ❌ También falló por IP: {e2}")
    
    # 4. Probar con boto3
    print("\n3. Probando conexión con boto3...")
    try:
        from api2.utils.r2_utils import r2_client
        buckets = r2_client.list_buckets()
        print(f"   ✅ Conexión boto3 exitosa!")
        print(f"   Buckets: {len(buckets.get('Buckets', []))}")
        return True
    except Exception as e:
        print(f"   ❌ Error boto3: {e}")
        
        # Sugerencia de corrección de endpoint
        print("\n   Sugerencia: Corrige el endpoint en settings.py")
        print(f"   Cambiar de: {endpoint}")
        
        # Endpoint corregido sugerido
        import re
        match = re.search(r'([a-f0-9]+)\.r2\.cloudflarestorage\.com', endpoint)
        if match:
            account_id = match.group(1)
            correct_endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
            print(f"   A: {correct_endpoint}")
        return False

if __name__ == "__main__":
    success = fix_r2_connection()
    
    if success:
        print("\n" + "="*60)
        print("✅ CONEXIÓN R2 FUNCIONA CORRECTAMENTE")
        print("="*60)
        print("\nAhora prueba subir una imagen con:")
        print("python test_image_upload_complete.py")
    else:
        print("\n" + "="*60)
        print("❌ HAY PROBLEMAS DE CONEXIÓN")
        print("="*60)
        print("\nSigue las instrucciones arriba para resolverlo")