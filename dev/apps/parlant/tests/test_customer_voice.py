from __future__ import annotations

from app.sim.customer_voice import clean_customer_message


def test_clean_customer_message_rejects_broker_echo() -> None:
    brokerish = "我是经纪人，不站队某一家，咱们可以给你配一套方案，只看条款和性价比。"
    out = clean_customer_message(brokerish)
    assert "我是经纪人" not in out
    assert len(out) <= 200
