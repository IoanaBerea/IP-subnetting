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
    """Group items where each item is (ip_int, metadata).

    Returns list of (prefix_int, prefix_len, [ (ip_int, metadata), ... ])
    """
    # Group by first octet (MSB)
    by_octet = defaultdict(list)
    for ip, metadata in items:
        octet = ip >> 24
        copied_meta = metadata.copy() if hasattr(metadata, 'copy') else metadata
        by_octet[octet].append((ip, copied_meta))

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

            # Look for application/service columns
            app_col = None
            for candidate in ['application', 'app', 'service', 'protocol']:
                if candidate in fieldnames_lower:
                    app_col = fieldnames_lower[candidate]
                    break

            if src_col and dst_col:
                # Use header-based extraction
                for row in reader:
                    try:
                        src_str = row.get(src_col, '').strip()
                        dst_str = row.get(dst_col, '').strip()
                        port_str = row.get(port_col, '').strip() if port_col else ''
                        app_str = row.get(app_col, '').strip() if app_col else ''
                        if src_str and dst_str:
                            src_ip = ip_to_int(src_str)
                            dst_ip = ip_to_int(dst_str)
                            dst_port = port_str if port_str else None
                            application = app_str if app_str else None
                            records.append((src_ip, dst_ip, dst_port, application))
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
                        application = parts[3] if len(parts) > 3 else None
                        records.append((src_ip, dst_ip, dst_port, application))
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


def write_output_csv_by_source(path, grouped_by_src24, source_ips_by_src24):
    """Write CSV output grouped by source /24 subnet.

    Each row is a source /24, with all destination subnets for that /24 on one line.
    """
    with open(path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Source /24', 'Source IPs', 'Destination Subnets', 'Destination IPs', 'Ports', 'Applications'])
        for src24 in sorted(grouped_by_src24.keys()):
            src24_str = f"{int_to_ip(src24)}/24"
            source_ips = sorted(int_to_ip(ip) for ip in source_ips_by_src24[src24])
            source_ips_s = '; '.join(source_ips)

            subnet_entries = []
            dest_ips = []
            port_set = set()
            app_set = set()
            for prefix, L, members in grouped_by_src24[src24]:
                subnet = f"{int_to_ip(prefix)}/{L}"
                subnet_entries.append(subnet)
                for m in members:
                    dest_ips.append(int_to_ip(m[0]))
                    if isinstance(m[1], dict):
                        port_set.update(m[1].get('ports', set()))
                        app_set.update(m[1].get('apps', set()))

            subnet_s = '; '.join(subnet_entries)
            dest_ips_s = '; '.join(sorted(dest_ips, key=lambda ip: tuple(int(x) for x in ip.split('.'))))
            ports_s = '; '.join(sorted(port_set, key=lambda p: (int(p) if p.isdigit() else p)))
            apps_s = '; '.join(sorted(app_set))
            writer.writerow([src24_str, source_ips_s, subnet_s, dest_ips_s, ports_s, apps_s])


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

        # Build source /24 -> dest_ip -> metadata (ports + applications)
        src24_map = defaultdict(lambda: defaultdict(lambda: {'ports': set(), 'apps': set()}))
        source_ips_by_src24 = defaultdict(set)
        for src_ip, dst_ip, dst_port, application in records:
            src24 = src_ip & mask_for_len(24)
            source_ips_by_src24[src24].add(src_ip)
            if dst_port:
                src24_map[src24][dst_ip]['ports'].add(dst_port)
            if application:
                src24_map[src24][dst_ip]['apps'].add(application)

        # For each source /24, prepare dest items list and group into subnets
        grouped_by_src24 = {}
        for src24, dsts in src24_map.items():
            items = [(dip, {'ports': set(sorted(list(metadata['ports']))), 'apps': set(sorted(list(metadata['apps'])))}) for dip, metadata in dsts.items()]
            groups = group_ip_meta(items, min_mask=args.min_mask, max_mask=args.max_mask, coarse_first=args.coarse_first)
            grouped_by_src24[src24] = groups

        # Write source /24-grouped CSV only
        write_output_csv_by_source(args.output, grouped_by_src24, source_ips_by_src24)
        total_groups = sum(len(g) for g in grouped_by_src24.values())
        print(f"Wrote {total_groups} subnets grouped by {len(grouped_by_src24)} source /24 subnets to {args.output}")
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
