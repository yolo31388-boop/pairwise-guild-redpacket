"""帮派红包与分红系统 - 含7个bug"""
import random
from dataclasses import dataclass, field

@dataclass
class RedPacket:
    rpid: str
    sender: str
    amount: int
    type: str = "normal"  # normal/lucky/exclusive
    claimed: list = field(default_factory=list)
    expire_time: float = 0  # bug4: 无过期

class RedPacketSystem:
    def __init__(self, seed=42):
        self.rng = random.Random(seed)
        self.packets: dict[str, RedPacket] = {}
        self.guild_funds: int = 100000
        self.member_contribution: dict[str, int] = {}  # bug3: 不看贡献

    def create_packet(self, sender: str, amount: int) -> tuple[bool, str]:
        # bug1: 无金额限制
        return True, "created"

    def claim_packet(self, rpid: str, player: str) -> int:
        # bug2: 先到先得纯随机
        packet = self.packets[rpid]
        share = packet.amount // (len(packet.claimed) + 1)
        packet.claimed.append(player)
        return share

    def calculate_dividend(self, player: str) -> int:
        # bug3: 不看贡献平均
        return self.guild_funds // 100

    def is_expired(self, rpid: str, current_time: float) -> bool:
        # bug4: 无过期
        return False

    def get_dividend_amount(self, funds: int) -> int:
        # bug5: 固定金额
        return 100

    def get_packet_types(self) -> list:
        # bug6: 无类型区分
        return ["normal"]

    def get_claim_history(self, player: str) -> list:
        # bug7: 无记录
        return []
