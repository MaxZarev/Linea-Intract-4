from __future__ import annotations

from decimal import Decimal

from web3.types import Wei


class Amount:
    wei: Wei | int
    ether: Decimal
    ether_float: float
    decimals: int

    def __init__(self, amount: int | float | str | Decimal, decimals: int = 18, wei: bool = False) -> None:

        if wei:
            self.wei = int(amount)
            self.ether = Decimal(str(amount)) / 10 ** decimals
            self.ether_float = float(self.ether)
        else:
            self.wei = int(amount * 10 ** decimals)
            self.ether = Decimal(str(amount))
            self.ether_float = float(amount)

        self.decimals = decimals

    def __str__(self) -> str:
        return str(self.ether)

    def __repr__(self) -> str:
        return f"Amount(ether={self.ether_float}, wei={self.wei}, decimals={self.decimals})"