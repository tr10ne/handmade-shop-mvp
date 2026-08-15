from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import json
import os

from api.database import get_db
from api.models import Product, Category, ProductAuction, AuctionBid, ProductStatus


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
    is_auction: bool | None = None


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


@router.put("/{product_id}/images/reorder")
async def reorder_images(product_id: int, images: list[str], db: AsyncSession = Depends(get_db)):
    """Обновить порядок изображений товара"""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    product.images = json.dumps(images)
    await db.commit()
    await db.refresh(product)
    
    return {"ok": True, "images": images}


class ProductReorder(BaseModel):
    """Модель для изменения порядка товаров"""
    product_id: int
    sort_order: int


@router.post("/reorder")
async def reorder_products(items: list[ProductReorder], db: AsyncSession = Depends(get_db)):
    """Массовое изменение порядка товаров"""
    for item in items:
        product = await db.get(Product, item.product_id)
        if product:
            product.sort_order = item.sort_order
    
    await db.commit()
    
    return {"ok": True, "message": f"Обновлено {len(items)} товаров"}


@router.get("/{product_id}/full")
async def get_product_full(product_id: int, db: AsyncSession = Depends(get_db)):
    """Получить полную информацию о товаре включая категорию и аукцион"""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    # Получаем информацию об аукционе если товар на аукционе
    auction_info = None
    if product.is_auction:
        auction_query = select(ProductAuction).where(ProductAuction.product_id == product_id)
        auction_result = await db.execute(auction_query)
        auction = auction_result.scalars().first()
        if auction:
            # Получаем текущую максимальную ставку
            bid_query = select(AuctionBid).where(AuctionBid.auction_id == auction.id).order_by(AuctionBid.amount.desc()).limit(1)
            bid_result = await db.execute(bid_query)
            highest_bid = bid_result.scalars().first()
            
            auction_info = {
                "id": auction.id,
                "start_price": auction.start_price,
                "current_price": highest_bid.amount if highest_bid else auction.start_price,
                "start_time": auction.start_time,
                "end_time": auction.end_time,
                "status": auction.status,
                "winner_id": auction.winner_id,
                "bids_count": len(auction.bids) if hasattr(auction, 'bids') else 0
            }
    
    result = product_to_out(product)
    result_dict = result.model_dump()
    result_dict["auction_info"] = auction_info
    
    return result_dict
