"""帮派红包与分红系统 - 红态测试"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from guild.redpacket import RedPacketSystem, RedPacket

class TestAmountLimit:
    def test_zero_amount_rejected(self):
        rps = RedPacketSystem()
        ok, msg = rps.create_packet("p1", 0)
        assert ok == False

class TestLuckyPacket:
    def test_lucky_packet_random_shares(self):
        rps = RedPacketSystem(seed=42)
        rps.packets["rp1"] = RedPacket("rp1", "p1", 100, type="lucky")
        s1 = rps.claim_packet("rp1", "p2")
        s2 = rps.claim_packet("rp1", "p3")
        assert s1 != s2  # 拼手气应该不同

class TestDividendByContribution:
    def test_higher_contribution_gets_more_dividend(self):
        rps = RedPacketSystem()
        rps.member_contribution = {"p1": 1000, "p2": 100}
        d1 = rps.calculate_dividend("p1")
        d2 = rps.calculate_dividend("p2")
        assert d1 > d2

class TestExpiration:
    def test_packet_expires_after_24h(self):
        rps = RedPacketSystem()
        rps.packets["rp1"] = RedPacket("rp1", "p1", 100, expire_time=100.0)
        assert rps.is_expired("rp1", 100.0) == False
        assert rps.is_expired("rp1", 100000.0) == True

class TestDividendByFunds:
    def test_more_funds_gives_more_dividend(self):
        rps = RedPacketSystem()
        d1 = rps.get_dividend_amount(1000)
        d2 = rps.get_dividend_amount(100000)
        assert d2 > d1

class TestPacketTypes:
    def test_multiple_packet_types(self):
        rps = RedPacketSystem()
        types = rps.get_packet_types()
        assert len(types) > 1

class TestClaimHistory:
    def test_claim_history_recorded(self):
        rps = RedPacketSystem()
        rps.packets["rp1"] = RedPacket("rp1", "p1", 100)
        rps.claim_packet("rp1", "p2")
        history = rps.get_claim_history("p2")
        assert len(history) > 0
