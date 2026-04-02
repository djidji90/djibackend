import os
import subprocess

def create_wallet_structure():
    # Verificar si la app ya existe
    if not os.path.exists('wallet'):
        subprocess.run(['python', 'manage.py', 'startapp', 'wallet'])
    
    # Crear estructura
    os.chdir('wallet')
    
    # Crear directorios
    os.makedirs('management/commands', exist_ok=True)
    
    # Crear archivos __init__.py
    for init_file in ['management/__init__.py', 'management/commands/__init__.py']:
        open(init_file, 'a').close()
    
    # Crear archivos
    files = [
        'signals.py', 'services.py', 'serializers.py',
        'permissions.py', 'pagination.py', 'filters.py',
        'exceptions.py', 'constants.py', 'utils.py',
        'validators.py', 'tests.py'
    ]
    
    for file in files:
        open(file, 'a').close()
    
    print("✅ Estructura de wallet creada exitosamente")

if __name__ == "__main__":
    create_wallet_structure()