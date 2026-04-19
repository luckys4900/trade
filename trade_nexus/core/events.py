from enum import Enum
from dataclasses import dataclass
from typing import Any, Optional

class EventType(Enum):
    TICK = "TICK"              # 価格更新
    SIGNAL = "SIGNAL"          # エントリー・エグジット判断
    ORDER = "ORDER"            # 注文リクエスト
    FILL = "FILL"              # 約定完了通知

@dataclass
class Event:
    type: EventType
    timestamp: float

@dataclass
class TickEvent(Event):
    symbol: str
    price: float
    volume: Optional[float] = None

@dataclass
class SignalEvent(Event):
    symbol: str
    side: str  # 'buy' or 'sell' or 'exit'
    strategy_name: str

@dataclass
class OrderEvent(Event):
    symbol: str
    side: str
    order_type: str  # 'market', 'limit'
    quantity: float
    price: Optional[float] = None

@dataclass
class FillEvent(Event):
    symbol: str
    side: str
    quantity: float
    fill_price: float
    commission: float
