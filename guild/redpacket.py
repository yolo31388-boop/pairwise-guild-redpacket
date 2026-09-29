"""帮派红包与分红系统"""
import random
import time
import uuid
from dataclasses import dataclass, field

EXPIRE_SECONDS = 24 * 60 * 60
MIN_AMOUNT = 1
MAX_AMOUNT = 200_000_000
DIVIDEND_RATIO = 100
DEFAULT_TOTAL_COUNT = 10
POSITION_WEIGHT = {
    "leader": 2.0,
    "deputy": 1.5,
    "elder": 1.2,
    "member": 1.0,
}


@dataclass
class RedPacket:
    rpid: str
    sender: str
    amount: int
    type: str = "normal"  # normal/lucky/exclusive
    claimed: list = field(default_factory=list)
    expire_time: float = 0.0
    total_count: int = DEFAULT_TOTAL_COUNT
    target: str | None = None
    create_time: float = 0.0
    remaining: int = 0
    refunded: bool = False

    def __post_init__(self):
        if self.remaining <= 0:
            self.remaining = self.amount
        if self.create_time <= 0:
            self.create_time = 0.0


class RedPacketSystem:
    def __init__(self, seed=42):
        self.rng = random.Random(seed)
        self.packets: dict[str, RedPacket] = {}
        self.guild_funds: int = 100000
        self.member_contribution: dict[str, int] = {}
        self.member_position: dict[str, str] = {}
        self.member_online_time: dict[str, int] = {}
        self.claim_records: list[dict] = []
        self.send_records: list[dict] = []
        self.dividend_records: list[dict] = []
        self.refund_records: list[dict] = []

    def create_packet(
        self,
        sender: str,
        amount: int,
        ptype: str = "normal",
        total_count: int = DEFAULT_TOTAL_COUNT,
        target: str | None = None,
        current_time: float | None = None,
    ) -> tuple[bool, str]:
        if not isinstance(amount, int) or isinstance(amount, bool):
            return False, "amount must be an integer"
        if amount < MIN_AMOUNT:
            return False, f"amount must be >= {MIN_AMOUNT}"
        if amount > MAX_AMOUNT:
            return False, f"amount must be <= {MAX_AMOUNT}"
        if ptype not in ("normal", "lucky", "exclusive"):
            return False, f"unknown packet type: {ptype}"
        if not isinstance(total_count, int) or total_count < 1:
            return False, "total_count must be a positive integer"
        if amount < total_count:
            return False, "amount must be >= total_count"
        if ptype == "exclusive" and not target:
            return False, "exclusive packet needs a target"
        if current_time is None:
            current_time = time.time()
        rpid = uuid.uuid4().hex[:12]
        packet = RedPacket(
            rpid=rpid,
            sender=sender,
            amount=amount,
            type=ptype,
            expire_time=current_time + EXPIRE_SECONDS,
            total_count=total_count,
            target=target,
            create_time=current_time,
            remaining=amount,
        )
        self.packets[rpid] = packet
        self.send_records.append({
            "rpid": rpid,
            "sender": sender,
            "amount": amount,
            "type": ptype,
            "time": current_time,
        })
        return True, rpid

    def _next_lucky_share(self, packet: RedPacket) -> int:
        left_slots = packet.total_count - len(packet.claimed)
        if left_slots <= 1:
            return packet.remaining
        max_share = max(1, packet.remaining // left_slots * 2)
        max_share = min(max_share, packet.remaining - (left_slots - 1))
        share = self.rng.randint(1, max(1, max_share))
        packet.remaining -= share
        return share

    def claim_packet(self, rpid: str, player: str, current_time: float | None = None) -> int:
        packet = self.packets.get(rpid)
        if packet is None:
            return 0
        if player == packet.sender:
            return 0
        if player in packet.claimed:
            return 0
        if len(packet.claimed) >= packet.total_count:
            return 0
        if self.is_expired(rpid, current_time if current_time is not None else time.time()):
            return 0
        if packet.type == "exclusive" and packet.target != player:
            return 0
        if packet.type == "lucky":
            share = self._next_lucky_share(packet)
        elif packet.type == "exclusive":
            share = packet.remaining
            packet.remaining = 0
        else:
            left_slots = packet.total_count - len(packet.claimed)
            share = packet.remaining // left_slots
            packet.remaining -= share
        packet.claimed.append(player)
        self.claim_records.append({
            "rpid": rpid,
            "player": player,
            "amount": share,
            "type": packet.type,
            "time": current_time if current_time is not None else time.time(),
        })
        return share

    def expire_refund(self, rpid: str, current_time: float | None = None) -> int:
        packet = self.packets.get(rpid)
        if packet is None or packet.refunded:
            return 0
        if not self.is_expired(rpid, current_time if current_time is not None else time.time()):
            return 0
        packet.refunded = True
        refund = packet.remaining
        packet.remaining = 0
        if refund > 0:
            self.refund_records.append({
                "rpid": rpid,
                "sender": packet.sender,
                "amount": refund,
                "time": current_time if current_time is not None else time.time(),
            })
        return refund

    def is_expired(self, rpid: str, current_time: float) -> bool:
        packet = self.packets.get(rpid)
        if packet is None:
            return True
        if packet.expire_time <= 0:
            return False
        return current_time > packet.expire_time

    def _member_weight(self, player: str) -> float:
        contribution = self.member_contribution.get(player, 0)
        position = self.member_position.get(player, "member")
        position_bonus = POSITION_WEIGHT.get(position, 1.0)
        online_hours = self.member_online_time.get(player, 0) // 3600
        return (contribution + online_hours) * position_bonus

    def calculate_dividend(self, player: str) -> int:
        pool = self.get_dividend_amount(self.guild_funds)
        weights = {p: self._member_weight(p) for p in self.member_contribution}
        total_weight = sum(weights.values())
        if total_weight <= 0:
            return 0
        return pool * weights.get(player, 0) // total_weight

    def distribute_dividends(self, current_time: float | None = None) -> dict[str, int]:
        pool = self.get_dividend_amount(self.guild_funds)
        result: dict[str, int] = {}
        remaining = pool
        members = sorted(self.member_contribution)
        total_weight = sum(self._member_weight(p) for p in members)
        if total_weight <= 0:
            return result
        for index, player in enumerate(members):
            if index == len(members) - 1:
                share = remaining
            else:
                share = pool * self._member_weight(player) // total_weight
                remaining -= share
            result[player] = share
            self.dividend_records.append({
                "player": player,
                "amount": share,
                "funds": self.guild_funds,
                "time": current_time if current_time is not None else time.time(),
            })
        return result

    def get_dividend_amount(self, funds: int) -> int:
        return funds // DIVIDEND_RATIO

    def get_packet_types(self) -> list:
        return ["normal", "lucky", "exclusive"]

    def get_claim_history(self, player: str) -> list:
        return [r for r in self.claim_records if r["player"] == player]

    def get_send_history(self, player: str) -> list:
        return [r for r in self.send_records if r["sender"] == player]

    def get_dividend_history(self, player: str) -> list:
        return [r for r in self.dividend_records if r["player"] == player]

    def get_refund_history(self, player: str) -> list:
        return [r for r in self.refund_records if r["sender"] == player]

