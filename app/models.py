import logging
from datetime import datetime, timezone
from typing import List

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from werkzeug.security import check_password_hash
from flask_login import UserMixin
from app.extensions import db


logger = logging.getLogger(__name__)
_password_hasher = PasswordHasher()


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(40), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    orders = db.relationship("Order", backref="user", lazy=True)

    def set_password(self, password: str) -> None:
        self.password_hash = _password_hasher.hash(password)

    def check_password(self, password: str) -> bool:
        try:
            return _password_hasher.verify(self.password_hash, password)
        except VerifyMismatchError:
            if check_password_hash(self.password_hash, password):
                self.set_password(password)
                db.session.commit()
                return True
        except Exception:
            return False
        return False


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------
class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False)

    products = db.relationship("Product", backref="category", lazy=True)


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, default="")
    price = db.Column(db.Numeric(10, 2), nullable=False)
    image_url = db.Column(db.String(255), default="")
    active = db.Column(db.Boolean, default=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relación con la receta (ingredientes necesarios)
    recipe_items = db.relationship("ProductRecipe", backref="product", lazy=True)

    def is_available(self) -> bool:
        """Retorna False si algún ingrediente de la receta tiene stock insuficiente."""
        if not self.recipe_items:
            return True  # Sin receta → siempre disponible
        for recipe in self.recipe_items:
            item = recipe.inventory_item
            if item.stock_current < recipe.quantity_required:
                return False
        return True


# ---------------------------------------------------------------------------
# Receta (tabla de asociación Product ↔ InventoryItem)
# ---------------------------------------------------------------------------
class ProductRecipe(db.Model):
    __tablename__ = "product_recipes"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id"), nullable=False
    )
    inventory_item_id = db.Column(
        db.Integer, db.ForeignKey("inventory_items.id"), nullable=False
    )
    quantity_required = db.Column(db.Float, nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "product_id", "inventory_item_id", name="uq_product_inventory"
        ),
    )


# ---------------------------------------------------------------------------
# Inventario
# ---------------------------------------------------------------------------
class InventoryItem(db.Model):
    __tablename__ = "inventory_items"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    unit = db.Column(db.String(20), default="unidades")
    stock_min = db.Column(db.Integer, default=0)
    stock_current = db.Column(db.Integer, default=0)
    price = db.Column(db.Numeric(10, 2), default=0)
    provider = db.Column(db.String(120), default="")
    active = db.Column(db.Boolean, default=True)

    # Relación inversa: en qué recetas participa este insumo
    recipe_usages = db.relationship("ProductRecipe", backref="inventory_item", lazy=True)


# ---------------------------------------------------------------------------
# Órdenes
# ---------------------------------------------------------------------------
class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status = db.Column(db.String(50), default="pendiente")
    payment_method = db.Column(db.String(50), default="efectivo")
    payment_status = db.Column(db.String(50), default="pendiente")
    total = db.Column(db.Numeric(10, 2), default=0)
    mp_preference_id = db.Column(db.String(120), nullable=True)
    mp_payment_id = db.Column(db.String(120), nullable=True)
    stock_processed = db.Column(db.Boolean, default=False)
    archived = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    items = db.relationship(
        "OrderItem", backref="order", lazy=True, cascade="all, delete-orphan"
    )


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    quantity = db.Column(db.Integer, default=1)

    product = db.relationship("Product")


