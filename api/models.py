from sqlalchemy import Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timedelta
import enum
from api.database import Base


class OrderStatus(str, enum.Enum):
    NEW = "new"
    CONFIRMED = "confirmed"
    PAID = "paid"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ProductStatus(str, enum.Enum):
    IN_STOCK = "in_stock"
    ORDER = "order"
    AUCTION = "auction"
    SOLD = "sold"
    RESERVED = "reserved"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(200))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Связи
    orders: Mapped[list["Order"]] = relationship(back_populates="user", lazy="select")
    bids: Mapped[list["AuctionBid"]] = relationship(back_populates="user", lazy="select")


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Путь к иконке категории
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Связи
    products: Mapped[list["Product"]] = relationship(back_populates="category", lazy="select", cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=ProductStatus.IN_STOCK.value)
    images: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON-строка списка путей
    sort_order: Mapped[int] = mapped_column(Integer, default=0)  # Для управления порядком в карусели
    is_auction: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    category: Mapped["Category"] = relationship(back_populates="products", lazy="joined")
    auction: Mapped["ProductAuction"] = relationship(back_populates="product", uselist=False, cascade="all, delete-orphan")
    order_items: Mapped[list["Order"]] = relationship(back_populates="product", lazy="select")


class ProductAuction(Base):
    """Модель аукциона для товара"""
    __tablename__ = "product_auctions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    start_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_bid: Mapped[float] = mapped_column(Float, nullable=True)
    min_bid_increment: Mapped[float] = mapped_column(Float, default=100.0)  # Минимальный шаг ставки
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, ended, sold
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Связи
    product: Mapped["Product"] = relationship(back_populates="auction", lazy="joined")
    bids: Mapped[list["AuctionBid"]] = relationship(back_populates="auction", lazy="select", cascade="all, delete-orphan")


class AuctionBid(Base):
    """Модель ставки на аукционе"""
    __tablename__ = "auction_bids"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    auction_id: Mapped[int] = mapped_column(ForeignKey("product_auctions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    tg_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Для пользователей без аккаунта
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Связи
    auction: Mapped["ProductAuction"] = relationship(back_populates="bids", lazy="joined")
    user: Mapped["User"] = relationship(back_populates="bids", lazy="joined")


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    customer_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=OrderStatus.NEW.value)
    total_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    user: Mapped["User"] = relationship(back_populates="orders", lazy="joined")
    product: Mapped["Product"] = relationship(back_populates="order_items", lazy="joined")