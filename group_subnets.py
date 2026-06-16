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
import csv
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


def read_input(path, csv_mode=False):
    """Read IPs from input file.
    
    In csv_mode: return dict {dest_ip_int: [source_ip_ints]}
      - Reads CSV with headers, extracts "Source address" and "Destination address" columns
      - Falls back to first two columns if headers not found
    Otherwise: return list of IP integers
    """
    if csv_mode:
        data = defaultdict(list)
        with open(path, 'r', encoding='utf-8') as f:
            # Try to read as CSV with headers (DictReader)
            reader = csv.DictReader(f)
            if reader.fieldnames is None or not reader.fieldnames:
                print("Warning: CSV file appears empty", file=sys.stderr)
                return data
            
            # Check for source/destination columns (case-insensitive)
            fieldnames_lower = {fn.lower(): fn for fn in reader.fieldnames}
            src_col = fieldnames_lower.get('source address') or fieldnames_lower.get('source ip') or None
            dst_col = fieldnames_lower.get('destination address') or fieldnames_lower.get('destination ip') or None
            
            if src_col and dst_col:
                # Use header-based extraction
                for row in reader:
                    try:
                        src_str = row.get(src_col, '').strip()
                        dst_str = row.get(dst_col, '').strip()
                        if src_str and dst_str:
                            src_ip = ip_to_int(src_str)
                            dst_ip = ip_to_int(dst_str)
                            data[dst_ip].append(src_ip)
                    except Exception as e:
                        print(f"Skipping invalid row: {row} ({e})", file=sys.stderr)
            else:
                # Fallback: assume first two columns are source, destination
                print(f"No 'Source address' or 'Destination address' columns found. Using first two columns.", file=sys.stderr)
                f.seek(0)
                for line_num, ln in enumerate(f, 1):
                    s = ln.strip()
                    if not s:
                        continue
                    parts = [p.strip() for p in s.split(',')]
                    if len(parts) < 2:
                        print(f"Skipping line {line_num} (need 2 fields): {s}", file=sys.stderr)
                        continue
                    try:
                        src_ip = ip_to_int(parts[0])
                        dst_ip = ip_to_int(parts[1])
                        data[dst_ip].append(src_ip)
                    except Exception as e:
                        print(f"Skipping line {line_num}: {s} ({e})", file=sys.stderr)
        return data
    else:
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


def write_output_csv(path, grouped_by_dest):
    """Write CSV output: for each destination, list grouped source subnets.
    
    Args:
        path: output file path
        grouped_by_dest: dict {dst_ip_int: [(prefix_int, prefix_len, [src_ips]), ...]}
    """
    with open(path, 'w', encoding='utf-8') as f:
        for dst_ip in sorted(grouped_by_dest.keys()):
            dst_str = int_to_ip(dst_ip)
            f.write(f"destination: {dst_str}\n")
            for prefix, L, members in grouped_by_dest[dst_ip]:
                subnet = f"{int_to_ip(prefix)}/{L}"
                member_s = ', '.join(int_to_ip(m) for m in members)
                f.write(f"  {subnet}: {member_s}\n")


def main():
    ap = argparse.ArgumentParser(description="Group IPs to smallest subnets")
    ap.add_argument('input', help='Input txt file with one IP per line, or CSV (source,dest) if --csv')
    ap.add_argument('output', help='Output txt file to write subnets')
    ap.add_argument('--csv', action='store_true', help='Input/output CSV format: source,destination per line')
    ap.add_argument('--coarse-first', action='store_true', help='Prefer larger subnets first (e.g., /23,/22)')
    ap.add_argument('--min-mask', type=int, default=8, help='Smallest mask length to consider (coarsest), e.g. 8')
    ap.add_argument('--max-mask', type=int, default=24, help='Largest mask length to consider (most specific), e.g. 24')
    args = ap.parse_args()

    if args.csv:
        # CSV mode: group source IPs by destination
        csv_data = read_input(args.input, csv_mode=True)
        if not csv_data:
            print("No valid CSV entries found in input.", file=sys.stderr)
            return 1

        # Group source IPs for each destination
        grouped_by_dest = {}
        for dst_ip, src_ips in csv_data.items():
            groups = group_ips(src_ips, min_mask=args.min_mask, max_mask=args.max_mask, coarse_first=args.coarse_first)
            grouped_by_dest[dst_ip] = groups

        write_output_csv(args.output, grouped_by_dest)
        total_groups = sum(len(g) for g in grouped_by_dest.values())
        print(f"Wrote {total_groups} subnets grouped by {len(grouped_by_dest)} destinations to {args.output}")
    else:
        # Original mode: group all IPs
        ips = read_input(args.input, csv_mode=False)
        if not ips:
            print("No valid IPs found in input.", file=sys.stderr)
            return 1

        groups = group_ips(ips, min_mask=args.min_mask, max_mask=args.max_mask, coarse_first=args.coarse_first)
        write_output(args.output, groups)
        print(f"Wrote {len(groups)} subnets to {args.output}")
    
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
