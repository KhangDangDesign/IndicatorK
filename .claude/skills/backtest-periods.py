#!/usr/bin/env python3
"""Backtest strategies across 3 fixed market periods for quick strategy validation.

Usage:
    python .claude/skills/backtest-periods.py [strategy_name]

Market periods:
    - Bear: 2022-04-04 → 2022-11-15 (Vietnamese market crash)
    - Sideway: 2024-01-02 → 2024-06-28 (Consolidation period)
    - Bull: 2025-01-02 → 2025-06-30 (Growth period)
"""

import sys
from datetime import date
from pathlib import Path
from typing import Dict, Any
import tempfile

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.backtest.cli import run_backtest
from src.utils.logging_setup import setup_logging


# Market periods for testing different conditions
MARKET_PERIODS = {
    "Bear": {
        "start": date(2022, 4, 4),
        "end": date(2022, 11, 15),
        "description": "Vietnamese market crash"
    },
    "Sideway": {
        "start": date(2024, 1, 2),
        "end": date(2024, 6, 28),
        "description": "Consolidation period"
    },
    "Bull": {
        "start": date(2025, 1, 2),
        "end": date(2025, 6, 30),
        "description": "Growth period"
    }
}

# Standard backtest parameters for consistency
STANDARD_PARAMS = {
    "initial_cash": 20_000_000,  # 20M VND
    "trades_per_week": 4,
    "tie_breaker": "worst",  # Conservative approach
    "exit_mode": "tpsl_only",  # Automatic TP/SL only
    "mode": "generate",  # Generate fresh plans per week
    "run_range": False,  # Single run per period
}


def extract_key_metrics(summary: Dict[str, Any]) -> Dict[str, float]:
    """Extract key performance metrics from backtest summary."""
    # Calculate total return percentage from final_value and initial_cash
    initial_cash = summary.get("initial_cash", 20_000_000)
    final_value = summary.get("final_value", initial_cash)
    total_return_pct = ((final_value - initial_cash) / initial_cash) * 100 if initial_cash > 0 else 0

    return {
        "total_return_pct": total_return_pct,
        "cagr_pct": (summary.get("cagr", 0) * 100),  # Convert from decimal to percentage
        "sharpe_ratio": summary.get("sharpe_ratio", 0),
        "max_drawdown_pct": (summary.get("max_drawdown", 0) * 100),  # Convert from decimal to percentage
        "win_rate_pct": (summary.get("win_rate", 0) * 100),  # Convert from decimal to percentage
        "profit_factor": summary.get("profit_factor", 0),
        "total_trades": summary.get("num_trades", 0),  # Correct field name
        "trading_days": summary.get("trading_days", 0)
    }


def format_results_table(results: Dict[str, Dict[str, Any]]) -> str:
    """Format backtest results into a readable comparison table."""

    header = """
╔═══════════════════════════════════════════════════════════════════════════════╗
║                          MULTI-PERIOD BACKTEST RESULTS                        ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

    table_header = f"""
{'Period':<10} {'Date Range':<25} {'Total%':<8} {'CAGR%':<8} {'Sharpe':<8} {'MaxDD%':<8} {'WinRate%':<10} {'PF':<6} {'Trades':<8}
{'-'*100}"""

    rows = []
    for period_name, data in results.items():
        period_info = MARKET_PERIODS[period_name]
        metrics = data["metrics"]

        row = f"{period_name:<10} {period_info['start']} → {period_info['end']:<10} " \
              f"{metrics['total_return_pct']:<8.1f} {metrics['cagr_pct']:<8.1f} " \
              f"{metrics['sharpe_ratio']:<8.2f} {metrics['max_drawdown_pct']:<8.1f} " \
              f"{metrics['win_rate_pct']:<10.1f} {metrics['profit_factor']:<6.2f} " \
              f"{int(metrics['total_trades']):<8}"
        rows.append(row)

    # Find best and worst periods
    best_period = max(results.keys(), key=lambda p: results[p]["metrics"]["sharpe_ratio"])
    worst_period = min(results.keys(), key=lambda p: results[p]["metrics"]["sharpe_ratio"])

    summary = f"""
{'-'*100}
📊 SUMMARY:
   • Best Period: {best_period} (Sharpe: {results[best_period]['metrics']['sharpe_ratio']:.2f})
   • Worst Period: {worst_period} (Sharpe: {results[worst_period]['metrics']['sharpe_ratio']:.2f})
   • Average CAGR: {sum(r['metrics']['cagr_pct'] for r in results.values()) / len(results):.1f}%
   • Average Sharpe: {sum(r['metrics']['sharpe_ratio'] for r in results.values()) / len(results):.2f}
   • Average Max DD: {sum(r['metrics']['max_drawdown_pct'] for r in results.values()) / len(results):.1f}%
"""

    return header + table_header + "\n" + "\n".join(rows) + summary


def main():
    """Run backtests across all market periods and display results."""

    setup_logging()

    # Handle optional strategy parameter
    if len(sys.argv) > 1:
        strategy_name = sys.argv[1]
        print(f"🎯 Testing strategy: {strategy_name}")
        print("💡 Note: Ensure config/strategy.yml has 'active: {strategy_name}' set")
    else:
        print("🎯 Testing active strategy from config/strategy.yml")

    print(f"⏱️  Running backtests for {len(MARKET_PERIODS)} market periods...")
    print()

    results = {}

    for period_name, period_info in MARKET_PERIODS.items():
        print(f"📈 Running {period_name} period ({period_info['start']} → {period_info['end']})...")

        try:
            # Use temporary directory for each backtest to avoid conflicts
            with tempfile.TemporaryDirectory() as temp_dir:
                output_dir = run_backtest(
                    from_date=period_info["start"],
                    to_date=period_info["end"],
                    output_base=temp_dir,
                    **STANDARD_PARAMS
                )

                # Read the summary.json that was written
                import json
                summary_file = output_dir / "summary.json"
                if summary_file.exists():
                    with open(summary_file) as f:
                        summary_data = json.load(f)

                    results[period_name] = {
                        "metrics": extract_key_metrics(summary_data),
                        "period_info": period_info
                    }
                    print(f"   ✅ {period_name}: CAGR {results[period_name]['metrics']['cagr_pct']:.1f}%, "
                          f"Sharpe {results[period_name]['metrics']['sharpe_ratio']:.2f}")
                else:
                    print(f"   ❌ {period_name}: Summary file not found")

        except Exception as e:
            print(f"   ❌ {period_name}: Failed with error: {e}")
            # Continue with other periods
            continue

    # Display results
    if results:
        print(format_results_table(results))

        # Save detailed results to file
        results_file = project_root / "data" / "backtest_periods_results.json"
        results_file.parent.mkdir(exist_ok=True)

        import json
        with open(results_file, 'w') as f:
            # Convert date objects to strings for JSON serialization
            serializable_results = {}
            for period_name, data in results.items():
                serializable_results[period_name] = {
                    "metrics": data["metrics"],
                    "period_info": {
                        "start": data["period_info"]["start"].isoformat(),
                        "end": data["period_info"]["end"].isoformat(),
                        "description": data["period_info"]["description"]
                    }
                }
            json.dump(serializable_results, f, indent=2)

        print(f"💾 Detailed results saved to: {results_file}")

    else:
        print("❌ No successful backtest results to display")
        sys.exit(1)


if __name__ == "__main__":
    main()