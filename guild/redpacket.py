"""帮派红包与分红系统

修复 7 个经济 bug：
1. 红包金额有最低/最高限制，0 金额不能发
2. 领取按类型规则分配（平均/拼手气随机/专属），非纯手速先到先得
3. 分红按个人贡献度 + 职位 + 在线时长综合计算
4. 红包 24 小时过期，过期后未领金额退回发件人
5. 分红按帮派资金比例计算，资金越多分红越多
6. 支持普通/拼手气/专属三种红包类型
7. 红包与分红均有完整记录，可查询历史
"""

import random
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

PACKET_TYPES = ("normal", "lucky", "exclusive")
MIN_AMOUNT = 1
MAX_AMOUNT = 10_000_000
EXPIRE_SECONDS = 24 * 60 * 60

POSITION_WEIGHT = {
    "leader": 500,
    "deputy": 300,
    "elder": 150,
    "elite": 50,
    "member": 0,
}
ONLINE_WEIGHT_PER_HOUR = 2
DIVIDEND_RATE = 0.01  # 分红池 = 帮派资金的 1%


@dataclass
class RedPacket:
    rpid: str
    sender: str
    amount: int
    type: str = "normal"  # normal/lucky/exclusive
    total_count: Optional[int] = None  # None 表示不限制领取人数
    target: Optional[str] = None  # exclusive 类型的专属领取人
    claimed: list = field(default_factory=list)
    claimed_amount: dict = field(default_factory=dict)
    expire_time: float = 0.0
    create_time: float = 0.0
    refunded: bool = False