# ---------------------------------------------------------------------------
# Seed de datos iniciales
# ---------------------------------------------------------------------------
def seed_defaults(admin_username: str, admin_password: str) -> None:
    categories = [
        ("Hamburguesas", "hamburguesas"),
        ("Hot Dogs", "hot-dogs"),
        ("Snacks", "snacks"),
        ("Postres", "postres"),
        ("Bebidas", "bebidas"),
        ("Combos", "combos"),
    ]

    for name, slug in categories:
        exists = Category.query.filter_by(slug=slug).first()
        if not exists:
            db.session.add(Category(name=name, slug=slug))

    admin_user = User.query.filter_by(username=admin_username).first()
    if not admin_user:
        admin_user = User(
            username=admin_username,
            name="Administrador",
            email=f"{admin_username}@local",
            phone="",
            is_admin=True,
        )
        admin_user.set_password(admin_password)
        db.session.add(admin_user)

    db.session.commit()

    # (slug, nombre, descripción, precio, image_url)
    products = [
        ("hamburguesas", "Hamburguesa clásica", "Carne 100% res, queso y vegetales", 60,
         "https://images.unsplash.com/photo-1550547660-d9450f859349?auto=format&fit=crop&w=600&q=80"),
        ("hamburguesas", "Hamburguesa triple", "Triple carne, queso y tocino", 90,
         "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?auto=format&fit=crop&w=600&q=80"),
        ("hamburguesas", "Hamburguesa hawaiana", "Piña, jamón y queso", 85,
         "https://images.unsplash.com/photo-1571091718767-18b5b1457add?auto=format&fit=crop&w=600&q=80"),
        ("snacks", "Papas a la francesa", "Porción mediana", 40,
         "https://images.unsplash.com/photo-1573080496219-bb080dd4f877?auto=format&fit=crop&w=600&q=80"),
        ("snacks", "Alitas buffalo", "6 piezas con salsa", 75,
         "https://images.unsplash.com/photo-1608039829572-25e8182a7554?auto=format&fit=crop&w=600&q=80"),
        ("postres", "Pay de limón", "Rebanada", 45,
         "https://images.unsplash.com/photo-1519915028121-7d3463d20b13?auto=format&fit=crop&w=600&q=80"),
        ("postres", "Pay de moras", "Rebanada", 45,
         "https://images.unsplash.com/photo-1464305795204-6f5bbfc7fb81?auto=format&fit=crop&w=600&q=80"),
        ("bebidas", "Coca-cola", "355 ml", 30,
         "https://images.unsplash.com/photo-1622483767028-3f66f32aef97?auto=format&fit=crop&w=600&q=80"),
        ("bebidas", "Sprite", "355 ml", 30,
         "https://images.unsplash.com/photo-1625772299848-391b6a87d7b3?auto=format&fit=crop&w=600&q=80"),
        ("combos", "Combo clásico", "Hamburguesa + papas + bebida", 120,
         "https://images.unsplash.com/photo-1594212699903-ec8a3eca50f5?auto=format&fit=crop&w=600&q=80"),
    ]

    for slug, name, description, price, image_url in products:
        category = Category.query.filter_by(slug=slug).first()
        if not category:
            continue
        existing = Product.query.filter_by(name=name, category_id=category.id).first()
        if existing:
            # Actualiza imagen si estaba vacía
            if not existing.image_url:
                existing.image_url = image_url
        else:
            db.session.add(
                Product(
                    name=name,
                    description=description,
                    price=price,
                    image_url=image_url,
                    active=True,
                    category_id=category.id,
                )
            )

    db.session.commit()


def seed_extended() -> None:
    """Añade productos gourmet extendidos. Idempotente por nombre."""
    extended_products = [
        # Burgers
        ("hamburguesas", "Truffle Street", "Hamburguesa premium con aceite de trufa y rúcula", 120,
         "https://images.unsplash.com/photo-1553979459-d2229ba7433b?auto=format&fit=crop&w=600&q=80"),
        ("hamburguesas", "Blue Cheese Burger", "Carne angus con queso azul y cebolla caramelizada", 115,
         "https://images.unsplash.com/photo-1572802419224-296b0aeee0d9?auto=format&fit=crop&w=600&q=80"),
        ("hamburguesas", "Veggie Urban", "Medallón de quinoa, aguacate y brotes frescos", 95,
         "https://images.unsplash.com/photo-1520072959219-c595e6cdc07e?auto=format&fit=crop&w=600&q=80"),
        # Hot Dogs
        ("hot-dogs", "Classic Dog", "Salchicha artesanal, mostaza y cebolla crujiente", 55,
         "https://images.unsplash.com/photo-1612392062631-94dd85fa2ddb?auto=format&fit=crop&w=600&q=80"),
        ("hot-dogs", "Chili Cheese Dog", "Salchicha con chili con carne y queso derretido", 85,
         "https://images.unsplash.com/photo-1619740455993-9d701c8bb7c7?auto=format&fit=crop&w=600&q=80"),
        # Sides (Snacks)
        ("snacks", "Truffle Fries", "Papas con aceite de trufa y parmesano", 70,
         "https://images.unsplash.com/photo-1630384060421-cb20d0e0649d?auto=format&fit=crop&w=600&q=80"),
        ("snacks", "Onion Rings Urban", "Aros de cebolla en tempura crujiente", 65,
         "https://images.unsplash.com/photo-1639024471283-03518883512d?auto=format&fit=crop&w=600&q=80"),
        # Drinks
        ("bebidas", "Limonada de Coco", "Limonada fresca con leche de coco y hierbabuena", 45,
         "https://images.unsplash.com/photo-1621263764928-df1444c5e859?auto=format&fit=crop&w=600&q=80"),
        ("bebidas", "Té Helado Artesanal", "Té negro con melocotón y jengibre", 40,
         "https://images.unsplash.com/photo-1556679343-c7306c1976bc?auto=format&fit=crop&w=600&q=80"),
    ]

    for slug, name, description, price, image_url in extended_products:
        category = Category.query.filter_by(slug=slug).first()
        if not category:
            continue
        exists = Product.query.filter_by(name=name, category_id=category.id).first()
        if not exists:
            db.session.add(
                Product(
                    name=name,
                    description=description,
                    price=price,
                    image_url=image_url,
                    active=True,
                    category_id=category.id,
                )
            )

    db.session.commit()


