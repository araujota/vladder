#!/usr/bin/env python3
"""Deterministic workflow fixture; this is not hardware evidence."""

import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
print(json.dumps({
    "gpu_time_ns": payload["gpu_time_ns"],
    "output_hash": payload["output_hash"],
    "device_identity": payload["device_identity"],
    "evidence_class": "simulated-runner-fixture",
}))
