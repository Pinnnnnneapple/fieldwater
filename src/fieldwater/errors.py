"""Errors distinguishing malformed data from file and usage failures."""

from __future__ import annotations


class DataError(ValueError):
    """Weather or model inputs are insufficient or physically inconsistent."""


class InputError(ValueError):
    """An input file or command configuration cannot be read."""

