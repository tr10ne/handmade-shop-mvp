from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import json
import os

from database import get_db
from models import Product, ProductAuction, AuctionBid, User, ProductStatus


router = APIRouter(prefix="/auctions", tags=["auctions"])


class AuctionOut(BaseModel):
    id: int
    product_id: int
    product_title: str
    start_price: float
    current_bid: float | None = None
    min_bid_increment: float
    start_time: datetime
    end_time: datetime
    status: str
    winner_id: int | None = None
    bids_count: int = 0
    time_remaining_seconds: int | None = None
    
    class Config:
        from_attributes = True


class AuctionCreate(BaseModel):
    product_id: int
    start_price: float = Field(..., gt=0)
    min_bid_increment: float = 100.0
    duration_hours: int = Field(default=48, ge=1, le=720)


class BidCreate(BaseModel):
    auction_id: int
    amount: float = Field(..., gt=0)
    user_id: int | None = None
    tg_user_id: int | None = None


def auction_to_out(auction: ProductAuction, bids_count: int = 0) -> AuctionOut:
    now = datetime.utcnow()
    time_remaining = None
    if auction.status == "active" and auction.end_time > now:
        time_remaining = int((auction.end_time - now).total_seconds())
    
    return AuctionOut(
        id=auction.id,
        product_id=auction.product_id,
        product_title=auction.product.title,
        start_price=auction.start_price,
        current_bid=auction.current_bid,
        min_bid_increment=auction.min_bid_increment,
        start_time=auction.start_time,
        end_time=auction.end_time,
        status=auction.status,
        winner_id=auction.winner_id,
        bids_count=bids_count,
        time_remaining_seconds=time_remaining,
    )


