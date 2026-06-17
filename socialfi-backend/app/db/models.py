from sqlalchemy import Column, Integer, String, SmallInteger, Numeric, BigInteger, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()

class Creator(Base):
    __tablename__ = "creators"
    id = Column(Integer, primary_key=True, index=True)
    google_id = Column(String(255), unique=True, nullable=False)
    youtube_channel_id = Column(String(255), unique=True, nullable=False)
    display_name = Column(String(255))
    wallet_address = Column(String(42), unique=True, nullable=False)
    token_contract = Column(String(42), unique=True)
    tier = Column(SmallInteger, nullable=False)
    base_price_usdc = Column(Numeric(18, 6), nullable=False)
    k_value = Column(Numeric(18, 9), nullable=False)
    subscriber_count = Column(BigInteger)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PriceEvent(Base):
    __tablename__ = "price_events"
    __table_args__ = (
        Index('idx_price_events_creator_time', 'creator_id', 'block_timestamp'),
    )
    id = Column(BigInteger, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("creators.id"))
    event_type = Column(String(10), nullable=False)
    price_usdc = Column(Numeric(18, 6), nullable=False)
    supply = Column(BigInteger, nullable=False)
    tx_hash = Column(String(66), unique=True, nullable=False)
    block_number = Column(BigInteger, nullable=False)
    block_timestamp = Column(DateTime(timezone=True), nullable=False)

class Candle5m(Base):
    __tablename__ = "candles_5m"
    __table_args__ = (
        UniqueConstraint('creator_id', 'open_time', name='uix_creator_opentime'),
        Index('idx_candles_creator_time', 'creator_id', 'open_time'),
    )
    id = Column(BigInteger, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("creators.id"))
    open_time = Column(DateTime(timezone=True), nullable=False)
    close_time = Column(DateTime(timezone=True), nullable=False)
    open_price = Column(Numeric(18, 6), nullable=False)
    high_price = Column(Numeric(18, 6), nullable=False)
    low_price = Column(Numeric(18, 6), nullable=False)
    close_price = Column(Numeric(18, 6), nullable=False)
    volume_tokens = Column(BigInteger, nullable=False)

class SentimentHistory(Base):
    __tablename__ = "sentiment_history"
    id = Column(BigInteger, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("creators.id"))
    modifier_bps = Column(Integer, nullable=False)
    raw_score = Column(Numeric(5, 4))
    comment_sample = Column(Integer)
    computed_at = Column(DateTime(timezone=True), server_default=func.now())
    tx_hash = Column(String(66))
