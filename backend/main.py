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
        try:
            fetch_and_store(db)
        except Exception as e:
            print(f"⚠️ Startup fetch failed: {e}. Server starting anyway.")

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
    rows = [r for r in rows if r.high is not None and r.low is not None and r.close is not None]
    if not rows:
        raise HTTPException(status_code=404, detail="No valid data found")
    closes = [r.close for r in rows]
    returns = [r.daily_return for r in rows if r.daily_return is not None]
    return {
        "symbol": full_symbol,
        "52w_high": round(max(r.high for r in rows), 2),
        "52w_low": round(min(r.low for r in rows), 2),
        "avg_close": round(sum(closes) / len(closes), 2),
        "volatility_score": round((max(closes) - min(closes)) / min(closes) * 100, 2),
        "avg_daily_return": round(sum(returns) / len(returns) * 100, 4) if returns else 0,
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
    rows = [r for r in rows if r.close is not None]
    if not rows:
        return []
    base = rows[0].close
    return [round((r.close - base) / base * 100, 2) for r in rows]

    return {
        symbol1: {"dates": [str(r.date) for r in rows1], "normalized": normalize(rows1)},
        symbol2: {"dates": [str(r.date) for r in rows2], "normalized": normalize(rows2)},
    }

import os
from dotenv import load_dotenv
import google.generativeai as genai
from pydantic import BaseModel

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    try:
        context_lines = []
        for sym in SYMBOLS:
            name = sym.replace(".NS", "")
            rows = db.query(StockPrice).filter(StockPrice.symbol == sym).order_by(StockPrice.date.desc()).limit(30).all()
            if not rows:
                continue
            closes = [r.close for r in rows]
            returns = [r.daily_return for r in rows if r.daily_return is not None]
            latest = rows[0]
            avg_return = round(sum(returns) / len(returns) * 100, 4) if returns else 0
            min_close = min(closes)
            volatility = round((max(closes) - min_close) / min_close * 100, 2) if min_close > 0 else 0
            context_lines.append(
                f"{name}: latest_close=₹{latest.close}, 30d_avg_return={avg_return}%, "
                f"volatility={volatility}%, high=₹{max(closes)}, low=₹{min_close}"
            )

        context = "\n".join(context_lines)
        prompt = f"""You are a helpful financial analyst assistant. 
Use the following real-time stock market data to answer the user's question.
If the data is not available for a specific company mentioned, state that you don't have data for it.

Data Context (Last 30 Days):
{context}

User Question: {req.message}

Instructions: Provide a direct, data-driven answer based ONLY on the context provided above. Mention specific prices or percentages where relevant.
"""
        if not os.getenv("GEMINI_API_KEY"):
            return {"reply": "Configuration Error: GEMINI_API_KEY is not set. Please add it to your .env file."}

        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        return {"reply": response.text}
    except Exception as e:
        return {"reply": f"AI Error: {str(e)}"}

@app.get("/refresh")
def refresh_data():
    db = next(get_db())
    try:
        fetch_and_store(db)
        return {"status": "success", "message": "Data fetched successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

app.mount("/static", StaticFiles(directory="../frontend"), name="static")

@app.get("/")
def serve_frontend():
    return FileResponse("../frontend/index.html")
