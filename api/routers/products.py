from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import json

from database import get_db
from models import Product

router = APIRouter(prefix="/products", tags=["products"])

class ProductOut(BaseModel):
    id: int
    title: str
    description: str | None
    price: float | None
    status: str
    images: list[str]
    category_id: int | None

class ProductCreate(BaseModel):
    title: str
    description: str | None = None
    price: float | None = None
    status: str = "in_stock"
    images: list[str] = []
    category_id: int | None = None

def to_out(p: Product) -> ProductOut:
    return ProductOut(
        id=p.id,
        title=p.title,
        description=p.description,
        price=p.price,
        status=p.status,
        images=json.loads(p.images) if p.images else [],
        category_id=p.category_id,
    )

@router.get("/", response_model=list[ProductOut])
async def list_products(status: str | None = None, db: AsyncSession = Depends(get_db)):
    q = select(Product)
    if status:
        q = q.where(Product.status == status)
    result = await db.execute(q)
    return [to_out(p) for p in result.scalars().all()]

@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    p = await db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    return to_out(p)

@router.post("/", response_model=ProductOut)
async def create_product(payload: ProductCreate, db: AsyncSession = Depends(get_db)):
    p = Product(
        title=payload.title,
        description=payload.description,
        price=payload.price,
        status=payload.status,
        images=json.dumps(payload.images),
        category_id=payload.category_id,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return to_out(p)

@router.delete("/{product_id}")
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db)):
    p = await db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    await db.delete(p)
    await db.commit()
    return {"ok": True}