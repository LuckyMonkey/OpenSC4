#!/usr/bin/env python3
"""AI-derived TAX_001 hypothesis: fit the monthly constant from data alone.

Hypothesis family: T = trunc(k * S), S = sum_c B[c] * M * R[c].
Each derivation month bounds k:  T / S <= k < (T + 1) / S.
The fit intersects those intervals and predicts with the interval midpoint.
It does not read the specification's constant; agreement with 1/1200 is a
result, not an input. Pure Python, independent of the OpenGlassBox helper.
"""

from __future__ import annotations

import math
import struct
from fractions import Fraction
from typing import Any, Iterable


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def weighted_sum(inputs: dict[str, Any]) -> Fraction:
    mult = Fraction(f32(inputs["mult"]))
    return sum((Fraction(int(b)) * mult * Fraction(f32(r)) for b, r in zip(inputs["bases"], inputs["rates"])), Fraction(0))


class TaxFit:
    def __init__(self, records: Iterable[dict[str, Any]]):
        low, high = Fraction(0), None
        used = 0
        for record in records:
            s = weighted_sum(record["inputs"])
            t = record["metrics"]["tax_income"]["value"]
            if s <= 0:
                continue
            low = max(low, Fraction(t) / s)
            upper = Fraction(t + 1) / s
            high = upper if high is None else min(high, upper)
            used += 1
        if used == 0 or high is None or low >= high:
            raise ValueError("no consistent constant: hypothesis family rejected by the derivation data")
        self.low, self.high, self.months = low, high, used
        self.k = (low + high) / 2

    def predict(self, inputs: dict[str, Any]) -> int:
        return math.floor(self.k * weighted_sum(inputs))

    def describe(self) -> dict[str, Any]:
        return {
            "model": "trunc(k * sum(B*M*R)) with k fitted by interval intersection",
            "derivation_months": self.months,
            "k_interval": [float(self.low), float(self.high)],
            "one_over_k_interval": [float(1 / self.high), float(1 / self.low)],
            "k_used": float(self.k),
        }
