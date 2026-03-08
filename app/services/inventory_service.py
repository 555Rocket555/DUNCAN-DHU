import logging
from typing import List

from app.extensions import db
from app.models import Order, ProductRecipe


logger = logging.getLogger(__name__)


class InventoryService:
    """Servicio atómico e idempotente para descuento de stock."""

    @staticmethod
    def deduct_stock(order: Order) -> bool:
        """Descuenta insumos del inventario según las recetas de cada OrderItem.

        Es idempotente: si ``order.stock_processed`` ya es True, no hace nada.
        Retorna True si el descuento se realizó, False si ya estaba procesado.

        Raises:
            ValueError: si el stock resultante sería negativo para algún insumo.
        """
        if order.stock_processed:
            logger.info(
                "Stock ya descontado para la orden #%s, omitiendo.", order.id
            )
            return False

        try:
            for order_item in order.items:
                recipes: List[ProductRecipe] = ProductRecipe.query.filter_by(
                    product_id=order_item.product_id
                ).all()

                for recipe in recipes:
                    inv_item = recipe.inventory_item
                    amount_to_deduct = recipe.quantity_required * order_item.quantity
                    new_stock = inv_item.stock_current - amount_to_deduct

                    if new_stock < 0:
                        raise ValueError(
                            f"Stock insuficiente para '{inv_item.name}': "
                            f"disponible={inv_item.stock_current}, "
                            f"requerido={amount_to_deduct}"
                        )

                    inv_item.stock_current = int(new_stock)

            order.stock_processed = True
            db.session.commit()
            logger.info("Stock descontado correctamente para la orden #%s.", order.id)
            return True

        except ValueError:
            db.session.rollback()
            logger.warning(
                "Descuento de stock fallido para la orden #%s — stock insuficiente.",
                order.id,
            )
            raise
        except Exception:
            db.session.rollback()
            logger.exception(
                "Error inesperado al descontar stock de la orden #%s.", order.id
            )
            raise
