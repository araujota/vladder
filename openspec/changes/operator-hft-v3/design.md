# Design: Low-Latency Operators V3

The event schema uses fixed-width big-endian fields and a deterministic binary
trace header/version. A single owner updates one fixed-capacity book. Risk
updates are transactional: rejected orders cannot mutate reservations. The SPSC
ring is the only concurrent component and uses fixed-size entries.

Trace generation controls type mix, price locality, depth, branch entropy, and
bursts. Held-out and adversarial traces have independent hashes. Batch 1 is the
latency profile; microbursts are reported as throughput and never merged.
