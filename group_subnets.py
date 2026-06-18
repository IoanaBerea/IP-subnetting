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
    # Backwards-compatible wrapper for metadata-free items
    items = [(ip, set()) for ip in ip_ints]
    grouped = group_ip_meta(items, min_mask=min_mask, max_mask=max_mask, coarse_first=coarse_first)
    # Convert members from (ip, ports) to plain ip lists
    results = []
    for prefix, L, members in grouped:
        ips = [m[0] for m in members]
        results.append((prefix, L, ips))
    return results


def group_ip_meta(items, min_mask=8, max_mask=24, coarse_first=False):
    """Group items where each item is (ip_int, ports_set).

    Returns list of (prefix_int, prefix_len, [ (ip_int, ports_set), ... ])
    """
    # Group by first octet (MSB)
    by_octet = defaultdict(list)
    for ip, ports in items:
        octet = ip >> 24
        by_octet[octet].append((ip, set(ports)))

    results = []
    for octet, ip_items in by_octet.items():
        remaining = {ip: ports for ip, ports in ip_items}

        low = max(min_mask, 8)
        high = min(max_mask, 32)
        if coarse_first:
            mask_range = range(low, high + 1)
        else:
            mask_range = range(high, low - 1, -1)

        for L in mask_range:
            mask = mask_for_len(L)
            groups = defaultdict(list)
            for ip in list(remaining.keys()):
                prefix = ip & mask
                groups[prefix].append(ip)

            for prefix, members in groups.items():
                if len(members) >= 2:
                    # collect member tuples
                    mems = []
                    for m in sorted(members):
                        mems.append((m, remaining[m]))
                    results.append((prefix, L, mems))
                    for m in members:
                        remaining.pop(m, None)

        # Remaining singletons -> /32
        for ip in sorted(remaining.keys()):
            results.append((ip, 32, [(ip, remaining[ip])]))

    results.sort(key=lambda x: (x[0], -x[1]))
    return results


