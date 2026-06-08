"""Olist dataset loader and preprocessor for IIAE-BR.

Loads the Brazilian E-Commerce Public Dataset by Olist (Kaggle) and
produces derived metrics used as simulation inputs:

* Mean inter-order arrival time (seconds)
* Product category distribution
* Price distribution (mean, std)
* Seller response-time proxies
* Geographic delivery-time estimation
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class DatasetMetrics:
    """Aggregated metrics derived from the Olist dataset."""

    total_orders: int = 0
    total_items: int = 0
    total_sellers: int = 0
    total_customers: int = 0

    # Timing
    mean_interarrival_s: float = 1.0
    median_interarrival_s: float = 0.8

    # Price
    price_mean: float = 120.0
    price_std: float = 80.0
    freight_mean: float = 20.0

    # Categories (name -> probability)
    category_distribution: Dict[str, float] = field(default_factory=dict)

    # Delivery time (days)
    delivery_days_mean: float = 12.0
    delivery_days_std: float = 8.0

    # Seller processing
    seller_approval_hours_mean: float = 24.0

    # Review score distribution [1..5]
    review_distribution: Dict[int, float] = field(default_factory=dict)

    # Payment
    payment_mean: float = 150.0
    payment_installments_mean: float = 2.5


class OlistDataLoader:
    """Load and preprocess Olist CSV files.

    Parameters:
        data_dir: Directory containing the CSV files.
    """

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self._orders: Optional[pd.DataFrame] = None
        self._items: Optional[pd.DataFrame] = None
        self._products: Optional[pd.DataFrame] = None
        self._sellers: Optional[pd.DataFrame] = None
        self._customers: Optional[pd.DataFrame] = None
        self._payments: Optional[pd.DataFrame] = None
        self._reviews: Optional[pd.DataFrame] = None
        self._categories: Optional[pd.DataFrame] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> DatasetMetrics:
        """Load all CSV files and compute derived metrics."""
        self._load_csvs()
        return self._compute_metrics()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _read(self, filename: str) -> pd.DataFrame:
        path = self.data_dir / filename
        if not path.exists():
            logger.warning("File not found: %s", path)
            return pd.DataFrame()
        df = pd.read_csv(path, low_memory=False)
        logger.info("Loaded %s: %d rows", filename, len(df))
        return df

    def _load_csvs(self) -> None:
        self._orders = self._read("olist_orders_dataset.csv")
        self._items = self._read("olist_order_items_dataset.csv")
        self._products = self._read("olist_products_dataset.csv")
        self._sellers = self._read("olist_sellers_dataset.csv")
        self._customers = self._read("olist_customers_dataset.csv")
        self._payments = self._read("olist_order_payments_dataset.csv")
        self._reviews = self._read("olist_order_reviews_dataset.csv")
        self._categories = self._read("product_category_name_translation.csv")

    def _compute_metrics(self) -> DatasetMetrics:
        m = DatasetMetrics()

        # Counts
        m.total_orders = len(self._orders)
        m.total_items = len(self._items)
        m.total_sellers = self._sellers["seller_id"].nunique() if "seller_id" in self._sellers.columns else 0
        m.total_customers = self._customers["customer_unique_id"].nunique() if "customer_unique_id" in self._customers.columns else 0

        # Inter-arrival time
        if "order_purchase_timestamp" in self._orders.columns:
            ts = pd.to_datetime(self._orders["order_purchase_timestamp"], errors="coerce").dropna().sort_values()
            if len(ts) > 1:
                diffs = ts.diff().dropna().dt.total_seconds()
                m.mean_interarrival_s = float(diffs.mean())
                m.median_interarrival_s = float(diffs.median())

        # Price
        if "price" in self._items.columns:
            m.price_mean = float(self._items["price"].mean())
            m.price_std = float(self._items["price"].std())
        if "freight_value" in self._items.columns:
            m.freight_mean = float(self._items["freight_value"].mean())

        # Category distribution
        if not self._products.empty and "product_category_name" in self._products.columns:
            cat_counts = self._products["product_category_name"].value_counts(normalize=True)
            # Translate if possible
            translation: Dict[str, str] = {}
            if not self._categories.empty:
                translation = dict(
                    zip(
                        self._categories["product_category_name"],
                        self._categories["product_category_name_english"],
                    )
                )
            m.category_distribution = {
                translation.get(k, k): float(v)
                for k, v in cat_counts.head(20).items()
            }

        # Delivery time
        orders = self._orders.copy()
        if {"order_purchase_timestamp", "order_delivered_customer_date"}.issubset(orders.columns):
            orders["purchase"] = pd.to_datetime(orders["order_purchase_timestamp"], errors="coerce")
            orders["delivered"] = pd.to_datetime(orders["order_delivered_customer_date"], errors="coerce")
            delta = (orders["delivered"] - orders["purchase"]).dt.total_seconds() / 86400
            delta = delta.dropna()
            delta = delta[delta > 0]
            if len(delta) > 0:
                m.delivery_days_mean = float(delta.mean())
                m.delivery_days_std = float(delta.std())

        # Seller approval
        if {"order_purchase_timestamp", "order_approved_at"}.issubset(orders.columns):
            orders["approved"] = pd.to_datetime(orders["order_approved_at"], errors="coerce")
            approval = (orders["approved"] - orders["purchase"]).dt.total_seconds() / 3600
            approval = approval.dropna()
            approval = approval[approval >= 0]
            if len(approval) > 0:
                m.seller_approval_hours_mean = float(approval.mean())

        # Reviews
        if "review_score" in self._reviews.columns:
            dist = self._reviews["review_score"].value_counts(normalize=True).sort_index()
            m.review_distribution = {int(k): float(v) for k, v in dist.items()}

        # Payments
        if "payment_value" in self._payments.columns:
            m.payment_mean = float(self._payments["payment_value"].mean())
        if "payment_installments" in self._payments.columns:
            m.payment_installments_mean = float(self._payments["payment_installments"].mean())

        logger.info(
            "Dataset metrics: %d orders, %d items, interarrival=%.2fs, price=R$%.2f±%.2f",
            m.total_orders, m.total_items,
            m.mean_interarrival_s, m.price_mean, m.price_std,
        )
        return m



# ===========================================================================
# Acesso aos dados brutos do Olist (para os casos de uso da arquitetura)
# ===========================================================================

# Raio médio da Terra em km (fórmula de Haversine)
_EARTH_RADIUS_KM = 6371.0


class OlistDataset:
    """Acesso aos dados **brutos** do dataset Olist para os casos de uso.

    Enquanto :class:`OlistDataLoader` produz métricas agregadas para o motor
    estatístico, esta classe expõe os ``DataFrames`` originais e utilitários
    de consulta usados pelos casos de uso (UC1, UC2, UC3) que percorrem as
    cinco camadas da arquitetura IIAE-BR com **dados reais**:

    * :meth:`get_random_order` — seleciona um pedido aleatório completo;
    * :meth:`get_product` / :meth:`get_random_product` — consulta de catálogo;
    * :meth:`is_available` — disponibilidade de estoque (heurística);
    * :meth:`calculate_distance` — distância entre dois CEPs via geolocalização.

    Parameters:
        frames: Dicionário ``nome -> DataFrame`` com as tabelas carregadas.
    """

    def __init__(self, frames: Dict[str, pd.DataFrame]) -> None:
        self.orders = frames.get("orders", pd.DataFrame())
        self.order_items = frames.get("order_items", pd.DataFrame())
        self.products = frames.get("products", pd.DataFrame())
        self.sellers = frames.get("sellers", pd.DataFrame())
        self.customers = frames.get("customers", pd.DataFrame())
        self.geolocation = frames.get("geolocation", pd.DataFrame())
        self.payments = frames.get("payments", pd.DataFrame())
        self.categories = frames.get("categories", pd.DataFrame())

        self._build_indices()

    # ------------------------------------------------------------------
    # Carregamento
    # ------------------------------------------------------------------
    @classmethod
    def load(cls, data_dir: str | Path) -> "OlistDataset":
        """Carrega todos os CSVs do dataset Olist a partir de ``data_dir``.

        Args:
            data_dir: Diretório contendo os arquivos ``olist_*_dataset.csv``.

        Returns:
            Instância de :class:`OlistDataset` com índices prontos para
            consultas rápidas nos casos de uso.
        """
        data_dir = Path(data_dir)

        def _read(name: str) -> pd.DataFrame:
            path = data_dir / name
            if not path.exists():
                logger.warning("Arquivo não encontrado: %s", path)
                return pd.DataFrame()
            df = pd.read_csv(path, low_memory=False)
            logger.info("Carregado %s: %d linhas", name, len(df))
            return df

        frames = {
            "orders": _read("olist_orders_dataset.csv"),
            "order_items": _read("olist_order_items_dataset.csv"),
            "products": _read("olist_products_dataset.csv"),
            "sellers": _read("olist_sellers_dataset.csv"),
            "customers": _read("olist_customers_dataset.csv"),
            "geolocation": _read("olist_geolocation_dataset.csv"),
            "payments": _read("olist_order_payments_dataset.csv"),
            "categories": _read("product_category_name_translation.csv"),
        }
        return cls(frames)

    # ------------------------------------------------------------------
    # Índices internos
    # ------------------------------------------------------------------
    def _build_indices(self) -> None:
        """Constrói índices em memória para consultas O(1)/O(log n)."""
        # Índice de produtos por product_id
        self._product_index: Dict[str, Dict[str, Any]] = {}
        if not self.products.empty and "product_id" in self.products.columns:
            self._product_index = self.products.set_index(
                "product_id"
            ).to_dict("index")
        self._product_ids: List[str] = list(self._product_index.keys())

        # Tradução de categorias (pt -> en)
        self._cat_translation: Dict[str, str] = {}
        if (
            not self.categories.empty
            and "product_category_name" in self.categories.columns
        ):
            self._cat_translation = dict(
                zip(
                    self.categories["product_category_name"],
                    self.categories["product_category_name_english"],
                )
            )

        # Itens por pedido
        self._items_by_order: Dict[str, pd.DataFrame] = {}
        if not self.order_items.empty and "order_id" in self.order_items.columns:
            self._items_by_order = {
                oid: grp for oid, grp in self.order_items.groupby("order_id")
            }
        self._order_ids_with_items: List[str] = list(self._items_by_order.keys())

        # Índice de vendedores e clientes (CEP)
        self._seller_zip: Dict[str, int] = {}
        if not self.sellers.empty and "seller_id" in self.sellers.columns:
            self._seller_zip = dict(
                zip(
                    self.sellers["seller_id"],
                    self.sellers["seller_zip_code_prefix"],
                )
            )
        self._customer_zip: Dict[str, int] = {}
        if not self.customers.empty and "customer_id" in self.customers.columns:
            self._customer_zip = dict(
                zip(
                    self.customers["customer_id"],
                    self.customers["customer_zip_code_prefix"],
                )
            )

        # Geolocalização média por prefixo de CEP
        self._geo_by_zip: Dict[int, Tuple[float, float]] = {}
        if not self.geolocation.empty:
            grp = self.geolocation.groupby("geolocation_zip_code_prefix")[
                ["geolocation_lat", "geolocation_lng"]
            ].mean()
            self._geo_by_zip = {
                int(zip_prefix): (float(row["geolocation_lat"]), float(row["geolocation_lng"]))
                for zip_prefix, row in grp.iterrows()
            }

        # Pedidos como lista para amostragem
        self._customer_by_order: Dict[str, str] = {}
        if not self.orders.empty and {"order_id", "customer_id"}.issubset(
            self.orders.columns
        ):
            self._customer_by_order = dict(
                zip(self.orders["order_id"], self.orders["customer_id"])
            )

    # ------------------------------------------------------------------
    # Consultas de catálogo
    # ------------------------------------------------------------------
    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Retorna os dados brutos de um produto pelo ``product_id``."""
        prod = self._product_index.get(product_id)
        if prod is None:
            return None
        result = dict(prod)
        result["product_id"] = product_id
        # Categoria traduzida (en) quando disponível
        cat = result.get("product_category_name")
        if isinstance(cat, str):
            result["category_en"] = self._cat_translation.get(cat, cat)
        return result

    def get_random_product(
        self, rng: Optional[random.Random] = None
    ) -> Optional[Dict[str, Any]]:
        """Seleciona um produto aleatório do catálogo."""
        if not self._product_ids:
            return None
        rng = rng or random
        pid = rng.choice(self._product_ids)
        return self.get_product(pid)

    def is_available(
        self,
        product_id: str,
        quantity: int = 1,
        rng: Optional[random.Random] = None,
        stock_probability: float = 0.85,
    ) -> bool:
        """Verifica a disponibilidade de um produto (heurística).

        O dataset Olist não possui nível de estoque explícito; modelamos a
        disponibilidade de forma determinística por ``product_id`` (mesma
        resposta para o mesmo produto) combinada com a probabilidade-base de
        estoque do experimento.
        """
        if product_id not in self._product_index:
            return False
        if quantity <= 0:
            return False
        # Pseudo-aleatório determinístico por produto + quantidade
        h = (hash(product_id) % 1000) / 1000.0
        # Quanto maior a quantidade, menor a chance de disponibilidade plena
        threshold = stock_probability * (0.99 ** max(0, quantity - 1))
        return h < threshold

    # ------------------------------------------------------------------
    # Pedidos
    # ------------------------------------------------------------------
    def get_random_order(
        self, rng: Optional[random.Random] = None
    ) -> Optional[Dict[str, Any]]:
        """Retorna um pedido aleatório completo do dataset.

        O pedido inclui ``order_id``, ``customer_id``, itens (produto,
        vendedor, preço, frete) e os CEPs de origem (vendedor) e destino
        (cliente) — tudo a partir de dados reais do Olist.
        """
        if not self._order_ids_with_items:
            return None
        rng = rng or random
        order_id = rng.choice(self._order_ids_with_items)
        return self.get_order_details(order_id)

    def get_order_details(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Monta a visão completa de um pedido a partir das tabelas Olist."""
        items_df = self._items_by_order.get(order_id)
        if items_df is None or items_df.empty:
            return None

        customer_id = self._customer_by_order.get(order_id, "")
        customer_zip = self._customer_zip.get(customer_id)

        items: List[Dict[str, Any]] = []
        total_weight_g = 0.0
        total_price = 0.0
        total_freight = 0.0
        seller_zip: Optional[int] = None

        for _, row in items_df.iterrows():
            product_id = row.get("product_id", "")
            seller_id = row.get("seller_id", "")
            price = float(row.get("price", 0.0) or 0.0)
            freight = float(row.get("freight_value", 0.0) or 0.0)
            prod = self._product_index.get(product_id, {})
            weight = float(prod.get("product_weight_g", 0.0) or 0.0)

            total_price += price
            total_freight += freight
            total_weight_g += weight
            if seller_zip is None:
                seller_zip = self._seller_zip.get(seller_id)

            items.append(
                {
                    "product_id": product_id,
                    "seller_id": seller_id,
                    "price": price,
                    "freight_value": freight,
                    "weight_g": weight,
                    "quantity": int(row.get("order_item_id", 1) or 1),
                }
            )

        return {
            "order_id": order_id,
            "customer_id": customer_id,
            "customer_zip": customer_zip,
            "seller_zip": seller_zip,
            "items": items,
            "n_items": len(items),
            "total_price": round(total_price, 2),
            "total_freight": round(total_freight, 2),
            "total_weight_kg": round(total_weight_g / 1000.0, 3),
        }

    # ------------------------------------------------------------------
    # Geolocalização
    # ------------------------------------------------------------------
    def _coords(self, zip_prefix: Optional[int]) -> Optional[Tuple[float, float]]:
        if zip_prefix is None:
            return None
        try:
            return self._geo_by_zip.get(int(zip_prefix))
        except (ValueError, TypeError):
            return None

    def calculate_distance(
        self, zip1: Optional[int], zip2: Optional[int]
    ) -> float:
        """Calcula a distância (km) entre dois prefixos de CEP via Haversine.

        Usa as coordenadas médias de latitude/longitude da tabela de
        geolocalização do Olist. Caso algum CEP não seja encontrado, retorna
        uma distância média nacional estimada (≈ 600 km).
        """
        c1 = self._coords(zip1)
        c2 = self._coords(zip2)
        if c1 is None or c2 is None:
            return 600.0  # distância média estimada (Brasil) quando ausente

        lat1, lon1 = math.radians(c1[0]), math.radians(c1[1])
        lat2, lon2 = math.radians(c2[0]), math.radians(c2[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(min(1.0, math.sqrt(a)))
        return round(_EARTH_RADIUS_KM * c, 2)

    # ------------------------------------------------------------------
    def summary(self) -> Dict[str, int]:
        """Resumo das tabelas carregadas."""
        return {
            "orders": len(self.orders),
            "order_items": len(self.order_items),
            "products": len(self.products),
            "sellers": len(self.sellers),
            "customers": len(self.customers),
            "geolocation_zips": len(self._geo_by_zip),
        }
