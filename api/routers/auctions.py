from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import json
import os
import asyncio

from database import get_db
from models import Product, ProductAuction, AuctionBid, User, ProductStatus

# Импортируем функцию проверки админа из main
async def verify_admin_access(request: Request) -> bool:
    """Проверяет, есть ли у пользователя доступ администратора"""
    tg_user_id = request.headers.get("X-Telegram-User-Id")

    if not tg_user_id:
        return False

    try:
        user_id = int(tg_user_id)
    except (ValueError, TypeError):
        return False
    
    # Получаем список админов из кэша или через Telegram API
    from main import get_group_admin_ids
    admin_ids = await get_group_admin_ids()
    
    # Если список администраторов пуст (нет токена/группы), проверяем по старому методу
    if not admin_ids:
        static_admin_ids = {
            int(id_str.strip())
            for id_str in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")
            if id_str.strip()
        }
        return user_id in static_admin_ids
    
    return user_id in admin_ids


router = APIRouter(prefix="/auctions", tags=["auctions"])

# Хранилище для фоновых задач (в production лучше использовать Redis/Celery)
active_auction_tasks: dict[int, asyncio.Task] = {}


async def check_and_complete_auctions(db: AsyncSession):
    """Фоновая задача для проверки и завершения истекших аукционов"""
    now = datetime.utcnow()
    
    query = select(ProductAuction).where(
        ProductAuction.status == "active",
        ProductAuction.end_time <= now
    )
    result = await db.execute(query)
    expired_auctions = result.scalars().all()
    
    for auction in expired_auctions:
        # Находим максимальную ставку
        bid_query = select(AuctionBid).where(
            AuctionBid.auction_id == auction.id
        ).order_by(AuctionBid.amount.desc())
        bid_result = await db.execute(bid_query)
        highest_bid = bid_result.scalars().first()
        
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
        
        # TODO: Здесь можно добавить отправку уведомления в Telegram
        # await notify_auction_ended(auction, highest_bid)
    
    return len(expired_auctions)


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


class AuctionUpdate(BaseModel):
    """Модель для обновления параметров аукциона"""
    start_price: float | None = Field(None, gt=0)
    min_bid_increment: float | None = None
    end_time: datetime | None = None
    status: str | None = None


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
async def create_auction(request: Request, payload: AuctionCreate, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Создать аукцион для товара - только для админов"""
    if not await verify_admin_access(request):
        raise HTTPException(status_code=403, detail="Доступ запрещён. Только для администраторов.")
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
    
    # Запускаем фоновую задачу для мониторинга окончания аукциона
    # В production лучше использовать Celery/Redis
    background_tasks.add_task(monitor_auction_end, auction.id, (end_time - now).total_seconds())
    
    # Получаем количество ставок (0 для нового аукциона)
    return auction_to_out(auction, 0)


async def monitor_auction_end(auction_id: int, delay_seconds: float):
    """Фоновая задача для мониторинга окончания аукциона"""
    await asyncio.sleep(delay_seconds)
    # После пробуждения проверяем и завершаем аукцион
    # Примечание: в production используйте более надежное решение (Celery beat, Redis streams)
    from database import get_db_session
    async for db in get_db_session():
        await check_and_complete_auctions(db)
        break


@router.get("/", response_model=list[AuctionOut])
async def list_auctions(request: Request, status_filter: str | None = None, db: AsyncSession = Depends(get_db)):
    """Получить список аукционов - только для админов"""
    if not await verify_admin_access(request):
        raise HTTPException(status_code=403, detail="Доступ запрещён. Только для администраторов.")
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
async def get_auction(request: Request, auction_id: int, db: AsyncSession = Depends(get_db)):
    """Получить аукцион по ID - только для админов"""
    if not await verify_admin_access(request):
        raise HTTPException(status_code=403, detail="Доступ запрещён. Только для администраторов.")
    auction = await db.get(ProductAuction, auction_id)
    if not auction:
        raise HTTPException(status_code=404, detail="Аукцион не найден")
    
    count_query = select(func.count(AuctionBid.id)).where(AuctionBid.auction_id == auction_id)
    count_result = await db.execute(count_query)
    bids_count = count_result.scalar() or 0
    
    return auction_to_out(auction, bids_count)


@router.post("/bids", status_code=status.HTTP_201_CREATED)
async def place_bid(request: Request, payload: BidCreate, db: AsyncSession = Depends(get_db)):
    """Сделать ставку на аукционе - только для админов"""
    if not await verify_admin_access(request):
        raise HTTPException(status_code=403, detail="Доступ запрещён. Только для администраторов.")
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
async def get_auction_bids(request: Request, auction_id: int, db: AsyncSession = Depends(get_db)):
    """Получить все ставки аукциона - только для админов"""
    if not await verify_admin_access(request):
        raise HTTPException(status_code=403, detail="Доступ запрещён. Только для администраторов.")
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
async def end_auction(request: Request, auction_id: int, db: AsyncSession = Depends(get_db)):
    """Завершить аукцион вручную - только для админов"""
    if not await verify_admin_access(request):
        raise HTTPException(status_code=403, detail="Доступ запрещён. Только для администраторов.")
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


@router.put("/{auction_id}")
async def update_auction(request: Request, auction_id: int, payload: AuctionUpdate, db: AsyncSession = Depends(get_db)):
    """Обновить параметры аукциона - только для админов"""
    if not await verify_admin_access(request):
        raise HTTPException(status_code=403, detail="Доступ запрещён. Только для администраторов.")
    auction = await db.get(ProductAuction, auction_id)
    if not auction:
        raise HTTPException(status_code=404, detail="Аукцион не найден")
    
    if auction.status != "active":
        raise HTTPException(status_code=400, detail="Можно обновить только активный аукцион")
    
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(auction, field, value)
    
    await db.commit()
    await db.refresh(auction)
    
    # Получаем количество ставок
    count_query = select(func.count(AuctionBid.id)).where(AuctionBid.auction_id == auction_id)
    count_result = await db.execute(count_query)
    bids_count = count_result.scalar() or 0
    
    return auction_to_out(auction, bids_count)
