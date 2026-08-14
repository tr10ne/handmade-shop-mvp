from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import json
import os

from database import get_db
from models import Product, Category, ProductAuction, AuctionBid, ProductStatus


router = APIRouter(prefix="/products", tags=["products"])


class ProductOut(BaseModel):
    id: int
    title: str
    description: str | None = None
    price: float | None = None
    status: str
    images: list[str] = []
    category_id: int | None = None
    category_name: str | None = None
    sort_order: int = 0
    is_auction: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    
    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    price: float | None = None
    status: str = ProductStatus.IN_STOCK.value
    images: list[str] = []
    category_id: int | None = None
    sort_order: int = 0


class ProductUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    price: float | None = None
    status: str | None = None
    images: list[str] | None = None
    category_id: int | None = None
    sort_order: int | None = None


def product_to_out(p: Product) -> ProductOut:
    category_name = p.category.name if p.category else None
    return ProductOut(
        id=p.id,
        title=p.title,
        description=p.description,
        price=p.price,
        status=p.status,
        images=json.loads(p.images) if p.images else [],
        category_id=p.category_id,
        category_name=category_name,
        sort_order=p.sort_order,
        is_auction=p.is_auction,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("/", response_model=list[ProductOut])
async def list_products(
    status: str | None = None,
    category_id: int | None = None,
    category_slug: str | None = None,
    is_auction: bool | None = None,
    db: AsyncSession = Depends(get_db)
):
    """Получить список товаров с фильтрацией"""
    query = select(Product)
    
    if status:
        query = query.where(Product.status == status)
    if category_id:
        query = query.where(Product.category_id == category_id)
    if category_slug:
        cat_result = await db.execute(select(Category.id).where(Category.slug == category_slug))
        cat_id = cat_result.scalar()
        if cat_id:
            query = query.where(Product.category_id == cat_id)
    if is_auction is not None:
        query = query.where(Product.is_auction == is_auction)
    
    query = query.order_by(Product.sort_order, Product.created_at)
    result = await db.execute(query)
    products = result.scalars().all()
    
    return [product_to_out(p) for p in products]


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    """Получить товар по ID"""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return product_to_out(product)


@router.post("/", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductCreate, db: AsyncSession = Depends(get_db)):
    """Создать новый товар"""
    # Проверка категории если указана
    if payload.category_id:
        category = await db.get(Category, payload.category_id)
        if not category:
            raise HTTPException(status_code=400, detail="Категория не найдена")
    
    product = Product(
        title=payload.title,
        description=payload.description,
        price=payload.price,
        status=payload.status,
        images=json.dumps(payload.images) if payload.images else None,
        category_id=payload.category_id,
        sort_order=payload.sort_order,
    )
    
    db.add(product)
    await db.commit()
    await db.refresh(product)
    
    return product_to_out(product)


@router.put("/{product_id}", response_model=ProductOut)
async def update_product(product_id: int, payload: ProductUpdate, db: AsyncSession = Depends(get_db)):
    """Обновить товар"""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    update_data = payload.model_dump(exclude_unset=True)
    
    # Обработка изображений
    if "images" in update_data and update_data["images"] is not None:
        update_data["images"] = json.dumps(update_data["images"])
    
    for field, value in update_data.items():
        setattr(product, field, value)
    
    await db.commit()
    await db.refresh(product)
    
    return product_to_out(product)


@router.delete("/{product_id}")
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db)):
    """Удалить товар"""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    await db.delete(product)
    await db.commit()
    
    return {"ok": True, "message": "Товар удалён"}


@router.patch("/{product_id}/reorder")
async def reorder_product(product_id: int, sort_order: int, db: AsyncSession = Depends(get_db)):
    """Изменить порядок товара в карусели"""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    product.sort_order = sort_order
    await db.commit()
    await db.refresh(product)
    
    return {"ok": True, "sort_order": sort_order}
