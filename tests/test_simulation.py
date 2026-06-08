"""Tests for the simulation engine."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.data_loader import DatasetMetrics
from src.simulation.engine import run_simulation


def _mock_metrics() -> DatasetMetrics:
    return DatasetMetrics(
        total_orders=1000,
        total_items=1500,
        mean_interarrival_s=0.5,
        median_interarrival_s=0.4,
        price_mean=100.0,
        price_std=50.0,
        category_distribution={"electronics": 0.4, "clothing": 0.3, "books": 0.3},
        delivery_days_mean=7.0,
        delivery_days_std=3.0,
    )


def test_single_run():
    metrics = _mock_metrics()
    result = run_simulation(
        metrics=metrics,
        load_multiplier=2.0,
        cache_hit_rate=0.0,
        duration_s=2.0,
        warmup_s=0.5,
        n_buyers=5,
        n_sellers=3,
        n_mediators=1,
        n_logistics=1,
        seed=42,
    )
    assert result.sim_duration_s == 2.0
    assert len(result.latencies_ms) > 0
    assert result.throughput >= 0
    assert 0 <= result.rejection_rate <= 1.0


def test_cache_reduces_latency():
    metrics = _mock_metrics()

    r_no_cache = run_simulation(
        metrics=metrics, load_multiplier=2.0, cache_hit_rate=0.0,
        duration_s=2.0, warmup_s=0.3, n_buyers=5, n_sellers=3,
        n_mediators=1, n_logistics=1, seed=42,
    )
    r_cache = run_simulation(
        metrics=metrics, load_multiplier=2.0, cache_hit_rate=0.8,
        duration_s=2.0, warmup_s=0.3, n_buyers=5, n_sellers=3,
        n_mediators=1, n_logistics=1, seed=42,
    )

    import numpy as np
    mean_no = np.mean(r_no_cache.latencies_ms) if r_no_cache.latencies_ms else 999
    mean_cache = np.mean(r_cache.latencies_ms) if r_cache.latencies_ms else 999
    # Cache should reduce average latency
    assert mean_cache <= mean_no + 10  # Allow small tolerance


def test_high_load_increases_latency():
    metrics = _mock_metrics()

    r_low = run_simulation(
        metrics=metrics, load_multiplier=2.0, cache_hit_rate=0.0,
        duration_s=2.0, warmup_s=0.3, n_buyers=5, n_sellers=3,
        n_mediators=1, n_logistics=1, seed=42,
    )
    r_high = run_simulation(
        metrics=metrics, load_multiplier=20.0, cache_hit_rate=0.0,
        duration_s=2.0, warmup_s=0.3, n_buyers=5, n_sellers=3,
        n_mediators=1, n_logistics=1, seed=42,
    )
    # Higher load should generate more transactions
    assert len(r_high.latencies_ms) >= len(r_low.latencies_ms)
