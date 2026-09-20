"""Latency benchmark for the search API.

Measures the HTTP path a real client takes, not ``run_search`` in-process, so
serialisation and the event loop are inside the number. The per-stage figures
come from the API's own ``timings`` block, so client wall time and server stage
time can be compared directly (the gap is transport + serialisation).
"""

from ops.bench.runner import BenchConfig, Sample, Summary, run_bench, summarise

__all__ = ["BenchConfig", "Sample", "Summary", "run_bench", "summarise"]
