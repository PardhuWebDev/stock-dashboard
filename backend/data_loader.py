import yfinance as yf
import pandas as pd
from sqlalchemy.orm import Session
from models import StockPrice
from database import engine, Base, SessionLocal

SYMBOLS = ["INFY.NS", "TCS.NS", "RELIANCE.NS", "WIPRO.NS", "HDFCBANK.NS"]

def fetch_and_store(db: Session):
    Base.metadata.create_all(bind=engine)
    
    # Use a fresh session to avoid locks
    fresh_db = SessionLocal()
    try:
        fresh_db.query(StockPrice).delete()
        fresh_db.commit()

        for symbol in SYMBOLS:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1y")

            if df.empty:
                continue

            df.reset_index(inplace=True)
            df["Date"] = pd.to_datetime(df["Date"]).dt.date
            df["DailyReturn"] = (df["Close"] - df["Open"]) / df["Open"]
            df["MA7"] = df["Close"].rolling(window=7).mean()

            for _, row in df.iterrows():
                record = StockPrice(
                    symbol=symbol,
                    date=row["Date"],
                    open=round(row["Open"], 2),
                    high=round(row["High"], 2),
                    low=round(row["Low"], 2),
                    close=round(row["Close"], 2),
                    volume=row["Volume"],
                    daily_return=round(row["DailyReturn"], 4),
                    moving_avg_7=round(row["MA7"], 2) if not pd.isna(row["MA7"]) else None
                )
                fresh_db.add(record)

        fresh_db.commit()
        print("✅ Data loaded successfully!")
    except Exception as e:
        fresh_db.rollback()
        raise e
    finally:
        fresh_db.close()
