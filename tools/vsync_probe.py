#!/usr/bin/env python3
import sys

sys.path.insert(0, "tools")
from input_probe import send

port = int(sys.argv[1]) if len(sys.argv) > 1 else 4630
print(send(port, '{"cmd":"vsync_query_hle"}'))
