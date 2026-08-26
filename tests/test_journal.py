from agent.journal import (
    connect,
    is_closing,
    is_opening,
    net_credit,
    order_source,
    pair_round_trips,
    reconcile,
)


def mk_order(oid, symbols, intents, filled_at, avg_price, qty="5", leg_prices=None,
             client_order_id=None):
    return {
        "id": oid,
        "qty": qty,
        "filled_at": filled_at,
        "filled_avg_price": avg_price,
        "client_order_id": client_order_id,
        "legs": [
            {"symbol": s, "side": "sell" if i.startswith("sell") else "buy",
             "position_intent": i,
             **({"filled_avg_price": p} if leg_prices else {})}
            for (s, i), p in zip(zip(symbols, intents), leg_prices or [None] * len(symbols))
        ],
    }


SHORT, LONG = "NVDA260911P00197500", "NVDA260911P00192500"


def test_intent_detection():
    o = mk_order("a", [SHORT, LONG], ["sell_to_open", "buy_to_open"], "2026-08-25T14:00:00Z", "-1.13")
    c = mk_order("b", [SHORT, LONG], ["buy_to_close", "sell_to_close"], "2026-08-26T15:00:00Z", "0.55")
    assert is_opening(o) and not is_closing(o)
    assert is_closing(c) and not is_opening(c)


def test_pairing_open_and_close():
    orders = [
        mk_order("a", [SHORT, LONG], ["sell_to_open", "buy_to_open"], "2026-08-25T14:00:00Z", "-1.13"),
        mk_order("b", [SHORT, LONG], ["buy_to_close", "sell_to_close"], "2026-08-26T15:00:00Z", "0.55"),
    ]
    trips = pair_round_trips(orders)
    assert len(trips) == 1
    t = trips[0]
    assert t["status"] == "closed"
    assert t["entry_credit"] == 1.13
    assert t["exit_debit"] == 0.55
    assert t["realized_pl"] == round((1.13 - 0.55) * 100 * 5, 2)  # +290.00


def test_unclosed_stays_open():
    orders = [mk_order("a", [SHORT, LONG], ["sell_to_open", "buy_to_open"], "2026-08-25T14:00:00Z", "-1.13")]
    trips = pair_round_trips(orders)
    assert trips[0]["status"] == "open"
    assert trips[0]["realized_pl"] is None


def test_fifo_multiple_rounds():
    orders = [
        mk_order("a1", [SHORT, LONG], ["sell_to_open", "buy_to_open"], "2026-08-25T14:00:00Z", "-1.00"),
        mk_order("c1", [SHORT, LONG], ["buy_to_close", "sell_to_close"], "2026-08-25T18:00:00Z", "0.50"),
        mk_order("a2", [SHORT, LONG], ["sell_to_open", "buy_to_open"], "2026-08-26T14:00:00Z", "-1.20"),
    ]
    trips = pair_round_trips(orders)
    assert [t["status"] for t in trips] == ["closed", "open"]


def test_net_credit_prefers_leg_fills():
    """The 2026-08-26 smoke test: legs 0.37/0.34, parent -0.03 -> 0.03 either way,
    but when they disagree the legs (what actually happened) win."""
    o = mk_order("a", [SHORT, LONG], ["sell_to_open", "buy_to_open"],
                 "2026-08-26T15:27:12Z", "-0.05", leg_prices=["0.37", "0.34"])
    assert net_credit(o) == 0.03


def test_net_credit_fallback_parent():
    o = mk_order("a", [SHORT, LONG], ["sell_to_open", "buy_to_open"],
                 "2026-08-25T14:00:00Z", "-1.13")
    assert net_credit(o) == 1.13


def test_monitor_and_journal_agree_on_entry_credit():
    """One definition: reconstruct_spreads fed the journal credit must match
    the journal's own fill-derived value exactly."""
    from types import SimpleNamespace

    from agent.execution.monitor import reconstruct_spreads

    o = mk_order("a", [SHORT, LONG], ["sell_to_open", "buy_to_open"],
                 "2026-08-25T14:00:00Z", "-1.13", leg_prices=["3.50", "2.37"])
    credit = net_credit(o)
    positions = [
        SimpleNamespace(symbol=SHORT, qty="-5", avg_entry_price="3.50"),
        SimpleNamespace(symbol=LONG, qty="5", avg_entry_price="2.37"),
    ]
    s = reconstruct_spreads(positions, {(SHORT, LONG): credit})[0]
    assert s.entry_credit == credit == 1.13
    assert s.credit_source == "journal"


def test_source_manual_when_id_not_agent():
    smoke = mk_order("a", [SHORT, LONG], ["sell_to_open", "buy_to_open"],
                     "2026-08-26T15:27:12Z", "-0.03", client_order_id="tf-smoke-cli-001")
    agent = mk_order("b", [SHORT, LONG], ["sell_to_open", "buy_to_open"],
                     "2026-08-26T15:27:12Z", "-1.13", client_order_id="tf-open-NVDA-ab12cd34")
    assert order_source(smoke) == "manual"
    assert order_source(agent) == "agent"
    trips = pair_round_trips([smoke, agent])
    assert [t["source"] for t in trips] == ["manual", "agent"]


def test_reconcile_upsert_idempotent(tmp_path):
    con = connect(tmp_path / "t.db")
    orders = [
        mk_order("a", [SHORT, LONG], ["sell_to_open", "buy_to_open"], "2026-08-25T14:00:00Z", "-1.13"),
    ]
    reconcile(orders, con)
    orders.append(
        mk_order("b", [SHORT, LONG], ["buy_to_close", "sell_to_close"], "2026-08-26T15:00:00Z", "0.55"))
    reconcile(orders, con)
    reconcile(orders, con)  # idempotent
    rows = con.execute("SELECT * FROM trades").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "closed"
    assert rows[0]["realized_pl"] == 290.0
    assert rows[0]["underlying"] == "NVDA"
