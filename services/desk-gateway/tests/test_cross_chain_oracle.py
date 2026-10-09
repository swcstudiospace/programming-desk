import pytest
from desk_gateway.cross_chain_oracle import (
    OracleReport,
    MedianizerFilter,
    ThresholdOracleAttestor,
    OracleAggregator,
    OracleAnchorExporter,
    CrossChainOracleDrillSimulator,
)

def test_medianizer_filter():
    reports = [
        OracleReport(source_id="s1", feed_name="BTC/USD", value=100.0),
        OracleReport(source_id="s2", feed_name="BTC/USD", value=102.0),
        OracleReport(source_id="s3", feed_name="BTC/USD", value=98.0),
        OracleReport(source_id="s4", feed_name="BTC/USD", value=101.0),
        OracleReport(source_id="s5", feed_name="BTC/USD", value=500.0),  # 500 is outlier
    ]
    med, valid, pruned = MedianizerFilter.filter_reports(reports, max_deviation_ratio=0.20)
    assert pruned == 1
    assert len(valid) == 4
    assert 100.0 <= med <= 101.5


def test_threshold_oracle_attestor():
    attestor = ThresholdOracleAttestor(signing_secret="oracle-secret")
    finalized = attestor.attest_feed(
        feed_name="BTC/USD",
        median_value=60000.5,
        report_count=5,
        outliers_pruned=1,
        attesting_seats=["lead", "systems"],
    )
    assert finalized.feed_name == "BTC/USD"
    assert finalized.median_value == 60000.5
    assert len(finalized.threshold_signature) == 64
    assert finalized.attesting_seats == ["lead", "systems"]


def test_oracle_aggregator_and_anchor():
    aggregator = OracleAggregator()

    aggregator.ingest_report(OracleReport(source_id="src-1", feed_name="ETH/USD", value=3000.0))
    aggregator.ingest_report(OracleReport(source_id="src-2", feed_name="ETH/USD", value=3050.0))
    aggregator.ingest_report(OracleReport(source_id="src-3", feed_name="ETH/USD", value=15000.0)) # Outlier

    feed = aggregator.finalize_feed("ETH/USD", min_reports=3)
    assert feed.feed_name == "ETH/USD"
    assert feed.median_value == 3025.0
    assert feed.report_count == 3
    assert feed.outliers_pruned == 1
    assert len(feed.threshold_signature) == 64

    # Verify Solana devnet anchor
    exporter = OracleAnchorExporter()
    anchor = exporter.export_oracle_anchor(feed)
    assert anchor["feed_name"] == "ETH/USD"
    assert "slot_id" in anchor
    assert "digest" in anchor
    assert anchor["status"] == "CONFIRMED"


def test_cross_chain_oracle_drill_simulator():
    results = CrossChainOracleDrillSimulator.run_drill()
    assert results["status"] == "PASS"
    for test_key, res in results["test_cases"].items():
        assert res["passed"] is True
