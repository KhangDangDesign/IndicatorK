---
name: backtest-periods
description: Backtest strategies across 3 fixed market periods (Bear, Sideway, Bull) for quick validation
---

# Market Period Backtesting Skill

Run the backtest-periods.py script to evaluate the active strategy across 3 predefined market periods:

- **Bear Market**: 2022-04-04 → 2022-11-15 (Vietnamese market crash)
- **Sideway Market**: 2024-01-02 → 2024-06-28 (Consolidation period)  
- **Bull Market**: 2025-01-02 → 2025-06-30 (Growth period)

Execute the following command:
```bash
cd "/Users/khangdang/Vibe code Project/IndicatorK" && PYTHONPATH=/Users/khangdang/Vibe\ code\ Project/IndicatorK python3 .claude/skills/backtest-periods.py
```

The script will:
1. Run backtests for all 3 periods with consistent parameters (20M VND initial, 4 trades/week max)
2. Generate comparative performance metrics (CAGR, Sharpe, Max DD, Win Rate)
3. Display results table showing which market conditions favor the active strategy
4. Save detailed results to `data/backtest_periods_results.json`

This enables quick strategy validation across different market cycles without manual date entry.