def seed_recipes() -> None:
    """Popula product_recipes con datos predeterminados.

    Crea InventoryItems faltantes con stock_current=50.
    Es idempotente: no duplica registros existentes.
    """
    # (nombre_insumo, cantidad, unidad)
    recipe_map = {
        # Burgers originales
        "Hamburguesa clásica": [("Pan", 1, "pza"), ("Carne de Res", 1, "pza")],
        "Hamburguesa triple": [("Pan", 1, "pza"), ("Carne de Res", 3, "pza")],
        "Hamburguesa hawaiana": [("Pan", 1, "pza"), ("Carne de Res", 1, "pza"), ("Piña", 1, "rodaja"), ("Jamón", 1, "rebanada")],
        # Burgers gourmet
        "Truffle Street": [("Pan", 1, "pza"), ("Carne de Res", 1, "pza"), ("Trufa", 1, "g"), ("Rúcula", 1, "porción")],
        "Blue Cheese Burger": [("Pan", 1, "pza"), ("Carne Angus", 1, "pza"), ("Queso Azul", 1, "porción"), ("Cebolla Caramelizada", 1, "porción")],
        "Veggie Urban": [("Pan", 1, "pza"), ("Medallón de Quinoa", 1, "pza"), ("Aguacate", 1, "pza")],
        # Hot Dogs
        "Classic Dog": [("Pan para Hot Dog", 1, "pza"), ("Salchicha Artesanal", 1, "pza")],
        "Chili Cheese Dog": [("Pan para Hot Dog", 1, "pza"), ("Salchicha Artesanal", 1, "pza"), ("Chili con Carne", 1, "porción"), ("Queso Cheddar", 1, "porción")],
        # Snacks
        "Papas a la francesa": [("Porción de Papas", 1, "porción")],
        "Alitas buffalo": [("Pieza de Pollo", 6, "pza"), ("Salsa Buffalo", 1, "porción")],
        "Truffle Fries": [("Porción de Papas", 1, "porción"), ("Trufa", 1, "g"), ("Parmesano", 1, "porción")],
        "Onion Rings Urban": [("Cebolla", 2, "pza"), ("Tempura", 1, "porción")],
        # Postres
        "Pay de limón": [("Rebanada de Pay", 1, "pza")],
        "Pay de moras": [("Rebanada de Pay", 1, "pza")],
        # Bebidas
        "Coca-cola": [("Unidad de Refresco", 1, "pza")],
        "Sprite": [("Unidad de Refresco", 1, "pza")],
        "Limonada de Coco": [("Limón", 2, "pza"), ("Leche de Coco", 1, "ml"), ("Hierbabuena", 1, "porción")],
        "Té Helado Artesanal": [("Té Negro", 1, "porción"), ("Melocotón", 1, "pza"), ("Jengibre", 1, "g")],
        # Combos
        "Combo clásico": [("Pan", 1, "pza"), ("Carne de Res", 1, "pza"), ("Porción de Papas", 1, "porción"), ("Unidad de Refresco", 1, "pza")],
    }

    for product_name, ingredients in recipe_map.items():
        product = Product.query.filter_by(name=product_name).first()
        if not product:
            continue

        for inv_name, qty, unit in ingredients:
            inv_item = InventoryItem.query.filter_by(name=inv_name).first()
            if not inv_item:
                inv_item = InventoryItem(
                    name=inv_name,
                    unit=unit,
                    stock_current=50,
                    stock_min=5,
                    active=True,
                )
                db.session.add(inv_item)
                db.session.flush()  # obtener id

            exists = ProductRecipe.query.filter_by(
                product_id=product.id, inventory_item_id=inv_item.id
            ).first()
            if not exists:
                db.session.add(
                    ProductRecipe(
                        product_id=product.id,
                        inventory_item_id=inv_item.id,
                        quantity_required=qty,
                    )
                )

    db.session.commit()
