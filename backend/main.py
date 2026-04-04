from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db, engine
from models import StockPrice, Base
from data_loader import fetch_and_store, SYMBOLS
import datetime
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Stock Intelligence Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    db = next(get_db())
    count = db.query(StockPrice).count()
    if count == 0:
        print("📦 No data found, fetching from yfinance...")
        fetch_and_store(db)

@app.get("/companies")
def get_companies():
    return {"companies": [s.replace(".NS", "") for s in SYMBOLS], "symbols": SYMBOLS}

@app.get("/data/{symbol}")
def get_stock_data(symbol: str, db: Session = Depends(get_db)):
    full_symbol = symbol if ".NS" in symbol else symbol + ".NS"
    cutoff = datetime.date.today() - datetime.timedelta(days=30)
    rows = (
        db.query(StockPrice)
        .filter(StockPrice.symbol == full_symbol, StockPrice.date >= cutoff)
        .order_by(StockPrice.date)
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Symbol not found")
    return [
        {
            "date": str(r.date),
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
            "daily_return": r.daily_return,
            "moving_avg_7": r.moving_avg_7,
        }
        for r in rows
    ]

@app.get("/summary/{symbol}")
def get_summary(symbol: str, db: Session = Depends(get_db)):
    full_symbol = symbol if ".NS" in symbol else symbol + ".NS"
    cutoff = datetime.date.today() - datetime.timedelta(days=365)
    rows = db.query(StockPrice).filter(
        StockPrice.symbol == full_symbol,
        StockPrice.date >= cutoff
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="Symbol not found")
    closes = [r.close for r in rows]
    returns = [r.daily_return for r in rows if r.daily_return is not None]
    return {
        "symbol": full_symbol,
        "52w_high": round(max(r.high for r in rows), 2),
        "52w_low": round(min(r.low for r in rows), 2),
        "avg_close": round(sum(closes) / len(closes), 2),
        "volatility_score": round((max(closes) - min(closes)) / min(closes) * 100, 2),
        "avg_daily_return": round(sum(returns) / len(returns) * 100, 4),
    }

@app.get("/compare")
def compare_stocks(symbol1: str, symbol2: str, db: Session = Depends(get_db)):
    def get_data(sym):
        full = sym if ".NS" in sym else sym + ".NS"
        cutoff = datetime.date.today() - datetime.timedelta(days=30)
        rows = db.query(StockPrice).filter(
            StockPrice.symbol == full,
            StockPrice.date >= cutoff
        ).order_by(StockPrice.date).all()
        return full, rows

    sym1, rows1 = get_data(symbol1)
    sym2, rows2 = get_data(symbol2)

    if not rows1 or not rows2:
        raise HTTPException(status_code=404, detail="One or both symbols not found")

    def normalize(rows):
        base = rows[0].close
        return [round((r.close - base) / base * 100, 2) for r in rows]

    return {
        symbol1: {"dates": [str(r.date) for r in rows1], "normalized": normalize(rows1)},
        symbol2: {"dates": [str(r.date) for r in rows2], "normalized": normalize(rows2)},
    }
app.mount("/static", StaticFiles(directory="../frontend"), name="static")

@app.get("/")
def serve_frontend():
    return FileResponse("../frontend/index.html")