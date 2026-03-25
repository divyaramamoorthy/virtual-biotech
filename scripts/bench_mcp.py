"""Benchmark MCP server tool latency.

Run with:  uv run python scripts/bench_mcp.py
"""

from virtual_biotech.mcp_servers.health_check import get_checks, run_check


def main() -> None:
    checks = get_checks()
    flat = [(f"{server}.{tool}", fn) for server, tools in checks.items() for tool, fn in tools]

    print(f"Running {len(flat)} benchmarks (serial, one at a time)...\n")

    results = [(label, *run_check(fn)) for label, fn in flat]
    results.sort(key=lambda r: r[1])

    print(f"{'Tool':<55} {'Time':>7}  Status")
    print("-" * 85)
    for label, elapsed, status in results:
        bar = "#" * int(min(elapsed, 30))
        print(f"{label:<55} {elapsed:>6.2f}s  {bar}  {status}")

    times = [r[1] for r in results]
    ok_count = sum(1 for r in results if r[2] == "OK")
    print(f"\n  Total tools: {len(results)}")
    print(f"  Succeeded:   {ok_count}")
    print(f"  Median:      {times[len(times) // 2]:.2f}s")
    print(f"  p95:         {sorted(times)[int(len(times) * 0.95)]:.2f}s")
    print(f"  Max:         {max(times):.2f}s")
    print(f"  Total time:  {sum(times):.2f}s")


if __name__ == "__main__":
    main()
