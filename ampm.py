#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
import threading
import time


class CPUTime:

    CLK_TCK = float(subprocess.run(
        ['getconf', 'CLK_TCK'], capture_output=True).stdout)

    def __init__(self, utime: int, stime: int, cutime: int, cstime: int,
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


class UsageHistory:

    def __init__(self):
        self._rss = []
        self._cpu = []
        self._index = -1
        self._read = -1
        self._cv = threading.Condition()
        self._term = False

    def append(self, cpu: float, rss: int):
        with self._cv:
            self._cpu.append(cpu)
            self._rss.append(rss)
            self._index = self._index + 1
            self._cv.notify()

    def get(self) -> (float, int, bool):
        with self._cv:
            while self._index == self._read and not self._term:
                self._cv.wait()
            if self._index != self._read:
                self._read = self._read + 1
                return self._cpu[self._index], self._rss[self._index], True
        return 0.0, 0, False

    def term(self):
        with self._cv:
            self._term = True
            self._cv.notify()

    def is_term(self):
        with self._cv:
            return self._term

    def empty(self) -> bool:
        with self._cv:
            return (len(self._cpu) == 0 or len(self._rss) == 0)

    def max(self) -> (float, int):
        with self._cv:
            return max(self._cpu), max(self._rss)

    def min(self) -> (float, int):
        with self._cv:
            return min(self._cpu), min(self._rss)

    def ave(self) -> (float, int):
        with self._cv:
            return sum(self._cpu)/len(self._cpu), \
                sum(self._rss)//len(self._rss)


def read_stat(pid: int) -> CPUTime:
    with open(os.path.join('/proc', str(pid), 'stat'), 'r') as f:
        s = f.read().split()
    # utime, stime, cutime, cstime, num_threads
    return CPUTime(int(s[13]), int(s[14]), int(s[15]), int(s[16]), int(s[19]))


def read_comm(pid: int) -> str:
    with open(os.path.join('/proc', str(pid), 'cmdline'), 'r') as f:
        cmdline = f.read().split('\0')
    return cmdline[0]


def read_smaps(pid: int) -> int:
    with open(os.path.join('/proc', str(pid), 'smaps_rollup'), 'r') as f:
        next(f)
        rss = f.readline().split()[1]
    return int(rss)


def print_summary(hist: UsageHistory):
    maxs = hist.max()
    mins = hist.min()
    aves = hist.ave()
    print('\n------ Summary ------')
    print('      CPU[%]  RSS[kB]')
    print(f'Max:   {maxs[0]:5.1f}  {maxs[1]:,}')
    print(f'Min:   {mins[0]:5.1f}  {mins[1]:,}')
    print(f'Ave:   {aves[0]:5.1f}  {aves[1]:,}')


def print_lines(comm: str, sep: str, hist: UsageHistory):
    # header
    print(f'Command{sep}CPU[%]{sep}RSS[kB]')
    while not hist.is_term():
        cpu, rss, ret = hist.get()
        if ret:
            print(f'{comm}{sep}{cpu:.1f}{sep}{rss}')


def run(pid: int, rate: float, duration: float, output_type: str):
    if output_type == 'csv':
        sep = ','
    else:
        sep = ' '
    if duration == 0:
        times = sys.maxsize
    else:
        times = int(duration * rate)

    interval = 1/rate
    t = time.perf_counter()
    b_cpu = read_stat(pid)
    comm = read_comm(pid)
    prev_cpu = b_cpu

    hist = UsageHistory()

    print_t = threading.Thread(target=print_lines, args=(comm, sep, hist))
    print_t.start()

    try:
        while times > 0:
            sleep_time = interval - (time.perf_counter() - t)
            if sleep_time > 0:
                time.sleep(sleep_time)

            t = time.perf_counter()
            diff_cpu = read_stat(pid)
            cpu_usage = prev_cpu.usage(interval, diff_cpu)
            prev_cpu = diff_cpu

            rss = read_smaps(pid)

            hist.append(cpu_usage, rss)
            times = times - 1
    except KeyboardInterrupt:
        pass
    finally:
        hist.term()
        print_t.join()
        if not hist.empty():
            print_summary(hist)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='A siMple Process Monitor.'
    )
    parser.add_argument('pid', help='process ID. e.g. $(pidof foo)', type=int)

    parser.add_argument('-r', '--rate',
                        help='calculation frequency. default:1 (< CLK_TCK/2)',
                        type=float, default='1', action='store')
    parser.add_argument('-d', '--duration',
                        help='monitoring duration [sec], 0 means inf.\
                        default:0 (>= 0)',
                        type=int, default=0, action='store')
    parser.add_argument('-t', '--type',
                        help='Output type. default:"" [|csv]',
                        default='', action='store')

    args = parser.parse_args()

    if args.rate > float(CPUTime.CLK_TCK)/2.0:
        print(f'Your rate exceeds the limit [{int(CPUTime.CLK_TCK)/2}]!',
              file=sys.stderr)
        sys.exit(1)

    run(args.pid, args.rate, float(args.duration), args.type)
