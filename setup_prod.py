from app import create_app, db
from app.models.user import User

app = create_app()
with app.app_context():
    print("Iniciando configuración de base de datos...")
    db.create_all()  # Crea todas las tablas basadas en tus modelos

    # Crear usuario admin si no existe
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', email='admin@duncandhu.com', name='Administrador', role='admin')
        admin.set_password('admin123') # Cambia esto después en el panel
        db.session.add(admin)
        db.session.commit()
        print("¡Usuario Administrador creado con éxito!")
    else:
        print("El usuario administrador ya existe.")