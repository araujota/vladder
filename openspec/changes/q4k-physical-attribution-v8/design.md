# Design: Q4_K Controlled Physical Attribution V8

The diagnostic harness includes weight-floor, metadata-only, unpack-only, pre-expanded
dot, serialized-consumption, forced-stack-traffic, and correction-only variants. Every
variant has a distortion declaration and is ineligible for ranking. Process order is
randomized, frequencies and temperatures are recorded, and unadjusted medians remain the
primary statistic. PMU data is supporting evidence because process startup and fixture
loading are inside the counter scope.

Variant runtimes are elimination envelopes. Except for the prior V7 activation ablation,
they do not identify schedule-preserving marginal shares and therefore have zero lower
bounds in the stage model.