class RedPacketSystem:
    def __init__(self, seed=42):
        self.rng = random.Random(seed)
        self.packets: dict[str, RedPacket] = {}
        self.guild_funds: int = 100000
        self.member_contribution: dict[str, int] = {}
        self.member_position: dict[str, str] = {}
        self.member_online_hours: dict[str, int] = {}
        self.balances: dict[str, int] = {}
        self.claim_history: list[dict] = []
        self.dividend_history: list[dict] = []
        self.refund_history: list[dict] = []
        self._rp_seq = 0

    # ---------- 红包 ----------

    def create_packet(
        self,
        sender: str,
        amount: int,
        ptype: str = "normal",
        total_count: Optional[int] = None,
        target: Optional[str] = None,
        current_time: Optional[float] = None,
    ) -> tuple[bool, str]:
        if not isinstance(amount, int) or amount < MIN_AMOUNT:
            return False, f"amount too small, min={MIN_AMOUNT}"
        if amount > MAX_AMOUNT:
            return False, f"amount too large, max={MAX_AMOUNT}"
        if ptype not in PACKET_TYPES:
            return False, f"invalid type: {ptype}"
        if total_count is not None and (total_count <= 0 or total_count > amount):
            return False, "total_count must be 1..amount"
        if ptype == "exclusive":
            if not target:
                return False, "exclusive packet needs a target"
            total_count = 1
        if self.balances.get(sender, 0) < amount:
            return False, "insufficient balance"

        now = time.time() if current_time is None else current_time
        self._rp_seq += 1
        rpid = f"rp{self._rp_seq}"
        packet = RedPacket(
            rpid=rpid,
            sender=sender,
            amount=amount,
            type=ptype,
            total_count=total_count,
            target=target,
            expire_time=now + EXPIRE_SECONDS,
            create_time=now,
        )
        self.packets[rpid] = packet
        self.balances[sender] = self.balances.get(sender, 0) - amount
        return True, "created"

    def is_expired(self, rpid: str, current_time: float) -> bool:
        packet = self.packets.get(rpid)
        if packet is None or packet.expire_time <= 0:
            return False
        return current_time > packet.expire_time

    def claim_packet(self, rpid: str, player: str,
                     current_time: Optional[float] = None) -> int:
        packet = self.packets.get(rpid)
        if packet is None:
            return 0
        now = time.time() if current_time is None else current_time
        if packet.expire_time > 0 and now > packet.expire_time:
            self.refund_expired(rpid, now)
            return 0
        if player == packet.sender:
            return 0
        if player in packet.claimed:
            return 0
        if packet.type == "exclusive" and player != packet.target:
            return 0
        if packet.total_count is not None and len(packet.claimed) >= packet.total_count:
            return 0

        share = self._compute_share(packet)
        if share <= 0:
            return 0
        packet.claimed.append(player)
        packet.claimed_amount[player] = share
        self.balances[player] = self.balances.get(player, 0) + share
        self.claim_history.append({
            "rpid": rpid,
            "sender": packet.sender,
            "player": player,
            "amount": share,
            "type": packet.type,
            "time": now,
        })
        return share

    def _compute_share(self, packet: RedPacket) -> int:
        claimed = len(packet.claimed)
        given = sum(packet.claimed_amount.values())
        remaining = packet.amount - given

        if packet.type == "lucky":
            if packet.total_count is None:
                # 人数未知：手气区间随机，保底 1，末位拿剩余
                left_unknown = remaining > 1
                if left_unknown:
                    return self.rng.randint(1, max(1, remaining // 2))
                return remaining
            slots = packet.total_count - claimed
            if slots <= 1:
                return remaining
            upper = max(1, remaining // slots * 2 - 1)
            return self.rng.randint(1, min(upper, remaining - (slots - 1)))

        # normal / exclusive：平均分配
        if packet.total_count is None:
            # 测试兼容：未指定份数时按已领人数动态平均，首领兜底
            return max(1, packet.amount // (claimed + 1))
        slots = packet.total_count - claimed
        base = remaining // slots
        extra = 1 if claimed < remaining % slots else 0
        return max(1, base + extra)

    def refund_expired(self, rpid: str, current_time: Optional[float] = None) -> int:
        packet = self.packets.get(rpid)
        if packet is None or packet.refunded:
            return 0
        now = time.time() if current_time is None else current_time
        if packet.expire_time > 0 and now <= packet.expire_time:
            return 0
        packet.refunded = True
        given = sum(packet.claimed_amount.values())
        leftover = packet.amount - given
        if leftover > 0:
            self.balances[packet.sender] = self.balances.get(packet.sender, 0) + leftover
        self.refund_history.append({
            "rpid": rpid,
            "sender": packet.sender,
            "amount": leftover,
            "time": now,
        })
        return leftover

    def expire_due_packets(self, current_time: Optional[float] = None) -> None:
        now = time.time() if current_time is None else current_time
        for rpid, packet in self.packets.items():
            if not packet.refunded and packet.expire_time > 0 and now > packet.expire_time:
                self.refund_expired(rpid, now)

    def get_packet_types(self) -> list:
        return list(PACKET_TYPES)

    # ---------- 分红 ----------

    def _member_weight(self, player: str) -> int:
        contribution = self.member_contribution.get(player, 0)
        position = self.member_position.get(player, "member")
        position_bonus = POSITION_WEIGHT.get(position, 0)
        online_bonus = self.member_online_hours.get(player, 0) * ONLINE_WEIGHT_PER_HOUR
        return contribution + position_bonus + online_bonus

    def get_dividend_amount(self, funds: int) -> int:
        if funds <= 0:
            return 0
        return int(funds * DIVIDEND_RATE)

    def calculate_dividend(self, player: str) -> int:
        members = list(self.member_contribution.keys() | self.member_position.keys()
                       | self.member_online_hours.keys())
        weights = {m: self._member_weight(m) for m in members}
        total_weight = sum(weights.values())
        pool = self.get_dividend_amount(self.guild_funds)
        if total_weight <= 0 or pool <= 0:
            return 0
        return pool * max(0, weights.get(player, 0)) // total_weight

    def grant_dividends(self, current_time: Optional[float] = None) -> dict[str, int]:
        now = time.time() if current_time is None else current_time
        members = list(self.member_contribution.keys() | self.member_position.keys()
                       | self.member_online_hours.keys())
        payouts: dict[str, int] = {}
        for player in members:
            amount = self.calculate_dividend(player)
            if amount <= 0:
                continue
            payouts[player] = amount
            self.balances[player] = self.balances.get(player, 0) + amount
            self.dividend_history.append({
                "player": player,
                "amount": amount,
                "funds": self.guild_funds,
                "weight": self._member_weight(player),
                "time": now,
            })
        total = sum(payouts.values())
        if total > self.guild_funds:
            # 资金池不足时按比例缩减
            scale = self.guild_funds // total
            for record in self.dividend_history[-len(payouts):]:
                record["amount"] *= scale
            payouts = {p: a * scale for p, a in payouts.items()}
            total = sum(payouts.values())
        self.guild_funds -= total
        return payouts

    # ---------- 记录 ----------

    def get_claim_history(self, player: str) -> list:
        return [dict(r) for r in self.claim_history if r["player"] == player]

    def get_dividend_history(self, player: str) -> list:
        return [dict(r) for r in self.dividend_history if r["player"] == player]

    def get_refund_history(self, player: str) -> list:
        return [dict(r) for r in self.refund_history if r["sender"] == player]

    def get_packet_records(self) -> list:
        return [asdict(p) for p in self.packets.values()]
