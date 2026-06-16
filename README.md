Grouping IP addresses into subnets

Usage

Run the CLI with an input file (one IPv4 per line) and an output file:

```bash
python3 group_subnets.py sample_ips.txt output_subnets.txt
```

Options

- `--coarse-first`: prefer larger subnets first (e.g., /23, /22) when grouping.
- `--min-mask N`: the smallest mask length to consider (coarsest). For example
  `--min-mask 22` will allow grouping up to `/22` but not `/21` or larger.
- `--max-mask N`: the largest mask length to consider (most specific). Default 24 (so by default grouping is between `/8` and `/24`).

Default behavior

By default the tool groups between `/8` and `/24` (inclusive) and gives
priority to the most restrictive masks (tries `/24` first, then `/23`,
etc.). Use `--coarse-first` to invert that order.

Example: prefer grouping across /24 boundaries up to /22:

```bash
python3 group_subnets.py --coarse-first --min-mask 22 sample_ips.txt output_coarse.txt
```

Output format

Each line in the output contains a subnet in CIDR form followed by the
input IPs that were grouped into that subnet, e.g.:

192.168.0.0/30: 192.168.0.1, 192.168.0.2

Notes

- The script groups IPs by their first octet (MSB) and then chooses the
  most-specific prefixes (largest CIDR length) that cover at least two
  input IPs. Remaining single IPs are emitted as /32.
