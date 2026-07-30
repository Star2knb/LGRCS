"""
RevAc — Multi-Channel e-Payment Integration Layer
=================================================
Alliance Consulting & Digital Solutions Ltd (ACDSL)

One adapter per e-channel in the collecting-bank integration scope:

    POS         POS terminals deployed to and in use by the Area Council
    OTC         Over-the-counter (teller) payments at bank branches
    IB_MB       Internet banking and mobile banking transfers
    USSD        USSD payment channels
    FIRSTMONIE  Agent banking network

Every adapter implements the same contract so the core platform is
channel-agnostic:

    validate(payload)   -> (ok, error)      structural validation
    normalise(payload)  -> ChannelTxn       canonical transaction record
    verify_signature()  -> bool             HMAC-SHA256 authenticity check

Inbound traffic arrives either as a real-time webhook (POS, USSD,
FirstMonie, IB/MB) or as an end-of-day settlement file (OTC). Both land in
`channel_transaction_feed` and are matched to `payment` rows by the
reconciliation engine.

NOTE: Endpoint URLs, credential handling and payload field names are
INDICATIVE and must be aligned with the collecting bank's published API
specification during the integration workstream.
"""

import hashlib
import hmac
import json
from dataclasses import dataclass, asdict
from datetime import datetime


# ---------------------------------------------------------------------------
# Canonical transaction record
# ---------------------------------------------------------------------------

@dataclass
class ChannelTxn:
    channel_code: str
    bank_txn_ref: str
    bill_ref: str
    amount: float
    narration: str
    value_date: str
    payer_msisdn: str = ""
    terminal_id: str = ""
    agent_code: str = ""
    raw: str = ""

    def as_dict(self):
        return asdict(self)


class ChannelError(Exception):
    pass


# ---------------------------------------------------------------------------
# Base adapter
# ---------------------------------------------------------------------------

class BaseChannelAdapter:
    code = "BASE"
    name = "Base Channel"
    mode = "WEBHOOK"          # WEBHOOK | FILE | POLL
    required = ()

    def __init__(self, secret: str):
        self.secret = secret

    # -- authenticity --------------------------------------------------
    def verify_signature(self, raw_body: bytes, signature: str) -> bool:
        """HMAC-SHA256 over the raw request body, hex digest."""
        if not signature:
            return False
        expected = hmac.new(
            self.secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature.lower())

    def sign(self, raw_body: bytes) -> str:
        return hmac.new(self.secret.encode(), raw_body, hashlib.sha256).hexdigest()

    # -- validation ----------------------------------------------------
    def validate(self, payload: dict):
        missing = [f for f in self.required
                   if f not in payload or payload[f] in (None, "")]
        if missing:
            return False, f"Missing required field(s): {', '.join(missing)}"
        try:
            amount = float(payload.get(self.amount_field, 0))
        except (TypeError, ValueError):
            return False, "Amount is not a valid number"
        if amount <= 0:
            return False, "Amount must be greater than zero"
        return True, None

    amount_field = "amount"

    def normalise(self, payload: dict) -> ChannelTxn:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# 1. POS terminals deployed to the Council
# ---------------------------------------------------------------------------

class PosAdapter(BaseChannelAdapter):
    code = "POS"
    name = "POS Terminal"
    mode = "WEBHOOK"
    required = ("terminalId", "rrn", "amount", "billRef")
    amount_field = "amount"

    def normalise(self, payload):
        # POS amounts are conventionally transmitted in kobo
        amount = float(payload["amount"]) / 100.0 if payload.get("amountInKobo") \
            else float(payload["amount"])
        return ChannelTxn(
            channel_code=self.code,
            bank_txn_ref=str(payload["rrn"]),
            bill_ref=str(payload["billRef"]),
            amount=amount,
            narration=payload.get("narration", "POS collection"),
            value_date=payload.get("transactionDate", datetime.utcnow().strftime("%Y-%m-%d")),
            terminal_id=str(payload["terminalId"]),
            agent_code=payload.get("agentCode", ""),
            raw=json.dumps(payload),
        )


# ---------------------------------------------------------------------------
# 2. Over-the-counter (teller) payments at bank branches
# ---------------------------------------------------------------------------

