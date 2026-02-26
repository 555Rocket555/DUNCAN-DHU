#!/usr/bin/env python
"""Script para inicializar la base de datos en Render"""

import os
import sys

def init_db():
    """Inicializar la base de datos"""
    try:
        from app import create_app, db
        from app.models import seed_defaults
        from flask_migrate import upgrade as flask_db_upgrade
        
        app = create_app()
        
        with app.app_context():
            # Aplicar migraciones pendientes (altera tablas existentes)
            flask_db_upgrade(directory="migrations")
            print("✓ Migraciones aplicadas")

            # Crear todas las tablas
            db.create_all()
            print("✓ Tablas de base de datos creadas/verificadas")
            
            # Seed datos por defecto usando config del app
            admin_username = app.config.get("ADMIN_USERNAME", "admin")
            admin_password = app.config.get("ADMIN_PASSWORD", "admin123")
            
            seed_defaults(admin_username, admin_password)
            print("✓ Base de datos inicializada con datos por defecto")
            
    except Exception as e:
        print(f"✗ Error al inicializar la base de datos: {e}")
        import traceback
        traceback.print_exc()
        # Fallar el deploy evita dejar la app arriba con esquema inconsistente.
        sys.exit(1)

if __name__ == "__main__":
    init_db()

