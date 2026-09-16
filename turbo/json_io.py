"""Strict UTF-8 JSON file loading, accepting the optional Windows UTF-8 BOM."""
import json
import math
from pathlib import Path


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON object key')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('Non-finite JSON number is not supported')


def _float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('JSON number is outside the finite float range')
    return number


def read_json(path, *, require_object=False):
    """Read without rewriting bytes; reject invalid encoding, duplicates and NaN."""
    data = Path(path).read_bytes().decode('utf-8-sig', errors='strict')
    value = json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)
    if require_object and not isinstance(value, dict):
        raise ValueError('JSON root must be an object')
    return value
