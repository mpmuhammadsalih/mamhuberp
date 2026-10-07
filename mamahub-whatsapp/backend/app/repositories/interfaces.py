"""Repository interfaces so Oracle ERP sources can replace local implementations later."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional, Protocol


class ProductRepository(Protocol):
    def search(self, query: str, *, limit: int = 20, location_code: int = 1) -> List[dict[str, Any]]:
        ...

    def get_by_code(self, itemcode: str, *, location_code: int = 1) -> Optional[dict[str, Any]]:
        ...


class CustomerRepository(Protocol):
    def get_by_whatsapp(self, whatsapp_number: str) -> Optional[Any]:
        ...

    def create_from_whatsapp(self, whatsapp_number: str, name: str, profile_image: Optional[str] = None) -> Any:
        ...


class OrderRepository(Protocol):
    def create(self, **kwargs: Any) -> Any:
        ...

    def get(self, order_id: int) -> Optional[Any]:
        ...


class ErpCustomerLookup(ABC):
    """Optional lookup against Oracle CUSTOMER master."""

    @abstractmethod
    def find_by_mobile(self, mobile: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError
