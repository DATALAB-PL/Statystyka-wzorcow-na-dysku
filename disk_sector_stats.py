#!/usr/bin/env python3
"""
Disk Sector Pattern Statistics Analyzer

Reads raw sectors from a physical disk (or image file) within a specified LBA range
and categorizes each sector by its content pattern. Designed for forensic analysis
of disks after data destruction / hacker attacks.

Requires Administrator privileges for physical disk access on Windows.

Usage:
    python disk_sector_stats.py <source> <start_lba> <end_lba> [options]

Examples:
    python disk_sector_stats.py \\.\PhysicalDrive1 0 1000000
    python disk_sector_stats.py \\.\PhysicalDrive1 0 1000000 --patterns 0xAA 0x55 0xDEAD
    python disk_sector_stats.py disk_image.dd 0 2048 --sector-size 4096
    python disk_sector_stats.py \\.\PhysicalDrive1 0 1000000 --output report.txt
"""

import argparse
import ctypes
import os
import struct
import sys
import time
from collections import defaultdict


SECTOR_SIZE_DEFAULT = 512


def is_admin():
    """Check if running with Administrator privileges (Windows)."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except AttributeError:
        # Not Windows — assume ok (Linux raw disk needs root, user handles it)
        return True


def open_disk(source, sector_size):
    """Open a physical disk or image file for raw reading."""
    if source.startswith("\\\\.\\") or source.startswith("//./"):
        # Physical disk on Windows — use raw open
        if not is_admin():
            print("ERROR: Physical disk access requires Administrator privileges.")
            print("       Right-click your terminal and select 'Run as administrator'.")
            sys.exit(1)
        # Open with standard Python open in binary mode — works for \\.\PhysicalDriveN
        try:
            f = open(source, "rb")
        except PermissionError:
            print(f"ERROR: Cannot open {source}. Run as Administrator.")
            sys.exit(1)
        except FileNotFoundError:
            print(f"ERROR: Device {source} not found. Check disk number with 'powershell Get-CimInstance Win32_DiskDrive'.")
            sys.exit(1)
        return f
    else:
        # Image file
        if not os.path.isfile(source):
            print(f"ERROR: File '{source}' not found.")
            sys.exit(1)
        return open(source, "rb")


def parse_pattern(pattern_str):
    """Parse a hex pattern string like '0x00', '0xFF', '0xDEAD' into bytes.

    Returns a tuple (byte_sequence, display_name).
    For single-byte patterns like 0x00, the sector is filled with that byte.
    For multi-byte patterns like 0xDEAD, the pattern repeats across the sector.
    """
    pattern_str = pattern_str.strip()
    if pattern_str.lower().startswith("0x"):
        hex_str = pattern_str[2:]
    else:
        hex_str = pattern_str

    if len(hex_str) % 2 != 0:
        hex_str = "0" + hex_str

    try:
        byte_seq = bytes.fromhex(hex_str)
    except ValueError:
        print(f"ERROR: Invalid hex pattern: {pattern_str}")
        sys.exit(1)

    return byte_seq, pattern_str.upper()


def build_pattern_sector(pattern_bytes, sector_size):
    """Build a full sector filled with the repeating pattern."""
    if len(pattern_bytes) == 0:
        return b"\x00" * sector_size
    repeats = (sector_size // len(pattern_bytes)) + 1
    return (pattern_bytes * repeats)[:sector_size]


def classify_sector(sector_data, pattern_sectors, pattern_names):
    """Classify a sector against known patterns.

    Returns the pattern name if matched, or 'DATA' if no pattern matches.
    """
    for pattern_sector, name in zip(pattern_sectors, pattern_names):
        if sector_data == pattern_sector:
            return name
    return "DATA"


def format_size(num_bytes):
    """Format byte count to human-readable size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"


