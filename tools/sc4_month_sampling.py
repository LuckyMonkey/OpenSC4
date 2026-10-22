"""Shared conservative month selection for live capture and offline replay."""
from __future__ import annotations


def month_index(row: dict) -> int:
    return int(row["simulation_year"]) * 12 + int(row["simulation_month"]) - 1


def consecutive(previous: dict, current: dict) -> bool:
    return (month_index(current) == month_index(previous) + 1
            and current["simulation_date_serial"] > previous["simulation_date_serial"])


class SettledMonths:
    """Skip the initial month, gaps and rewinds; emit once after a settling delay.

    Delay starts at the first observed sample in the new month, conservatively
    allowing for missed days. Freezing a sample makes reads coherent but cannot
    prove the game's update has completed; the delay remains necessary.
    """

    def __init__(self, settle_days: int = 3):
        if settle_days < 1:
            raise ValueError("settle_days must be at least 1")
        self.settle_days = settle_days
        self.previous = None
        self.first_serial = None
        self.taken = True
        self.segment = 0

    def push(self, row: dict) -> dict | None:
        if "error" in row:
            return None
        serial = row["simulation_date_serial"]
        if self.previous is None:
            self.first_serial = serial
        elif serial < self.previous["simulation_date_serial"]:
            self.segment += 1
            self.first_serial, self.taken = serial, True
        elif month_index(row) != month_index(self.previous):
            continuous = consecutive(self.previous, row)
            if not continuous:
                self.segment += 1
            self.first_serial, self.taken = serial, not continuous
        self.previous = row
        if not self.taken and serial - self.first_serial >= self.settle_days:
            self.taken = True
            return dict(row, sampling_segment=self.segment)
        return None
