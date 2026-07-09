"""Crypto 'fundamentals' = tokenomics + สภาพคล่อง (แทนงบการเงินของหุ้น).

crypto ไม่มีรายได้/กำไร/margin — สิ่งที่ใกล้เคียง 'พื้นฐาน' ที่สุดคือ:
  - supply schedule: circulating vs max supply -> ยังจะเฟ้อ (dilution) อีกแค่ไหน / ใกล้เพดานหรือยัง
  - scarcity: มี hard cap ไหม (BTC=21M) หรือ uncapped (ETH)
  - liquidity: 24h volume เทียบ market cap -> ซื้อขายคล่องแค่ไหน
ทั้งหมดดึงจาก yfinance info (ชุดเดียวกับหุ้น) — ไม่เพิ่ม dependency/API ใหม่ (thin slice).
ลึกกว่านี้ (active addresses, fees/revenue, TVL) = on-chain source รอบหน้า.
"""
from dataclasses import dataclass

import yfinance as yf

from src.domain.interfaces import Fundamentals, FundamentalsProvider, Fact
from src.providers.crypto.price import yf_symbol


@dataclass
class CryptoFundamentals(Fundamentals):
    name: str | None = None
    price: float | None = None
    market_cap: float | None = None
    volume_24h: float | None = None
    circulating_supply: float | None = None
    max_supply: float | None = None          # None = ไม่มีเพดาน (เฟ้อได้เรื่อยๆ เช่น ETH)
    total_supply: float | None = None

    def to_facts(self) -> list[Fact]:
        facts: list[Fact] = []

        def add(label, value, unit):
            if value is not None:
                facts.append(Fact(label=label, value=float(value), unit=unit, period="spot"))

        add("Market Cap", self.market_cap, "USD")
        add("24h Volume", self.volume_24h, "USD")
        # สภาพคล่อง: ปริมาณซื้อขายต่อวันเป็น % ของ market cap (สูง = คล่อง/มีคนเทรดจริง)
        if self.volume_24h and self.market_cap:
            add("Volume / Market Cap", self.volume_24h / self.market_cap * 100, "%")
        add("Circulating Supply", self.circulating_supply, "coins")
        add("Max Supply", self.max_supply, "coins")

        # tokenomics ที่ต้องมี max supply ถึงคำนวณได้ (uncapped -> ข้าม)
        if self.max_supply and self.circulating_supply:
            # ออกมาแล้วกี่ % ของเพดาน — ใกล้ 100% = เฟ้อในอนาคตน้อย (scarcity สูง)
            add("Supply Issued", self.circulating_supply / self.max_supply * 100, "%")
            # เหรียญที่ยังไม่ออก เทียบของที่ออกแล้ว = แรงเฟ้อในอนาคต (สูง = ระวัง dilution)
            remaining = self.max_supply - self.circulating_supply
            add("Dilution Ahead", remaining / self.circulating_supply * 100, "%")
            if self.price:
                add("Fully Diluted Valuation", self.max_supply * self.price, "USD")

        return facts


class CryptoFundamentalsProvider(FundamentalsProvider):
    def get_fundamentals(self, ticker: str) -> CryptoFundamentals:
        info = yf.Ticker(yf_symbol(ticker)).info
        return CryptoFundamentals(
            name=info.get("name"),
            price=info.get("regularMarketPrice") or info.get("lastPrice"),
            market_cap=info.get("marketCap"),
            volume_24h=info.get("volume24Hr") or info.get("volume"),
            circulating_supply=info.get("circulatingSupply"),
            max_supply=info.get("maxSupply"),
            total_supply=info.get("totalSupply"),
        )
