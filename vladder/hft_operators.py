from __future__ import annotations

from dataclasses import asdict, dataclass
import random
import struct
from typing import Iterable, Sequence


MESSAGE = struct.Struct(">BBiiQ")
TRACE_HEADER = struct.Struct(">8sII")
TRACE_MAGIC = b"STHFTV1\0"
BOOK_LEVELS = 64
PRICE_BASE = 100_000


@dataclass(frozen=True)
class MarketEvent:
    type: int
    side: int
    price_ticks: int
    quantity: int
    sequence: int


@dataclass
class BookState:
    bid_qty: list[int]
    ask_qty: list[int]
    last_sequence: int = 0

    @classmethod
    def empty(cls) -> "BookState":
        return cls([0] * BOOK_LEVELS, [0] * BOOK_LEVELS)


@dataclass(frozen=True)
class TopOfBook:
    best_bid_ticks: int
    best_bid_qty: int
    best_ask_ticks: int
    best_ask_qty: int


@dataclass
class RiskState:
    position: int = 0
    reserved: int = 0


@dataclass
class FeatureState:
    ewma_microprice: float = 0.0
    previous_spread: int = 0


@dataclass(frozen=True)
class PipelineOutput:
    status: int
    event: MarketEvent | None
    top: TopOfBook | None
    changed_mask: int
    accepted: bool
    reject_reason: int
    wire: bytes


def encode_event(event: MarketEvent) -> bytes:
    return MESSAGE.pack(event.type, event.side, event.price_ticks, event.quantity, event.sequence)


def decode_event(data: bytes) -> MarketEvent:
    if len(data) != MESSAGE.size:
        raise ValueError("market_message_v1 is exactly 18 bytes")
    return MarketEvent(*MESSAGE.unpack(data))


def update_book(book: BookState, event: MarketEvent) -> tuple[TopOfBook, int]:
    if event.type not in (1, 2, 3) or event.side not in (0, 1):
        raise ValueError("invalid event tag")
    level = event.price_ticks - PRICE_BASE
    if not 0 <= level < BOOK_LEVELS or event.quantity < 0 or event.sequence <= book.last_sequence:
        raise ValueError("invalid state transition")
    quantities = book.bid_qty if event.side == 0 else book.ask_qty
    quantities[level] = 0 if event.type == 3 else event.quantity
    book.last_sequence = event.sequence
    bid = next(((PRICE_BASE + i, book.bid_qty[i]) for i in range(BOOK_LEVELS - 1, -1, -1) if book.bid_qty[i]), (0, 0))
    ask = next(((PRICE_BASE + i, book.ask_qty[i]) for i in range(BOOK_LEVELS) if book.ask_qty[i]), (0, 0))
    return TopOfBook(bid[0], bid[1], ask[0], ask[1]), 1 << level


def risk_gate(event: MarketEvent, state: RiskState, max_position: int, max_order: int) -> tuple[bool, int]:
    if event.quantity > max_order:
        return False, 1
    signed = event.quantity if event.side == 0 else -event.quantity
    next_reserved = state.reserved + signed
    if abs(state.position + next_reserved) > max_position:
        return False, 2
    state.reserved = next_reserved
    return True, 0


def risk_gate_mask(event: MarketEvent, state: RiskState, max_position: int, max_order: int) -> tuple[bool, int]:
    signed = event.quantity if event.side == 0 else -event.quantity
    order_failure = int(event.quantity > max_order)
    position_failure = int(abs(state.position + state.reserved + signed) > max_position)
    reason = 1 if order_failure else (2 if position_failure else 0)
    accepted = (order_failure | position_failure) == 0
    if accepted:
        state.reserved += signed
    return accepted, reason


def feature_update(top: TopOfBook, state: FeatureState, alpha: float = 0.125) -> tuple[float, int, bool]:
    if not top.best_bid_ticks or not top.best_ask_ticks:
        microprice = float(top.best_bid_ticks or top.best_ask_ticks)
        spread = 0
    else:
        total = top.best_bid_qty + top.best_ask_qty
        microprice = ((top.best_ask_ticks * top.best_bid_qty + top.best_bid_ticks * top.best_ask_qty) / total) if total else (top.best_bid_ticks + top.best_ask_ticks) * 0.5
        spread = top.best_ask_ticks - top.best_bid_ticks
    state.ewma_microprice += alpha * (microprice - state.ewma_microprice)
    changed = spread != state.previous_spread
    state.previous_spread = spread
    return state.ewma_microprice, spread, changed


def encode_decision(event: MarketEvent, accepted: bool, reason: int, producer_sequence: int) -> bytes:
    flags = 1 if accepted else 0
    return struct.pack(">QIBBi", producer_sequence, event.sequence & 0xFFFFFFFF, flags, reason, event.quantity)


