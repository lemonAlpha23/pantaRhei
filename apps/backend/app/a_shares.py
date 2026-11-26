from datetime import timedelta, timezone
from typing import Literal


CHINA_STANDARD_TIME = timezone(timedelta(hours=8))


def exchange_suffix(symbol: str) -> Literal["SH", "SZ"] | None:
    if len(symbol) == 6 and symbol.isascii() and symbol.isdecimal():
        if symbol.startswith(("600", "601", "603", "605", "688")):
            return "SH"
        # The 001001–001199 and 309800–309999 ranges are depositary receipts.
        if (symbol.startswith("000") or "001200" <= symbol <= "004999"
                or "300000" <= symbol <= "309799"):
            return "SZ"
    return None
