# Design: SKSF Attribution Gate V6

AttributionStudy is immutable and binds target, workload, source artifact hash,
instrumentation class, bottleneck region, metric, runtime fraction, resolution, and
limitations. Grammar registration is fail-closed. Low-share or instrumented-only evidence
is exploratory unless policy explicitly permits its use.
