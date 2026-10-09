"""Unit tests for Phase 49: Algorithmic Compute Tokenomics & Cross-Desk Settlement Mesh."""

import pytest
from desk_gateway.swarm_tokenomics import (
    ComputeCreditLedger,
    PaymentChannelManager,
    CrossDeskClearinghouse,
    SettlementAnchorExporter,
    TokenomicsDrillSimulator,
)


def test_compute_credit_ledger_pricing_and_transfer():
    ledger = ComputeCreditLedger(base_price=0.01)

    # Dynamic pricing curve
    price_low = ledger.calculate_compute_price(node_load=0.1)
    price_high = ledger.calculate_compute_price(node_load=0.95)
    assert price_high > price_low

    # Account balances & transfers
    acc_a = ledger.get_or_create_account("desk-a-acc", "desk-a", 100.0)
    acc_b = ledger.get_or_create_account("desk-b-acc", "desk-b", 50.0)

    tx = ledger.transfer("desk-a-acc", "desk-b-acc", amount=20.0, fee=0.1)
    assert tx["amount"] == 20.0
    assert acc_a.balance == 79.9
    assert acc_b.balance == 70.0

    # Overdraft rejected
    with pytest.raises(ValueError, match="Insufficient balance"):
        ledger.transfer("desk-a-acc", "desk-b-acc", amount=500.0)


def test_payment_channel_lifecycle():
    mgr = PaymentChannelManager()

    chan = mgr.open_channel("desk-a", "desk-b", deposit_a=100.0, deposit_b=20.0)
    assert chan.transferred_a_to_b == 0.0

    # Micro-payment
    mgr.update_channel_state(chan.channel_id, payment_amount=30.0)
    assert chan.transferred_a_to_b == 30.0

    # Close channel
    res = mgr.close_channel(chan.channel_id)
    assert res["final_balance_a"] == 70.0
    assert res["final_balance_b"] == 50.0


def test_clearinghouse_anchor_and_drill():
    ledger = ComputeCreditLedger()
    ledger.get_or_create_account("d1", "desk-1", 100.0)
    ledger.get_or_create_account("d2", "desk-2", 100.0)

    clearinghouse = CrossDeskClearinghouse(ledger)
    batch = clearinghouse.execute_batch_clearing([{"from_id": "d1", "to_id": "d2", "amount": 10.0}])
    assert batch["total_settled"] == 10.0

    exporter = SettlementAnchorExporter()
    anchor = exporter.export_settlement_anchor(batch)
    assert anchor["status"] == "CONFIRMED"
    assert "solana_devnet" in anchor["target"]

    # Drill simulator
    drill = TokenomicsDrillSimulator.run_tokenomics_drill()
    assert drill["status"] == "PASS"
    for case_name, res in drill["test_cases"].items():
        assert res["passed"] is True, f"Failed case {case_name}"
