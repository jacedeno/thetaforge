from agent.journal import pair_round_trips, is_opening, is_closing, connect, reconcile


def mk_order(oid, symbols, intents, filled_at, avg_price, qty="5"):
    return {
        "id": oid,
        "qty": qty,
        "filled_at": filled_at,
        "filled_avg_price": avg_price,
        "legs": [
            {"symbol": s, "side": "sell" if i.startswith("sell") else "buy", "position_intent": i}
            for s, i in zip(symbols, intents)
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
