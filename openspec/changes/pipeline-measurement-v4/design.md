# Design: Information Movement Measurement V4

The static model maps edge lifetimes and reuse distance into target cache capacities
and emits register/L1/L2/LLC/DRAM byte estimates plus uncertainty. Physical runs use
randomized independent processes, held-out prompts, fixed affinity, and perf counters.
Attribution reports both inclusive and exclusive region time and the maximum possible
end-to-end gain implied by Amdahl's law.
