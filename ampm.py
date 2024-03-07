#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
import time


class CPUTime:

    CLK_TCK = float(subprocess.run(
        ['getconf', 'CLK_TCK'], capture_output=True).stdout)

    def __init__(self: int, utime: int, stime: int, cutime: int, cstime: int,
                 num_threads: int):
        self._utime = utime
        self._stime = stime
        self._cutime = cutime
        self._cstime = cstime
        self._cpu_max = num_threads * 100.0

    def usage(self, interval: float, diff_usage) -> float:
        diff = (diff_usage._utime - self._utime) + \
            (diff_usage._stime - self._stime) + \
            (diff_usage._cutime - self._cutime) + \
            (diff_usage._cstime - self._cstime)
        usage = (diff/(interval * CPUTime.CLK_TCK))*100.0
        if usage > (diff_usage._cpu_max):
            return diff_usage._cpu_max
        return usage


def read_stat(pid: int) -> CPUTime:
    with open(os.path.join('/proc', str(pid), 'stat'), 'r') as f:
        s = f.read().split()
    # comm, utime, stime, cutime, cstime, num_threads
    return CPUTime(int(s[13]), int(s[14]), int(s[15]), int(s[16]),
                   int(s[19]))


def read_comm(pid: int) -> str:
    with open(os.path.join('/proc', str(pid), 'cmdline'), 'r') as f:
        cmdline = f.read().split('\0')
    return cmdline[0]


def read_smaps(pid: int) -> int:
    with open(os.path.join('/proc', str(pid), 'smaps_rollup'), 'r') as f:
        next(f)
        rss = f.readline().split()[1]
    return int(rss)


def run(pid: int, interval: float, duration: float, output_type: str):
    if output_type == 'csv':
        sep = ','
    else:
        sep = ' '
    if duration == 0:
        duration = sys.float_info.max

    t = time.perf_counter()
    b_cpu = read_stat(pid)
    comm = read_comm(pid)
    prev_cpu = b_cpu

    try:
        # header
        print(f'Command{sep}CPUUsage[%]{sep}RSS[kB]', flush=True)
        while duration > 0:
            time.sleep(interval - (time.perf_counter() - t))

            t = time.perf_counter()
            diff_cpu = read_stat(pid)
            cpu_usage = prev_cpu.usage(interval, diff_cpu)
            prev_cpu = diff_cpu

            rss = read_smaps(pid)

            print(f'{comm}{sep}{cpu_usage}{sep}{rss}', flush=True)
            duration = duration - interval
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description="A siMple Process Monitor."
    )
    parser.add_argument("pid", help="process ID. e.g. $(pidof foo)", type=int)

    parser.add_argument("-r", "--rate",
                        help="calculation frequency. default:1 (>= 0.01)",
                        type=float, default="1", action="store")
    parser.add_argument("-d", "--duration",
                        help="monitoring duration [sec], 0 means inf.\
                        default:0 (>= 0)",
                        type=int, default=0, action="store")
    parser.add_argument("-t", "--type",
                        help="Output type. default:"" [|csv]",
                        default="", action="store")

    args = parser.parse_args()

    run(args.pid, 1/args.rate, float(args.duration), args.type)