@router.post("/", response_model=AuctionOut, status_code=status.HTTP_201_CREATED)
async def create_auction(payload: AuctionCreate, db: AsyncSession = Depends(get_db)):
    """Создать аукцион для товара"""
    # Проверка товара
    product = await db.get(Product, payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    # Проверка, нет ли уже активного аукциона
    existing_query = select(ProductAuction).where(
        ProductAuction.product_id == payload.product_id,
        ProductAuction.status == "active"
    )
    existing_result = await db.execute(existing_query)
    existing = existing_result.scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Для этого товара уже есть активный аукцион")
    
    now = datetime.utcnow()
    end_time = now + timedelta(hours=payload.duration_hours)
    
    auction = ProductAuction(
        product_id=payload.product_id,
        start_price=payload.start_price,
        min_bid_increment=payload.min_bid_increment,
        start_time=now,
        end_time=end_time,
        status="active",
    )
    
    # Обновляем товар
    product.is_auction = True
    product.status = ProductStatus.AUCTION.value
    product.price = payload.start_price
    
    db.add(auction)
    await db.commit()
    await db.refresh(auction)
    
    # Получаем количество ставок (0 для нового аукциона)
    return auction_to_out(auction, 0)


@router.get("/", response_model=list[AuctionOut])
async def list_auctions(status_filter: str | None = None, db: AsyncSession = Depends(get_db)):
    """Получить список аукционов"""
    query = select(ProductAuction)
    
    if status_filter:
        query = query.where(ProductAuction.status == status_filter)
    
    query = query.order_by(ProductAuction.end_time)
    result = await db.execute(query)
    auctions = result.scalars().all()
    
    auctions_with_counts = []
    for auction in auctions:
        count_query = select(func.count(AuctionBid.id)).where(AuctionBid.auction_id == auction.id)
        count_result = await db.execute(count_query)
        bids_count = count_result.scalar() or 0
        auctions_with_counts.append(auction_to_out(auction, bids_count))
    
    return auctions_with_counts


@router.get("/{auction_id}", response_model=AuctionOut)
async def get_auction(auction_id: int, db: AsyncSession = Depends(get_db)):
    """Получить аукцион по ID"""
    auction = await db.get(ProductAuction, auction_id)
    if not auction:
        raise HTTPException(status_code=404, detail="Аукцион не найден")
    
    count_query = select(func.count(AuctionBid.id)).where(AuctionBid.auction_id == auction_id)
    count_result = await db.execute(count_query)
    bids_count = count_result.scalar() or 0
    
    return auction_to_out(auction, bids_count)


@router.post("/bids", status_code=status.HTTP_201_CREATED)
async def place_bid(payload: BidCreate, db: AsyncSession = Depends(get_db)):
    """Сделать ставку на аукционе"""
    auction = await db.get(ProductAuction, payload.auction_id)
    if not auction:
        raise HTTPException(status_code=404, detail="Аукцион не найден")
    
    if auction.status != "active":
        raise HTTPException(status_code=400, detail="Аукцион не активен")
    
    now = datetime.utcnow()
    if now > auction.end_time:
        # Завершаем аукцион
        auction.status = "ended"
        await db.commit()
        raise HTTPException(status_code=400, detail="Аукцион завершен")
    
    # Проверка минимальной ставки
    min_bid = auction.current_bid or auction.start_price
    if payload.amount < min_bid + auction.min_bid_increment:
        raise HTTPException(
            status_code=400, 
            detail=f"Минимальная ставка: {min_bid + auction.min_bid_increment}"
        )
    
    # Проверка пользователя
    if not payload.user_id and not payload.tg_user_id:
        raise HTTPException(status_code=400, detail="Требуется user_id или tg_user_id")
    
    # Создаем ставку
    bid = AuctionBid(
        auction_id=auction.id,
        user_id=payload.user_id,
        tg_user_id=payload.tg_user_id,
        amount=payload.amount,
    )
    
    # Обновляем текущую ставку
    auction.current_bid = payload.amount
    
    db.add(bid)
    await db.commit()
    await db.refresh(bid)
    
    return {
        "ok": True,
        "bid_id": bid.id,
        "amount": payload.amount,
        "message": "Ставка принята"
    }


@router.get("/{auction_id}/bids")
async def get_auction_bids(auction_id: int, db: AsyncSession = Depends(get_db)):
    """Получить все ставки аукциона"""
    auction = await db.get(ProductAuction, auction_id)
    if not auction:
        raise HTTPException(status_code=404, detail="Аукцион не найден")
    
    query = select(AuctionBid).where(AuctionBid.auction_id == auction_id).order_by(AuctionBid.created_at.desc())
    result = await db.execute(query)
    bids = result.scalars().all()
    
    return [
        {
            "id": bid.id,
            "amount": bid.amount,
            "user_id": bid.user_id,
            "tg_user_id": bid.tg_user_id,
            "created_at": bid.created_at,
        }
        for bid in bids
    ]


@router.post("/{auction_id}/end")
async def end_auction(auction_id: int, db: AsyncSession = Depends(get_db)):
    """Завершить аукцион вручную"""
    auction = await db.get(ProductAuction, auction_id)
    if not auction:
        raise HTTPException(status_code=404, detail="Аукцион не найден")
    
    if auction.status != "active":
        raise HTTPException(status_code=400, detail="Аукцион уже завершен")
    
    # Находим максимальную ставку
    query = select(AuctionBid).where(AuctionBid.auction_id == auction_id).order_by(AuctionBid.amount.desc())
    result = await db.execute(query)
    highest_bid = result.scalars().first()
    
    if highest_bid:
        auction.winner_id = highest_bid.user_id
        auction.status = "sold"
        
        # Обновляем товар
        product = await db.get(Product, auction.product_id)
        if product:
            product.status = ProductStatus.SOLD.value
            product.is_auction = False
    else:
        auction.status = "ended"
        # Возвращаем товар в обычный статус
        product = await db.get(Product, auction.product_id)
        if product:
            product.status = ProductStatus.IN_STOCK.value
            product.is_auction = False
    
    await db.commit()
    
    return {
        "ok": True,
        "status": auction.status,
        "winner_id": auction.winner_id,
        "final_bid": highest_bid.amount if highest_bid else None
    }