def encode_decision_template(event: MarketEvent, accepted: bool, reason: int, producer_sequence: int) -> bytes:
    message = bytearray(18)
    struct.pack_into(">Q", message, 0, producer_sequence)
    struct.pack_into(">I", message, 8, event.sequence & 0xFFFFFFFF)
    message[12], message[13] = int(accepted), reason
    struct.pack_into(">i", message, 14, event.quantity)
    return bytes(message)


def book_as_aos(book: BookState) -> list[tuple[int, int]]:
    return list(zip(book.bid_qty, book.ask_qty))


def book_from_aos(levels: Sequence[tuple[int, int]], sequence: int) -> BookState:
    if len(levels) != BOOK_LEVELS:
        raise ValueError("book layout requires 64 levels")
    return BookState([level[0] for level in levels], [level[1] for level in levels], sequence)


def ewma_recompute(values: Sequence[float], alpha: float = 0.125) -> float:
    result = 0.0
    for value in values:
        result += alpha * (value - result)
    return result


class SPSCRing:
    """Executable model of the acquire/release SPSC contract."""

    def __init__(self, capacity: int):
        if capacity < 2 or capacity & (capacity - 1):
            raise ValueError("SPSC capacity must be a power of two")
        self.capacity = capacity
        self.slots: list[bytes | None] = [None] * capacity
        self.producer = 0
        self.consumer = 0

    def enqueue(self, value: bytes) -> bool:
        if self.producer - self.consumer == self.capacity:
            return False
        self.slots[self.producer & (self.capacity - 1)] = value
        self.producer += 1
        return True

    def dequeue(self) -> bytes | None:
        if self.consumer == self.producer:
            return None
        index = self.consumer & (self.capacity - 1)
        value = self.slots[index]
        self.slots[index] = None
        self.consumer += 1
        return value


def run_pipeline(messages: Iterable[bytes], max_position: int = 50_000, max_order: int = 10_000) -> tuple[list[PipelineOutput], dict[str, object]]:
    book, risk, features, ring = BookState.empty(), RiskState(), FeatureState(), SPSCRing(8)
    outputs = []
    for sequence, message in enumerate(messages, 1):
        try:
            event = decode_event(message)
            top, mask = update_book(book, event)
        except ValueError:
            outputs.append(PipelineOutput(-2, None, None, 0, False, 3, b""))
            continue
        accepted, reason = risk_gate(event, risk, max_position, max_order)
        feature_update(top, features)
        wire = encode_decision(event, accepted, reason, sequence)
        if not ring.enqueue(wire):
            ring.dequeue()
            if not ring.enqueue(wire):
                raise AssertionError("SPSC progress invariant failed")
        outputs.append(PipelineOutput(0, event, top, mask, accepted, reason, wire))
    drained = []
    while True:
        value = ring.dequeue()
        if value is None:
            break
        drained.append(value)
    state = {"book": asdict(book), "risk": asdict(risk), "features": asdict(features), "ring_drained": [value.hex() for value in drained]}
    return outputs, state


def generate_trace(kind: str, count: int, seed: int) -> list[bytes]:
    rng = random.Random(seed)
    trace = []
    sequence = 1
    for i in range(count):
        if kind == "adversarial":
            event_type = 1 + i % 3
            side = i & 1
            level = 63 if i % 4 == 0 else (0 if i % 4 == 1 else i % 64)
            quantity = 0 if event_type == 3 else (10_000 if i % 17 == 0 else 1 + i % 997)
        else:
            draw = rng.random()
            event_type = 1 if draw < 0.42 else (2 if draw < 0.79 else 3)
            side = rng.randrange(2)
            level = min(63, int(rng.expovariate(0.18)))
            if side == 0:
                level = 63 - level
            quantity = 0 if event_type == 3 else rng.randrange(1, 2000)
        trace.append(encode_event(MarketEvent(event_type, side, PRICE_BASE + level, quantity, sequence)))
        sequence += 1
    return trace


def write_trace(path: str, messages: Sequence[bytes], seed: int) -> None:
    with open(path, "wb") as stream:
        stream.write(TRACE_HEADER.pack(TRACE_MAGIC, len(messages), seed))
        for message in messages:
            stream.write(message)


def read_trace(path: str) -> tuple[list[bytes], int]:
    with open(path, "rb") as stream:
        magic, count, seed = TRACE_HEADER.unpack(stream.read(TRACE_HEADER.size))
        if magic != TRACE_MAGIC:
            raise ValueError("unsupported trace schema")
        messages = [stream.read(MESSAGE.size) for _ in range(count)]
        if any(len(message) != MESSAGE.size for message in messages) or stream.read(1):
            raise ValueError("malformed trace")
    return messages, seed
