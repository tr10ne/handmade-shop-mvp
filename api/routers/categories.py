from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import json
import os

from api.database import get_db
from api.models import Category, Product


router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryOut(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None = None
    icon: str | None = None
    sort_order: int = 0
    is_active: bool = True
    product_count: int = 0
    
    class Config:
        from_attributes = True


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    icon: str | None = None
    sort_order: int = 0
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    slug: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    icon: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class ProductReorder(BaseModel):
    """Модель для изменения порядка товаров"""
    product_id: int
    sort_order: int


def category_to_out(category: Category, product_count: int = 0) -> CategoryOut:
    return CategoryOut(
        id=category.id,
        name=category.name,
        slug=category.slug,
        description=category.description,
        icon=category.icon,
        sort_order=category.sort_order,
        is_active=category.is_active,
        product_count=product_count,
    )


@router.get("/", response_model=list[CategoryOut])
async def list_categories(include_inactive: bool = False, db: AsyncSession = Depends(get_db)):
    """Получить список всех категорий"""
    query = select(Category)
    if not include_inactive:
        query = query.where(Category.is_active == True)
    query = query.order_by(Category.sort_order, Category.name)
    
    result = await db.execute(query)
    categories = result.scalars().all()
    
    # Получаем количество товаров в каждой категории
    categories_with_counts = []
    for cat in categories:
        count_query = select(func.count(Product.id)).where(Product.category_id == cat.id)
        count_result = await db.execute(count_query)
        product_count = count_result.scalar() or 0
        categories_with_counts.append(category_to_out(cat, product_count))
    
    return categories_with_counts


@router.get("/{category_id}", response_model=CategoryOut)
async def get_category(category_id: int, db: AsyncSession = Depends(get_db)):
    """Получить категорию по ID"""
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    
    count_query = select(func.count(Product.id)).where(Product.category_id == category_id)
    count_result = await db.execute(count_query)
    product_count = count_result.scalar() or 0
    
    return category_to_out(category, product_count)


@router.post("/", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(payload: CategoryCreate, db: AsyncSession = Depends(get_db)):
    """Создать новую категорию"""
    # Проверка на уникальность slug
    existing = await db.get(Category, payload.slug)
    if existing:
        raise HTTPException(status_code=400, detail="Категория с таким slug уже существует")
    
    category = Category(
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        icon=payload.icon,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
    )
    
    db.add(category)
    await db.commit()
    await db.refresh(category)
    
    return category_to_out(category)


@router.put("/{category_id}", response_model=CategoryOut)
async def update_category(category_id: int, payload: CategoryUpdate, db: AsyncSession = Depends(get_db)):
    """Обновить категорию"""
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)
    
    await db.commit()
    await db.refresh(category)
    
    count_query = select(func.count(Product.id)).where(Product.category_id == category_id)
    count_result = await db.execute(count_query)
    product_count = count_result.scalar() or 0
    
    return category_to_out(category, product_count)


@router.delete("/{category_id}")
async def delete_category(category_id: int, db: AsyncSession = Depends(get_db)):
    """Удалить категорию"""
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    
    await db.delete(category)
    await db.commit()
    
    return {"ok": True, "message": "Категория удалена"}


@router.get("/{category_id}/products")
async def get_category_products(category_id: int, db: AsyncSession = Depends(get_db)):
    """Получить все товары категории"""
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    
    query = select(Product).where(Product.category_id == category_id).order_by(Product.sort_order, Product.created_at)
    result = await db.execute(query)
    products = result.scalars().all()
    
    # Преобразование в формат вывода
    product_list = []
    for p in products:
        product_list.append({
            "id": p.id,
            "title": p.title,
            "description": p.description,
            "price": p.price,
            "status": p.status,
            "images": json.loads(p.images) if p.images else [],
            "category_id": p.category_id,
            "sort_order": p.sort_order,
        })
    
    return product_list


@router.post("/{category_id}/products/reorder")
async def reorder_category_products(category_id: int, items: list[ProductReorder], db: AsyncSession = Depends(get_db)):
    """Массовое изменение порядка товаров в категории"""
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    
    for item in items:
        product = await db.get(Product, item.product_id)
        if product and product.category_id == category_id:
            product.sort_order = item.sort_order
    
    await db.commit()
    
    return {"ok": True, "message": f"Обновлено {len(items)} товаров"}
