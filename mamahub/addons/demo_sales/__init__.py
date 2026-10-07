"""
Demo Sales addon — **one folder = one module**: Flask Blueprint and ``models/`` live in the same package.

Import surface:
  ``from addons.demo_sales import bp`` — register or introspect routes.
  ``from addons.demo_sales.models import SaleOrderRow`` — domain types / repo helpers.
"""
from addons.demo_sales.controllers.routes import bp
__all__ = ['bp']
