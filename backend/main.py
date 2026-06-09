from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yfinance as yf
import pandas as pd
import datetime
import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

SYMBOLS = ["INFY.NS", "TCS.NS", "RELIANCE.NS", "WIPRO.NS", "HDFCBANK.NS"]
_cache = {}

def get_df(symbol: str, period: str = "1y") -> pd.DataFrame:
    key = f"{symbol}_{period}"
    cached = _cache.get(key)
    if cached:
        fetched_at, df = cached
        if (datetime.datetime.now() - fetched_at).seconds < 3600:
            return df
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period)
    if df.empty:
        return df
    df.reset_index(inplace=True)
    df["Date"] = pd.to_datetime(df["Date"]).dt.date
    df["DailyReturn"] = (df["Close"] - df["Open"]) / df["Open"]
    df["MA7"] = df["Close"].rolling(window=7).mean()
    df = df.dropna(subset=["Close", "High", "Low", "Open"])
    _cache[key] = (datetime.datetime.now(), df)
    return df

app = FastAPI(title="Stock Intelligence Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/companies")
def get_companies():
    return {"companies": [s.replace(".NS", "") for s in SYMBOLS], "symbols": SYMBOLS}

@app.get("/data/{symbol}")
def get_stock_data(symbol: str, days: int = 30):
    full_symbol = symbol if ".NS" in symbol else symbol + ".NS"
    try:
        df = get_df(full_symbol)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if df.empty:
        raise HTTPException(status_code=404, detail="Symbol not found")
    cutoff = datetime.date.today() - datetime.timedelta(days=days)
    df = df[df["Date"] >= cutoff]
    return [
        {
            "date": str(row["Date"]),
            "open": round(row["Open"], 2),
            "high": round(row["High"], 2),
            "low": round(row["Low"], 2),
            "close": round(row["Close"], 2),
            "volume": int(row["Volume"]),
            "daily_return": round(row["DailyReturn"], 4),
            "moving_avg_7": round(row["MA7"], 2) if not pd.isna(row["MA7"]) else None,
        }
        for _, row in df.iterrows()
    ]

@app.get("/summary/{symbol}")
def get_summary(symbol: str):
    full_symbol = symbol if ".NS" in symbol else symbol + ".NS"
    try:
        df = get_df(full_symbol)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if df.empty:
        raise HTTPException(status_code=404, detail="Symbol not found")
    closes = df["Close"].tolist()
    returns = df["DailyReturn"].dropna().tolist()
    return {
        "symbol": full_symbol,
        "52w_high": round(df["High"].max(), 2),
        "52w_low": round(df["Low"].min(), 2),
        "avg_close": round(sum(closes) / len(closes), 2),
        "volatility_score": round((max(closes) - min(closes)) / min(closes) * 100, 2),
        "avg_daily_return": round(sum(returns) / len(returns) * 100, 4) if returns else 0,
    }

@app.get("/compare")
def compare_stocks(symbol1: str, symbol2: str, days: int = 30):
    def get_normalized(sym):
        full = sym if ".NS" in sym else sym + ".NS"
        df = get_df(full)
        if df.empty:
            return [], []
        cutoff = datetime.date.today() - datetime.timedelta(days=days)
        df = df[df["Date"] >= cutoff]
        if df.empty:
            return [], []
        base = df["Close"].iloc[0]
        normalized = [round((c - base) / base * 100, 2) for c in df["Close"]]
        dates = [str(d) for d in df["Date"]]
        return dates, normalized

    dates1, norm1 = get_normalized(symbol1)
    dates2, norm2 = get_normalized(symbol2)

    if not norm1 or not norm2:
        raise HTTPException(status_code=404, detail="One or both symbols not found")

    return {
        symbol1: {"dates": dates1, "normalized": norm1},
        symbol2: {"dates": dates2, "normalized": norm2},
    }

class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
def chat(req: ChatRequest):
    try:
        context_lines = []
        for sym in SYMBOLS:
            name = sym.replace(".NS", "")
            df = get_df(sym)
            if df.empty:
                continue
            closes = df["Close"].tail(30).tolist()
            returns = df["DailyReturn"].tail(30).dropna().tolist()
            latest_close = closes[-1]
            avg_return = round(sum(returns) / len(returns) * 100, 4) if returns else 0
            min_close = min(closes)
            volatility = round((max(closes) - min_close) / min_close * 100, 2) if min_close > 0 else 0
            context_lines.append(
                f"{name}: latest_close=₹{latest_close:.2f}, 30d_avg_return={avg_return}%, "
                f"volatility={volatility}%, high=₹{max(closes):.2f}, low=₹{min_close:.2f}"
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
            return {"reply": "Configuration Error: GEMINI_API_KEY is not set."}
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        return {"reply": response.text}
    except Exception as e:
        return {"reply": f"AI Error: {str(e)}"}

@app.get("/refresh")
def refresh_data():
    _cache.clear()
    return {"status": "success", "message": "Cache cleared. Data will be fetched fresh on next request."}

app.mount("/static", StaticFiles(directory="../frontend"), name="static")

@app.get("/")
def serve_frontend():
    return FileResponse("../frontend/index.html")
