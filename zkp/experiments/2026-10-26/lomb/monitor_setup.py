"""Sample one setup process without reading its command-line arguments."""

import argparse
import csv
import subprocess
import time
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("pid", type=int)
p.add_argument("output", type=Path)
a = p.parse_args()
with a.output.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["time_epoch_seconds", "pid", "rss_kib", "cpu_percent"])
    while True:
        result = subprocess.run(["ps", "-p", str(a.pid), "-o", "pid=,rss=,pcpu="], capture_output=True, text=True)
        if result.returncode or not result.stdout.strip():
            break
        pid, rss, cpu = result.stdout.split()
        w.writerow([time.time(), pid, rss, cpu])
        f.flush()
        time.sleep(5)