def format_duration(seconds):
    """Format seconds to human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{int(m)}m {int(s)}s"
    else:
        h, remainder = divmod(seconds, 3600)
        m, s = divmod(remainder, 60)
        return f"{int(h)}h {int(m)}m {int(s)}s"


def print_progress(current, total, start_time, last_print_time, print_interval=0.5):
    """Print progress bar. Returns new last_print_time."""
    now = time.time()
    if now - last_print_time < print_interval and current < total:
        return last_print_time

    elapsed = now - start_time
    pct = current / total if total > 0 else 1
    bar_width = 40
    filled = int(bar_width * pct)
    bar = "#" * filled + "-" * (bar_width - filled)

    if pct > 0 and current > 0:
        eta = elapsed / pct - elapsed
        eta_str = format_duration(eta)
    else:
        eta_str = "???"

    speed = current / elapsed if elapsed > 0 else 0
    speed_str = format_size(current * SECTOR_SIZE_DEFAULT) + "/s"  # approximate

    sys.stdout.write(
        f"\r  [{bar}] {pct*100:6.2f}%  "
        f"Sector {current:,}/{total:,}  "
        f"ETA: {eta_str}  Speed: {speed_str}   "
    )
    sys.stdout.flush()
    return now


def analyze_disk(source, start_lba, end_lba, sector_size, patterns, chunk_sectors=2048):
    """Main analysis loop. Reads sectors in chunks for performance.

    Args:
        source: disk path or image file path
        start_lba: first LBA to read (inclusive)
        end_lba: last LBA to read (inclusive)
        sector_size: bytes per sector
        patterns: list of (byte_sequence, display_name) tuples
        chunk_sectors: number of sectors to read at once

    Returns:
        dict with statistics
    """
    global SECTOR_SIZE_DEFAULT
    SECTOR_SIZE_DEFAULT = sector_size

    # Build full-sector patterns for comparison
    pattern_sectors = [build_pattern_sector(p, sector_size) for p, _ in patterns]
    pattern_names = [name for _, name in patterns]

    total_sectors = end_lba - start_lba + 1
    counts = defaultdict(int)
    # Track contiguous regions for the report
    regions = []  # list of (start_lba, end_lba, type)
    current_region_type = None
    current_region_start = start_lba

    # Error tracking
    read_errors = 0
    error_sectors = []

    print(f"\n  Source:       {source}")
    print(f"  LBA range:   {start_lba:,} — {end_lba:,}")
    print(f"  Total:       {total_sectors:,} sectors ({format_size(total_sectors * sector_size)})")
    print(f"  Sector size: {sector_size} bytes")
    print(f"  Patterns:    {', '.join(pattern_names)}")
    print(f"  Chunk size:  {chunk_sectors} sectors ({format_size(chunk_sectors * sector_size)})")
    print()

    f = open_disk(source, sector_size)
    start_time = time.time()
    last_print = 0
    sectors_processed = 0

    try:
        # Seek to start LBA
        start_offset = start_lba * sector_size
        f.seek(start_offset)

        remaining = total_sectors
        current_lba = start_lba

        while remaining > 0:
            to_read = min(chunk_sectors, remaining)
            read_size = to_read * sector_size

            try:
                data = f.read(read_size)
            except OSError as e:
                # Bulk read failed — fall back to sector-by-sector
                print(f"\n  Warning: Bulk read failed at LBA {current_lba}: {e}")
                print(f"  Falling back to sector-by-sector reading...")
                data = b""
                for i in range(to_read):
                    try:
                        f.seek((current_lba + i) * sector_size)
                        sector = f.read(sector_size)
                        if len(sector) < sector_size:
                            sector += b"\x00" * (sector_size - len(sector))
                        data += sector
                    except OSError:
                        read_errors += 1
                        if len(error_sectors) < 100:
                            error_sectors.append(current_lba + i)
                        data += b"\x00" * sector_size

            if not data:
                print(f"\n  Warning: No data read at LBA {current_lba}. Possibly past end of disk.")
                break

            actual_sectors = len(data) // sector_size
            if len(data) % sector_size != 0:
                # Pad last incomplete sector
                data += b"\x00" * (sector_size - len(data) % sector_size)
                actual_sectors = len(data) // sector_size

            # Classify each sector in the chunk
            for i in range(actual_sectors):
                sector_data = data[i * sector_size : (i + 1) * sector_size]
                sector_type = classify_sector(sector_data, pattern_sectors, pattern_names)
                counts[sector_type] += 1

                # Track contiguous regions
                if sector_type != current_region_type:
                    if current_region_type is not None:
                        regions.append((current_region_start, current_lba + i - 1, current_region_type))
                    current_region_type = sector_type
                    current_region_start = current_lba + i

            current_lba += actual_sectors
            remaining -= actual_sectors
            sectors_processed += actual_sectors

            last_print = print_progress(sectors_processed, total_sectors, start_time, last_print)

    finally:
        f.close()

    # Close last region
    if current_region_type is not None:
        regions.append((current_region_start, end_lba, current_region_type))

    elapsed = time.time() - start_time
    print_progress(total_sectors, total_sectors, start_time, 0)
    print()

    return {
        "counts": dict(counts),
        "total_sectors": total_sectors,
        "sector_size": sector_size,
        "elapsed": elapsed,
        "regions": regions,
        "read_errors": read_errors,
        "error_sectors": error_sectors,
        "start_lba": start_lba,
        "end_lba": end_lba,
        "source": source,
        "pattern_names": pattern_names,
    }


def print_report(stats, show_regions=True, top_regions=30, output_file=None):
    """Print the analysis report to stdout and optionally to a file."""
    lines = []

    def out(line=""):
        lines.append(line)

    out("=" * 78)
    out("  DISK SECTOR PATTERN ANALYSIS REPORT")
    out("=" * 78)
    out()
    out(f"  Source:        {stats['source']}")
    out(f"  LBA range:    {stats['start_lba']:,} — {stats['end_lba']:,}")
    out(f"  Sector size:  {stats['sector_size']} bytes")
    out(f"  Total:        {stats['total_sectors']:,} sectors "
        f"({format_size(stats['total_sectors'] * stats['sector_size'])})")
    out(f"  Scan time:    {format_duration(stats['elapsed'])}")
    if stats["elapsed"] > 0:
        speed = stats["total_sectors"] * stats["sector_size"] / stats["elapsed"]
        out(f"  Avg speed:    {format_size(speed)}/s")
    out()

    if stats["read_errors"] > 0:
        out(f"  *** READ ERRORS: {stats['read_errors']} sectors could not be read ***")
        if stats["error_sectors"]:
            out(f"  First error LBAs: {', '.join(str(s) for s in stats['error_sectors'][:20])}")
        out()

    # --- Sector classification table ---
    out("-" * 78)
    out("  SECTOR CLASSIFICATION")
    out("-" * 78)
    out()
    out(f"  {'Pattern':<20} {'Count':>15} {'Size':>12} {'Percentage':>12}")
    out(f"  {'—'*20} {'—'*15} {'—'*12} {'—'*12}")

    total = stats["total_sectors"]
    # Sort: DATA first, then patterns sorted by count descending
    sorted_types = sorted(stats["counts"].items(), key=lambda x: (x[0] != "DATA", -x[1]))

    data_sectors = 0
    non_data_sectors = 0

    for pattern_type, count in sorted_types:
        pct = (count / total * 100) if total > 0 else 0
        size = format_size(count * stats["sector_size"])
        marker = " <-- USEFUL DATA" if pattern_type == "DATA" else ""
        out(f"  {pattern_type:<20} {count:>15,} {size:>12} {pct:>11.2f}%{marker}")
        if pattern_type == "DATA":
            data_sectors = count
        else:
            non_data_sectors += count

    out(f"  {'—'*20} {'—'*15} {'—'*12} {'—'*12}")
    out(f"  {'TOTAL':<20} {total:>15,} "
        f"{format_size(total * stats['sector_size']):>12} {'100.00%':>12}")
    out()

    # --- Summary ---
    out("-" * 78)
    out("  SUMMARY")
    out("-" * 78)
    out()
    data_pct = (data_sectors / total * 100) if total > 0 else 0
    empty_pct = (non_data_sectors / total * 100) if total > 0 else 0
    out(f"  Sectors with useful data:   {data_sectors:>15,} ({data_pct:.2f}%)")
    out(f"  Empty/pattern sectors:      {non_data_sectors:>15,} ({empty_pct:.2f}%)")
    out(f"  Ratio data:empty:           1 : {non_data_sectors/data_sectors:.1f}" if data_sectors > 0 else
        f"  Ratio data:empty:           N/A (no data sectors found)")
    out()

    # --- Top contiguous regions ---
    if show_regions and stats["regions"]:
        out("-" * 78)
        out(f"  TOP {top_regions} LARGEST CONTIGUOUS REGIONS")
        out("-" * 78)
        out()

        # Calculate region sizes and sort by size descending
        region_sizes = []
        for start, end, rtype in stats["regions"]:
            size = end - start + 1
            region_sizes.append((start, end, size, rtype))
        region_sizes.sort(key=lambda x: -x[2])

        out(f"  {'#':>4} {'Type':<15} {'Start LBA':>15} {'End LBA':>15} {'Sectors':>12} {'Size':>12}")
        out(f"  {'—'*4} {'—'*15} {'—'*15} {'—'*15} {'—'*12} {'—'*12}")

        for i, (start, end, size, rtype) in enumerate(region_sizes[:top_regions]):
            out(f"  {i+1:>4} {rtype:<15} {start:>15,} {end:>15,} "
                f"{size:>12,} {format_size(size * stats['sector_size']):>12}")

        out()

        # Data regions specifically
        data_regions = [(s, e, sz, t) for s, e, sz, t in region_sizes if t == "DATA"]
        if data_regions:
            out(f"  DATA REGIONS ({len(data_regions)} total):")
            out(f"  {'#':>4} {'Start LBA':>15} {'End LBA':>15} {'Sectors':>12} {'Size':>12}")
            out(f"  {'—'*4} {'—'*15} {'—'*15} {'—'*12} {'—'*12}")
            for i, (start, end, size, _) in enumerate(data_regions[:top_regions]):
                out(f"  {i+1:>4} {start:>15,} {end:>15,} {size:>12,} {format_size(size * stats['sector_size']):>12}")
            if len(data_regions) > top_regions:
                out(f"  ... and {len(data_regions) - top_regions} more data regions")
            out()

    out("=" * 78)

    report = "\n".join(lines)
    print(report)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(report + "\n")
        print(f"\n  Report saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Disk Sector Pattern Statistics Analyzer — forensic tool for analyzing "
                    "disk content distribution after data destruction or hacker attacks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s \\\\.\\PhysicalDrive1 0 1000000
  %(prog)s \\\\.\\PhysicalDrive1 0 1000000 --patterns 0xAA 0x55
  %(prog)s disk_image.dd 0 2048 --sector-size 4096
  %(prog)s \\\\.\\PhysicalDrive1 0 1000000 --output report.txt --no-regions

Note: Physical disk access requires Administrator privileges on Windows.
      Use 'powershell Get-CimInstance Win32_DiskDrive' to find your disk number.
        """,
    )

    parser.add_argument(
        "source",
        help="Physical disk (e.g. \\\\.\\PhysicalDrive1) or image file path",
    )
    parser.add_argument(
        "start_lba",
        type=int,
        help="First LBA to analyze (inclusive)",
    )
    parser.add_argument(
        "end_lba",
        type=int,
        help="Last LBA to analyze (inclusive)",
    )
    parser.add_argument(
        "--sector-size",
        type=int,
        default=SECTOR_SIZE_DEFAULT,
        help=f"Sector size in bytes (default: {SECTOR_SIZE_DEFAULT})",
    )
    parser.add_argument(
        "--patterns",
        nargs="+",
        default=["0x00", "0xFF"],
        help="Hex patterns to detect (default: 0x00 0xFF). "
             "Each sector is checked if it's entirely filled with the repeating pattern. "
             "Examples: 0x00 0xFF 0xAA 0x55 0xDEADBEEF",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=2048,
        help="Number of sectors to read at once (default: 2048, = 1MB for 512-byte sectors)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Save report to file",
    )
    parser.add_argument(
        "--no-regions",
        action="store_true",
        help="Skip contiguous region analysis (faster, less memory)",
    )
    parser.add_argument(
        "--top-regions",
        type=int,
        default=30,
        help="Number of top regions to show (default: 30)",
    )

    args = parser.parse_args()

    if args.start_lba < 0:
        parser.error("start_lba must be >= 0")
    if args.end_lba < args.start_lba:
        parser.error("end_lba must be >= start_lba")

    # Parse patterns
    patterns = [parse_pattern(p) for p in args.patterns]

    print()
    print("=" * 78)
    print("  DISK SECTOR PATTERN ANALYZER")
    print("=" * 78)

    stats = analyze_disk(
        source=args.source,
        start_lba=args.start_lba,
        end_lba=args.end_lba,
        sector_size=args.sector_size,
        patterns=patterns,
        chunk_sectors=args.chunk_size,
    )

    print()
    print_report(
        stats,
        show_regions=not args.no_regions,
        top_regions=args.top_regions,
        output_file=args.output,
    )


if __name__ == "__main__":
    main()
