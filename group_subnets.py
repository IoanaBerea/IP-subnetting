#!/usr/bin/env python3
"""Group IPv4 addresses into subnets with as-large-as-possible masks.

Usage:
  python group_subnets.py input.txt output.txt

The script groups IPs by their first octet (MSB) and then finds the
most-specific prefixes (largest mask length) that cover at least two
input IPs. Remaining single IPs are emitted as /32.
"""
import argparse
from collections import defaultdict
import ipaddress
import sys


def ip_to_int(ip_str: str) -> int:
    return int(ipaddress.IPv4Address(ip_str))


def int_to_ip(i: int) -> str:
    return str(ipaddress.IPv4Address(i))


def mask_for_len(L: int) -> int:
    if L == 0:
        return 0
    return (0xFFFFFFFF << (32 - L)) & 0xFFFFFFFF


def group_ips(ip_ints, min_mask=8, max_mask=24, coarse_first=False):
    # Group by first octet (MSB) to avoid crossing MSB boundaries
    by_octet = defaultdict(list)
    for ip in ip_ints:
        octet = ip >> 24
        by_octet[octet].append(ip)

    results = []  # tuples (prefix_int, prefix_len, [ip_ints])

    for octet, ips in by_octet.items():
        remaining = set(ips)

        # Determine mask iteration order based on coarse_first
        low = max(min_mask, 8)
        high = min(max_mask, 32)
        if coarse_first:
            mask_range = range(low, high + 1)  # e.g., 8..24
        else:
            mask_range = range(high, low - 1, -1)  # e.g., 24..8

        for L in mask_range:
            mask = mask_for_len(L)
            groups = defaultdict(list)
            for ip in list(remaining):
                prefix = ip & mask
                groups[prefix].append(ip)

            # Collect groups that have at least 2 addresses
            for prefix, members in groups.items():
                if len(members) >= 2:
                    results.append((prefix, L, sorted(members)))
                    for m in members:
                        remaining.discard(m)

        # Remaining singletons -> /32
        for ip in sorted(remaining):
            results.append((ip, 32, [ip]))

    # Sort results by numeric prefix then mask length (more specific first)
    results.sort(key=lambda x: (x[0], -x[1]))
    return results


def read_input(path):
    ips = []
    with open(path, 'r', encoding='utf-8') as f:
        for ln in f:
            s = ln.strip()
            if not s:
                continue
            try:
                _ = ipaddress.IPv4Address(s)
                ips.append(ip_to_int(s))
            except Exception:
                print(f"Skipping invalid IP: {s}", file=sys.stderr)
    return ips


def write_output(path, groups):
    with open(path, 'w', encoding='utf-8') as f:
        for prefix, L, members in groups:
            subnet = f"{int_to_ip(prefix)}/{L}"
            member_s = ', '.join(int_to_ip(m) for m in members)
            f.write(f"{subnet}: {member_s}\n")


def main():
    ap = argparse.ArgumentParser(description="Group IPs to smallest subnets")
    ap.add_argument('input', help='Input txt file with one IP per line')
    ap.add_argument('output', help='Output txt file to write subnets')
    ap.add_argument('--coarse-first', action='store_true', help='Prefer larger subnets first (e.g., /23,/22)')
    ap.add_argument('--min-mask', type=int, default=8, help='Smallest mask length to consider (coarsest), e.g. 8')
    ap.add_argument('--max-mask', type=int, default=24, help='Largest mask length to consider (most specific), e.g. 24')
    args = ap.parse_args()

    ips = read_input(args.input)
    if not ips:
        print("No valid IPs found in input.", file=sys.stderr)
        return 1

    groups = group_ips(ips, min_mask=args.min_mask, max_mask=args.max_mask, coarse_first=args.coarse_first)
    write_output(args.output, groups)
    print(f"Wrote {len(groups)} subnets to {args.output}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
