"""Extract only unambiguous, single-instrument trade disclosures from post text."""

import re
import unicodedata


NUMBER = r"(?:[0-9]{1,3}(?:,[0-9]{3}){1,3}|[0-9]{1,12})(?:\.[0-9]{1,10})?"
SYMBOL = r"\$?(?:[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z]{1,4})?|[0-9]{6}(?:\.(?:SH|SZ|BJ))?)"
EN_DETAILS = (
    rf"(?:(?P<qty>{NUMBER})\s+(?i:(?:(?:shares?|units?|coins?|tokens?)\s+(?:of\s+)?)?))?"
    rf"(?P<symbol>{SYMBOL})(?i:(?:\s+shares?)?)"
    rf"(?:\s*(?i:@|at\b)\s*(?:US\$|\$|USD\s*)?(?P<price>{NUMBER})(?i:(?:\s+(?:USD|each|per share))?))?"
)
CN_DETAILS = (
    rf"(?P<symbol>{SYMBOL})\s*(?:[,，]?\s*(?P<qty>{NUMBER})\s*(?:股|枚|份))?"
    rf"(?:\s*[,，]?\s*(?:成交价(?:格)?|委托价|限价|价格|均价|@)\s*[:：]?\s*"
    rf"(?P<currency_sign>[¥￥$])?(?P<price>{NUMBER})\s*(?P<currency_unit>元|美元)?)?"
)
EN_PREFIX = r"(?i:(?:(?:I|we)\s+)?(?:just\s+)?)"
CN_PREFIX = r"(?:我(?:们)?)?\s*(?:今天|今日|刚刚|刚|已经|已)?\s*"
DECLARATIONS = (
    re.compile(EN_PREFIX + r"(?i:(?P<verb>bought|purchased|sold)\s+)" + EN_DETAILS),
    re.compile(CN_PREFIX + r"(?P<verb>买入|卖出)(?:了)?\s*" + CN_DETAILS),
    re.compile(EN_PREFIX + r"(?i:(?:placed|submitted)\s+(?:(?:a|an)\s+)?(?:(?P<type>limit|market)\s+)?"
               r"(?P<verb>buy|sell)\s+order\s+for\s+)" + EN_DETAILS),
    re.compile(CN_PREFIX + r"(?:提交|挂出|挂了)(?:了)?\s*(?P<type>限价|市价)?(?P<verb>买单|卖单)"
               r"\s*[:：]?\s*" + CN_DETAILS),
    re.compile(CN_PREFIX + r"(?:下单|挂单)\s*(?P<type>限价|市价)?(?P<verb>买入|卖出)\s*" + CN_DETAILS),
)
HYPOTHETICAL = re.compile(
    r"\b(?:if|would|unless|hypothetical|paper trad(?:e|ing)|simulated|demo account|not real)\b"
    r"|\b(?:cancelled|canceled|just kidding)\b|如果|假如|模拟[盘交易]|纸上交易|撤单|并未|没有(?:买入|卖出)|[?？]", re.IGNORECASE
)
TRADE_VERB = re.compile(r"\b(?:bought|sold|purchased|buy order|sell order)\b|买入|卖出|买单|卖单", re.IGNORECASE)


def _declaration(text: str) -> re.Match[str] | None:
    text = unicodedata.normalize("NFKC", text).strip()
    if HYPOTHETICAL.search(text) or len(TRADE_VERB.findall(text)) != 1:
        return None
    # Only a complete opening declaration qualifies. A quoted opinion later in a post does not.
    opening = re.split(r"(?:[。;\n]|\.\s)", text, maxsplit=1)[0]
    opening = re.sub(r"\s+https?://\S+$", "", opening).strip().rstrip(".!。！").strip()
    return next((m for pattern in DECLARATIONS if (m := pattern.fullmatch(opening))), None)


def price_in_yuan(text: str, price: float | None) -> bool:
    if price is None:
        return False
    match = _declaration(text)
    if not match or not match["price"]:
        return False
    fields = match.groupdict()
    return (fields.get("currency_unit") == "元" and fields.get("currency_sign") != "$"
            and float(match["price"].replace(",", "")) == price)


def extract_signal(text: str) -> dict | None:
    match = _declaration(text)
    if not match:
        return None
    if match["symbol"].isalpha() and not (match["qty"] or match["price"]):
        return None
    numbers = {key: float(match[key].replace(",", "")) if match[key] else None for key in ("price", "qty")}
    if any(value is not None and value <= 0 for value in numbers.values()):
        return None
    order_type = (match.groupdict().get("type") or "").lower()
    return {
        "kind": "order" if "type" in match.groupdict() else "trade",
        "orderType": {"limit": "limit", "限价": "limit", "market": "market", "市价": "market"}.get(order_type),
        "action": "sell" if match["verb"].lower() in ("sold", "sell", "卖出", "卖单") else "buy",
        "symbol": match["symbol"].lstrip("$"), "price": numbers["price"], "quantity": numbers["qty"],
    }