def read_input(path, csv_mode=False):
    """Read IPs from input file.
    
    In csv_mode: return dict {dest_ip_int: [source_ip_ints]}
      - Reads CSV with headers, auto-detects delimiter (comma or semicolon)
      - Looks for: src_ip, source_address, source address, source_ip
      - Looks for: dest_ip, destination_address, destination address, destination_ip
      - Falls back to first two columns if headers not found
    Otherwise: return list of IP integers
    """
    if csv_mode:
        records = []
        with open(path, 'r', encoding='utf-8') as f:
            # Read first line to detect delimiter
            first_line = f.readline().strip()
            if not first_line:
                print("Warning: CSV file appears empty", file=sys.stderr)
                return records
            
            # Detect delimiter
            delimiter = ',' if ',' in first_line else ';'
            
            # Reset and parse with DictReader
            f.seek(0)
            reader = csv.DictReader(f, delimiter=delimiter)
            if reader.fieldnames is None or not reader.fieldnames:
                print("Warning: CSV file appears empty", file=sys.stderr)
                return records
            
            # Check for source/destination columns (case-insensitive)
            fieldnames_lower = {fn.lower().replace(' ', '_').replace('-', '_'): fn for fn in reader.fieldnames}
            
            # Look for source column with multiple name variations
            src_col = None
            for candidate in ['src_ip', 'source_ip', 'source_address', 'source_addr', 'sourceip', 'sourceaddress']:
                if candidate in fieldnames_lower:
                    src_col = fieldnames_lower[candidate]
                    break
            
            # Look for destination column with multiple name variations
            dst_col = None
            for candidate in ['dest_ip', 'destination_ip', 'destination_address', 'destination_addr', 'destip', 'destinationaddress']:
                if candidate in fieldnames_lower:
                    dst_col = fieldnames_lower[candidate]
                    break
            
            # Also look for port columns
            port_col = None
            for candidate in ['dest_port', 'destination_port', 'dport', 'destport', 'port']:
                if candidate in fieldnames_lower:
                    port_col = fieldnames_lower[candidate]
                    break

            if src_col and dst_col:
                # Use header-based extraction
                for row in reader:
                    try:
                        src_str = row.get(src_col, '').strip()
                        dst_str = row.get(dst_col, '').strip()
                        port_str = row.get(port_col, '').strip() if port_col else ''
                        if src_str and dst_str:
                            src_ip = ip_to_int(src_str)
                            dst_ip = ip_to_int(dst_str)
                            dst_port = port_str if port_str else None
                            records.append((src_ip, dst_ip, None, dst_port))
                    except Exception as e:
                        print(f"Skipping invalid row: {row} ({e})", file=sys.stderr)
            else:
                print(f"Columns found: {list(reader.fieldnames)}", file=sys.stderr)
                print(f"No source/destination IP columns found. Using first two columns.", file=sys.stderr)
                f.seek(0)
                for line_num, ln in enumerate(f, 1):
                    s = ln.strip()
                    if not s:
                        continue
                    parts = [p.strip() for p in s.split(delimiter)]
                    if len(parts) < 2:
                        print(f"Skipping line {line_num} (need 2 fields): {s}", file=sys.stderr)
                        continue
                    try:
                        src_ip = ip_to_int(parts[0])
                        dst_ip = ip_to_int(parts[1])
                        dst_port = parts[2] if len(parts) > 2 else None
                        records.append((src_ip, dst_ip, None, dst_port))
                    except Exception as e:
                        print(f"Skipping line {line_num}: {s} ({e})", file=sys.stderr)
        return records
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
    """Write CSV output: for each destination, list grouped source subnets and ports.

    Columns: Destination IP, Subnet, Source IPs, Ports
    """
    with open(path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Destination IP', 'Subnet', 'Source IPs', 'Ports'])

        for dst_ip in sorted(grouped_by_dest.keys()):
            dst_str = int_to_ip(dst_ip)
            for prefix, L, members in grouped_by_dest[dst_ip]:
                subnet = f"{int_to_ip(prefix)}/{L}"
                # members are list of (ip_int, ports_set)
                ips = [int_to_ip(m[0]) for m in members]
                ports_list = []
                for m in members:
                    ports = sorted([p for p in m[1]]) if m[1] else []
                    ports_list.append(','.join(ports) if ports else '')
                member_s = '; '.join(ips)
                ports_s = '; '.join(ports_list)
                writer.writerow([dst_str, subnet, member_s, ports_s])


def write_output_csv_by_source(path, grouped_by_src):
    """Write CSV output grouped by source IP: Source IP, Subnet, Destination IPs, Ports"""
    with open(path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Source IP', 'Subnet', 'Destination IPs', 'Ports'])
        for src_ip in sorted(grouped_by_src.keys()):
            src_str = int_to_ip(src_ip)
            for prefix, L, members in grouped_by_src[src_ip]:
                subnet = f"{int_to_ip(prefix)}/{L}"
                dsts = [int_to_ip(m[0]) for m in members]
                ports_list = []
                for m in members:
                    ports = sorted([p for p in m[1]]) if m[1] else []
                    ports_list.append(','.join(ports) if ports else '')
                dst_s = '; '.join(dsts)
                ports_s = '; '.join(ports_list)
                writer.writerow([src_str, subnet, dst_s, ports_s])


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
        # CSV mode: read records (src_ip, dst_ip, src_port, dst_port)
        records = read_input(args.input, csv_mode=True)
        if not records:
            print("No valid CSV entries found in input.", file=sys.stderr)
            return 1

        # Build destination -> src_ip -> set(dst_ports)
        dest_map = defaultdict(lambda: defaultdict(set))
        # Build source -> dest_ip -> set(dest_ports)
        src_map = defaultdict(lambda: defaultdict(set))
        for src_ip, dst_ip, _, dst_port in records:
            if dst_port:
                dest_map[dst_ip][src_ip].add(dst_port)
                src_map[src_ip][dst_ip].add(dst_port)
            else:
                dest_map[dst_ip][src_ip]
                src_map[src_ip][dst_ip]

        # For each destination, prepare items list (src_ip, ports_set) and group
        grouped_by_dest = {}
        for dst_ip, srcs in dest_map.items():
            items = [(sip, set(sorted(list(ports)))) for sip, ports in srcs.items()]
            groups = group_ip_meta(items, min_mask=args.min_mask, max_mask=args.max_mask, coarse_first=args.coarse_first)
            grouped_by_dest[dst_ip] = groups

        # For each source, prepare items list (dst_ip, ports_set) and group into subnets
        grouped_by_src = {}
        for src_ip, dsts in src_map.items():
            items = [(dip, set(sorted(list(ports)))) for dip, ports in dsts.items()]
            groups = group_ip_meta(items, min_mask=args.min_mask, max_mask=args.max_mask, coarse_first=args.coarse_first)
            grouped_by_src[src_ip] = groups

        # Write destination-grouped CSV (includes Source IPs and their ports)
        write_output_csv(args.output, grouped_by_dest)
        # Write source-grouped CSV next to output (append _by_source)
        out_by_src = args.output
        if out_by_src.endswith('.csv'):
            out_by_src = out_by_src[:-4] + '_by_source.csv'
        else:
            out_by_src = out_by_src + '_by_source.csv'
        write_output_csv_by_source(out_by_src, grouped_by_src)

        total_groups = sum(len(g) for g in grouped_by_dest.values())
        print(f"Wrote {total_groups} subnets grouped by {len(grouped_by_dest)} destinations to {args.output}")
        print(f"Wrote source-grouped CSV to {out_by_src}")
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