class OtcAdapter(BaseChannelAdapter):
    code = "OTC"
    name = "Over-the-Counter (Branch Teller)"
    mode = "FILE"            # end-of-day settlement file / statement feed
    required = ("tellerRef", "amount", "billRef", "branchCode")

    def normalise(self, payload):
        return ChannelTxn(
            channel_code=self.code,
            bank_txn_ref=str(payload["tellerRef"]),
            bill_ref=str(payload["billRef"]),
            amount=float(payload["amount"]),
            narration=f"Branch {payload['branchCode']} teller lodgement",
            value_date=payload.get("valueDate", datetime.utcnow().strftime("%Y-%m-%d")),
            raw=json.dumps(payload),
        )

    def parse_settlement_file(self, rows):
        """Accepts a list of dict rows from the daily CSV/statement export."""
        out = []
        for row in rows:
            ok, err = self.validate(row)
            if not ok:
                raise ChannelError(f"Settlement row rejected: {err}")
            out.append(self.normalise(row))
        return out


# ---------------------------------------------------------------------------
# 3. Internet banking and mobile banking transfers
# ---------------------------------------------------------------------------

class InternetMobileBankingAdapter(BaseChannelAdapter):
    code = "IB_MB"
    name = "Internet / Mobile Banking Transfer"
    mode = "WEBHOOK"
    required = ("sessionId", "amount", "billRef")

    def normalise(self, payload):
        return ChannelTxn(
            channel_code=self.code,
            bank_txn_ref=str(payload["sessionId"]),
            bill_ref=str(payload["billRef"]),
            amount=float(payload["amount"]),
            narration=payload.get("narration", "Bank transfer"),
            value_date=payload.get("valueDate", datetime.utcnow().strftime("%Y-%m-%d")),
            payer_msisdn=payload.get("payerPhone", ""),
            raw=json.dumps(payload),
        )


# ---------------------------------------------------------------------------
# 4. USSD payment channel
# ---------------------------------------------------------------------------

class UssdAdapter(BaseChannelAdapter):
    code = "USSD"
    name = "USSD Payment"
    mode = "WEBHOOK"
    required = ("ussdRef", "msisdn", "amount", "billRef")

    def normalise(self, payload):
        return ChannelTxn(
            channel_code=self.code,
            bank_txn_ref=str(payload["ussdRef"]),
            bill_ref=str(payload["billRef"]),
            amount=float(payload["amount"]),
            narration=f"USSD payment from {payload['msisdn']}",
            value_date=payload.get("valueDate", datetime.utcnow().strftime("%Y-%m-%d")),
            payer_msisdn=str(payload["msisdn"]),
            raw=json.dumps(payload),
        )

    # USSD menu tree served to the payer's handset
    MENU = {
        "root": "Welcome to KAC Revenue\n1. Pay a bill\n2. Check balance\n3. Verify receipt",
        "1": "Enter your Bill Reference:",
        "2": "Enter your Payer ID:",
        "3": "Enter Receipt Reference:",
    }


# ---------------------------------------------------------------------------
# 5. Agent banking network
# ---------------------------------------------------------------------------

class AgentBankingAdapter(BaseChannelAdapter):
    code = "FIRSTMONIE"
    name = "Agent Banking Network"
    mode = "WEBHOOK"
    required = ("agentTxnRef", "agentId", "amount", "billRef")

    def normalise(self, payload):
        return ChannelTxn(
            channel_code=self.code,
            bank_txn_ref=str(payload["agentTxnRef"]),
            bill_ref=str(payload["billRef"]),
            amount=float(payload["amount"]),
            narration=f"Agent banking collection via agent {payload['agentId']}",
            value_date=payload.get("valueDate", datetime.utcnow().strftime("%Y-%m-%d")),
            agent_code=str(payload["agentId"]),
            payer_msisdn=payload.get("payerPhone", ""),
            raw=json.dumps(payload),
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ADAPTERS = {
    a.code: a for a in (
        PosAdapter,
        OtcAdapter,
        InternetMobileBankingAdapter,
        UssdAdapter,
        AgentBankingAdapter,
    )
}


def get_adapter(channel_code: str, secret: str) -> BaseChannelAdapter:
    cls = ADAPTERS.get(channel_code.upper())
    if not cls:
        raise ChannelError(f"Unknown channel code: {channel_code}")
    return cls(secret)


def channel_catalogue():
    return [
        {"code": c.code, "name": c.name, "mode": c.mode, "required": list(c.required)}
        for c in ADAPTERS.values()
    ]
