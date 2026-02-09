from datetime import datetime
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from werkzeug.security import check_password_hash
from flask_login import UserMixin
from app.extensions import db


_password_hasher = PasswordHasher()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(40), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class InventoryItem(db.Model):
    __tablename__ = "inventory_items"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    stock_min = db.Column(db.Integer, default=0)
    stock_current = db.Column(db.Integer, default=0)
    price = db.Column(db.Numeric(10, 2), default=0)
    provider = db.Column(db.String(120), default="")
    active = db.Column(db.Boolean, default=True)


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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship("OrderItem", backref="order", lazy=True, cascade="all, delete-orphan")


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    quantity = db.Column(db.Integer, default=1)

    product = db.relationship("Product")


def seed_defaults(admin_username: str, admin_password: str) -> None:
    categories = [
        ("Hamburguesas", "hamburguesas"),
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

    if not Product.query.first():
        sample_category = Category.query.filter_by(slug="hamburguesas").first()
        if sample_category:
            db.session.add(
                Product(
                    name="Hamburguesa clásica",
                    description="Carne 100% res, queso y vegetales",
                    price=60,
                    image_url="",
                    active=True,
                    category_id=sample_category.id,
                )
            )
            db.session.add(
                Product(
                    name="Hamburguesa triple",
                    description="Triple carne, queso y tocino",
                    price=90,
                    image_url="",
                    active=True,
                    category_id=sample_category.id,
                )
            )
            db.session.commit()
