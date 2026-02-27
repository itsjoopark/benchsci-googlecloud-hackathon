#!/usr/bin/env python3
from __future__ import annotations

import json

from backend.services.overview import verify_vector_overview


if __name__ == "__main__":
    print(json.dumps(verify_vector_overview(), indent=2))
