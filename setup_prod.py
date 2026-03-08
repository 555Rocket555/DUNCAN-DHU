import sys
import os

# Asegura que Python encuentre la carpeta 'app'
sys.path.append(os.getcwd())

from app import create_app, db
from app.models import User, seed_defaults, seed_extended, seed_recipes

app = create_app()

with app.app_context():
    try:
        print("--- Iniciando Configuración Duncan Dhu ---")
        
        # 0. Recrea la base de datos desde cero (solo desarrollo)
        print("Limpiando base de datos...")
        db.drop_all()
        
        # 1. Crea las tablas físicamente en la base de datos
        print("Creando tablas...")
        db.create_all() 
        
        # 2. Usamos tus funciones de models.py para poblar todo
        print("Poblando categorías, administrador y productos iniciales...")
        seed_defaults("admin", "admin123") 
        
        print("Poblando catálogo gourmet extendido...")
        seed_extended()
        
        print("Configurando recetas e inventario...")
        seed_recipes()
        
        print("--- ¡Despliegue Exitoso! ---")
        print("Puedes entrar con: admin / admin123")
        
    except Exception as e:
        print(f"ERROR DURANTE EL SETUP: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)