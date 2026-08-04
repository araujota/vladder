# Design: Q4_K Improvement Ceiling and Grammar Admission V8

Stage ceilings combine a zero-to-elimination envelope with an explicit reducibility
hypothesis. Their optimistic aggregate is a scenario bound, not demonstrated headroom;
the conservative aggregate remains zero where marginal reductions are unidentified.

V8 admits only work reuse across token or sequence rows. The row-four native path showed
5.86% throughput amortization relative to four row-one-equivalent runtimes, directly
targeting useful work per fetched weight byte. Decode synthesis requires a
schedule-preserving marginal experiment; software pipelining and accumulator scheduling
are deferred; layout and sibling activation reuse are rejected for the measured target.
