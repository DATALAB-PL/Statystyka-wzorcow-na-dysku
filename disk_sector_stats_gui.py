#!/usr/bin/env python3
"""
Disk Sector Pattern Statistics Analyzer — GUI Version

Tkinter-based graphical interface for analyzing raw disk sectors
within a specified LBA range and generating pattern statistics.

Requires Administrator privileges for physical disk access on Windows.
"""

import ctypes
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from collections import defaultdict


SECTOR_SIZE_DEFAULT = 512


# ─── Backend (analysis logic) ────────────────────────────────────────────────


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except AttributeError:
        return True


def get_physical_disks():
    """Detect physical disks and their sizes using WMI (Windows).

    Returns list of dicts: [{
        "path": "\\\\.\\PhysicalDrive0",
        "model": "Samsung SSD 970 EVO 1TB",
        "size_bytes": 1000204886016,
        "sectors": 1953525168,
        "sector_size": 512,
        "display": "PhysicalDrive0 — Samsung SSD 970 EVO 1TB (931.51 GB)",
    }, ...]
    """
    disks = []
    try:
        result = subprocess.run(
            ["wmic", "diskdrive", "get",
             "DeviceID,Model,Size,BytesPerSector,MediaType,Status",
             "/format:csv"],
            capture_output=True, text=True, timeout=15,
        )
        lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
        if len(lines) < 2:
            return disks

        header = [h.strip() for h in lines[0].split(",")]
        for line in lines[1:]:
            cols = [c.strip() for c in line.split(",")]
            if len(cols) != len(header):
                continue
            row = dict(zip(header, cols))

            device_id = row.get("DeviceID", "")
            model = row.get("Model", "Unknown")
            size_str = row.get("Size", "0")
            bps_str = row.get("BytesPerSector", "512")
            media_type = row.get("MediaType", "")
            status = row.get("Status", "")

            if not device_id:
                continue

            try:
                size_bytes = int(size_str) if size_str else 0
            except ValueError:
                size_bytes = 0

            try:
                sector_size = int(bps_str) if bps_str else 512
            except ValueError:
                sector_size = 512

            if sector_size <= 0:
                sector_size = 512

            total_sectors = size_bytes // sector_size if size_bytes > 0 else 0

            # Build display string
            size_display = format_size(size_bytes) if size_bytes > 0 else "? size"
            drive_name = device_id.replace("\\\\.\\", "")
            extra = []
            if media_type:
                extra.append(media_type)
            if status and status.lower() != "ok":
                extra.append(f"Status: {status}")
            extra_str = f"  [{', '.join(extra)}]" if extra else ""

            display = f"{drive_name} \u2014 {model} ({size_display}){extra_str}"

            disks.append({
                "path": device_id,
                "model": model,
                "size_bytes": size_bytes,
                "sectors": total_sectors,
                "sector_size": sector_size,
                "display": display,
            })

    except Exception:
        pass

    # Sort by drive number
    disks.sort(key=lambda d: d["path"])
    return disks


def open_disk(source):
    if source.startswith("\\\\.\\") or source.startswith("//./"):
        if not is_admin():
            raise PermissionError(
                "Dostęp do dysku fizycznego wymaga uprawnień Administratora.\n"
                "Uruchom program jako Administrator."
            )
        return open(source, "rb")
    else:
        if not os.path.isfile(source):
            raise FileNotFoundError(f"Plik '{source}' nie istnieje.")
        return open(source, "rb")


def parse_pattern(pattern_str):
    pattern_str = pattern_str.strip()
    if pattern_str.lower().startswith("0x"):
        hex_str = pattern_str[2:]
    else:
        hex_str = pattern_str
    if len(hex_str) % 2 != 0:
        hex_str = "0" + hex_str
    byte_seq = bytes.fromhex(hex_str)
    return byte_seq, pattern_str.upper()


def build_pattern_sector(pattern_bytes, sector_size):
    if len(pattern_bytes) == 0:
        return b"\x00" * sector_size
    repeats = (sector_size // len(pattern_bytes)) + 1
    return (pattern_bytes * repeats)[:sector_size]


def format_size(num_bytes):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"


def format_duration(seconds):
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{int(m)}m {int(s)}s"
    else:
        h, remainder = divmod(seconds, 3600)
        m, s = divmod(remainder, 60)
        return f"{int(h)}h {int(m)}m {int(s)}s"


def analyze_disk_threaded(source, start_lba, end_lba, sector_size, patterns,
                          chunk_sectors, msg_queue, stop_event):
    """Run analysis in a background thread, posting updates to msg_queue."""
    try:
        pattern_sectors = [build_pattern_sector(p, sector_size) for p, _ in patterns]
        pattern_names = [name for _, name in patterns]

        total_sectors = end_lba - start_lba + 1
        counts = defaultdict(int)
        regions = []
        current_region_type = None
        current_region_start = start_lba
        read_errors = 0
        error_sectors = []

        f = open_disk(source)
        start_time = time.time()
        sectors_processed = 0
        last_update = 0

        try:
            f.seek(start_lba * sector_size)
            remaining = total_sectors
            current_lba = start_lba

            while remaining > 0:
                if stop_event.is_set():
                    msg_queue.put(("stopped", None))
                    return

                to_read = min(chunk_sectors, remaining)

                try:
                    data = f.read(to_read * sector_size)
                except OSError:
                    data = b""
                    for i in range(to_read):
                        if stop_event.is_set():
                            msg_queue.put(("stopped", None))
                            return
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
                    break

                actual_sectors = len(data) // sector_size
                if len(data) % sector_size != 0:
                    data += b"\x00" * (sector_size - len(data) % sector_size)
                    actual_sectors = len(data) // sector_size

                for i in range(actual_sectors):
                    sector_data = data[i * sector_size : (i + 1) * sector_size]
                    matched = False
                    for pattern_sector, name in zip(pattern_sectors, pattern_names):
                        if sector_data == pattern_sector:
                            counts[name] += 1
                            sector_type = name
                            matched = True
                            break
                    if not matched:
                        counts["DATA"] += 1
                        sector_type = "DATA"

                    if sector_type != current_region_type:
                        if current_region_type is not None:
                            regions.append((current_region_start, current_lba + i - 1, current_region_type))
                        current_region_type = sector_type
                        current_region_start = current_lba + i

                current_lba += actual_sectors
                remaining -= actual_sectors
                sectors_processed += actual_sectors

                now = time.time()
                if now - last_update >= 0.25:
                    elapsed = now - start_time
                    pct = sectors_processed / total_sectors
                    speed = sectors_processed * sector_size / elapsed if elapsed > 0 else 0
                    eta = (elapsed / pct - elapsed) if pct > 0 else 0
                    msg_queue.put(("progress", {
                        "pct": pct,
                        "sectors": sectors_processed,
                        "total": total_sectors,
                        "speed": speed,
                        "eta": eta,
                        "counts": dict(counts),
                        "errors": read_errors,
                    }))
                    last_update = now

        finally:
            f.close()

        if current_region_type is not None:
            regions.append((current_region_start, end_lba, current_region_type))

        elapsed = time.time() - start_time

        stats = {
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
        msg_queue.put(("done", stats))

    except Exception as e:
        msg_queue.put(("error", str(e)))


def generate_report(stats, top_regions=30):
    """Generate the text report from stats dict."""
    lines = []
    out = lines.append

    out("=" * 78)
    out("  DISK SECTOR PATTERN ANALYSIS REPORT")
    out("=" * 78)
    out("")
    out(f"  Source:        {stats['source']}")
    out(f"  LBA range:    {stats['start_lba']:,} \u2014 {stats['end_lba']:,}")
    out(f"  Sector size:  {stats['sector_size']} bytes")
    out(f"  Total:        {stats['total_sectors']:,} sectors "
        f"({format_size(stats['total_sectors'] * stats['sector_size'])})")
    out(f"  Scan time:    {format_duration(stats['elapsed'])}")
    if stats["elapsed"] > 0:
        speed = stats["total_sectors"] * stats["sector_size"] / stats["elapsed"]
        out(f"  Avg speed:    {format_size(speed)}/s")
    out("")

    if stats["read_errors"] > 0:
        out(f"  *** READ ERRORS: {stats['read_errors']} sectors could not be read ***")
        if stats["error_sectors"]:
            out(f"  First error LBAs: {', '.join(str(s) for s in stats['error_sectors'][:20])}")
        out("")

    out("-" * 78)
    out("  SECTOR CLASSIFICATION")
    out("-" * 78)
    out("")
    out(f"  {'Pattern':<20} {'Count':>15} {'Size':>12} {'Percentage':>12}")
    out(f"  {'\u2014'*20} {'\u2014'*15} {'\u2014'*12} {'\u2014'*12}")

    total = stats["total_sectors"]
    sorted_types = sorted(stats["counts"].items(), key=lambda x: (x[0] != "DATA", -x[1]))
    data_sectors = 0
    non_data_sectors = 0

    for ptype, count in sorted_types:
        pct = (count / total * 100) if total > 0 else 0
        size = format_size(count * stats["sector_size"])
        marker = " <-- USEFUL DATA" if ptype == "DATA" else ""
        out(f"  {ptype:<20} {count:>15,} {size:>12} {pct:>11.2f}%{marker}")
        if ptype == "DATA":
            data_sectors = count
        else:
            non_data_sectors += count

    out(f"  {'\u2014'*20} {'\u2014'*15} {'\u2014'*12} {'\u2014'*12}")
    out(f"  {'TOTAL':<20} {total:>15,} "
        f"{format_size(total * stats['sector_size']):>12} {'100.00%':>12}")
    out("")

    out("-" * 78)
    out("  SUMMARY")
    out("-" * 78)
    out("")
    data_pct = (data_sectors / total * 100) if total > 0 else 0
    empty_pct = (non_data_sectors / total * 100) if total > 0 else 0
    out(f"  Sectors with useful data:   {data_sectors:>15,} ({data_pct:.2f}%)")
    out(f"  Empty/pattern sectors:      {non_data_sectors:>15,} ({empty_pct:.2f}%)")
    if data_sectors > 0:
        out(f"  Ratio data:empty:           1 : {non_data_sectors/data_sectors:.1f}")
    else:
        out(f"  Ratio data:empty:           N/A (no data sectors found)")
    out("")

    if stats["regions"]:
        out("-" * 78)
        out(f"  TOP {top_regions} LARGEST CONTIGUOUS REGIONS")
        out("-" * 78)
        out("")

        region_sizes = []
        for start, end, rtype in stats["regions"]:
            size = end - start + 1
            region_sizes.append((start, end, size, rtype))
        region_sizes.sort(key=lambda x: -x[2])

        out(f"  {'#':>4} {'Type':<15} {'Start LBA':>15} {'End LBA':>15} {'Sectors':>12} {'Size':>12}")
        out(f"  {'\u2014'*4} {'\u2014'*15} {'\u2014'*15} {'\u2014'*15} {'\u2014'*12} {'\u2014'*12}")

        for i, (start, end, size, rtype) in enumerate(region_sizes[:top_regions]):
            out(f"  {i+1:>4} {rtype:<15} {start:>15,} {end:>15,} "
                f"{size:>12,} {format_size(size * stats['sector_size']):>12}")
        out("")

        data_regions = [(s, e, sz, t) for s, e, sz, t in region_sizes if t == "DATA"]
        if data_regions:
            out(f"  DATA REGIONS ({len(data_regions)} total):")
            out(f"  {'#':>4} {'Start LBA':>15} {'End LBA':>15} {'Sectors':>12} {'Size':>12}")
            out(f"  {'\u2014'*4} {'\u2014'*15} {'\u2014'*15} {'\u2014'*12} {'\u2014'*12}")
            for i, (start, end, size, _) in enumerate(data_regions[:top_regions]):
                out(f"  {i+1:>4} {start:>15,} {end:>15,} {size:>12,} "
                    f"{format_size(size * stats['sector_size']):>12}")
            if len(data_regions) > top_regions:
                out(f"  ... and {len(data_regions) - top_regions} more data regions")
            out("")

    out("=" * 78)
    return "\n".join(lines)


# ─── GUI ──────────────────────────────────────────────────────────────────────


class DiskAnalyzerGUI:
    """Main application window."""

    # Colors
    BG = "#1e1e2e"
    BG_LIGHT = "#2a2a3e"
    BG_INPUT = "#313148"
    FG = "#cdd6f4"
    FG_DIM = "#6c7086"
    ACCENT = "#89b4fa"
    GREEN = "#a6e3a1"
    RED = "#f38ba8"
    YELLOW = "#f9e2af"
    PEACH = "#fab387"

    def __init__(self, root):
        self.root = root
        self.root.title("Disk Sector Pattern Analyzer")
        self.root.geometry("960x780")
        self.root.minsize(800, 600)
        self.root.configure(bg=self.BG)

        self.msg_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.analysis_thread = None
        self.last_stats = None
        self.detected_disks = []  # list of disk info dicts

        self._apply_style()
        self._build_ui()
        self._detect_disks()
        self._poll_queue()

    def _apply_style(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".", background=self.BG, foreground=self.FG, fieldbackground=self.BG_INPUT)
        style.configure("TFrame", background=self.BG)
        style.configure("TLabel", background=self.BG, foreground=self.FG, font=("Segoe UI", 10))
        style.configure("Header.TLabel", background=self.BG, foreground=self.ACCENT,
                         font=("Segoe UI", 13, "bold"))
        style.configure("Status.TLabel", background=self.BG, foreground=self.FG_DIM,
                         font=("Segoe UI", 9))
        style.configure("TEntry", fieldbackground=self.BG_INPUT, foreground=self.FG,
                         insertcolor=self.FG, borderwidth=1, relief="solid")
        style.configure("TButton", background=self.ACCENT, foreground=self.BG,
                         font=("Segoe UI", 10, "bold"), borderwidth=0, padding=(16, 6))
        style.map("TButton",
                   background=[("active", "#b4d0fb"), ("disabled", self.BG_LIGHT)],
                   foreground=[("disabled", self.FG_DIM)])
        style.configure("Stop.TButton", background=self.RED, foreground=self.BG)
        style.map("Stop.TButton", background=[("active", "#f5a0b8"), ("disabled", self.BG_LIGHT)])
        style.configure("Save.TButton", background=self.GREEN, foreground=self.BG)
        style.map("Save.TButton", background=[("active", "#bee8b7"), ("disabled", self.BG_LIGHT)])

        style.configure("Horizontal.TProgressbar",
                         troughcolor=self.BG_LIGHT, background=self.ACCENT,
                         borderwidth=0, thickness=22)

        style.configure("TCombobox", fieldbackground=self.BG_INPUT, foreground=self.FG,
                         selectbackground=self.ACCENT, selectforeground=self.BG,
                         borderwidth=1)
        style.map("TCombobox",
                   fieldbackground=[("readonly", self.BG_INPUT)],
                   foreground=[("readonly", self.FG)])

        style.configure("TLabelframe", background=self.BG, foreground=self.ACCENT,
                         borderwidth=1, relief="solid")
        style.configure("TLabelframe.Label", background=self.BG, foreground=self.ACCENT,
                         font=("Segoe UI", 10, "bold"))

    def _build_ui(self):
        # ── Main container ──
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        # ── Title ──
        ttk.Label(main, text="Disk Sector Pattern Analyzer", style="Header.TLabel").pack(
            anchor=tk.W, pady=(0, 8))

        # ── Parameters frame ──
        params = ttk.LabelFrame(main, text="  Parameters  ", padding=10)
        params.pack(fill=tk.X, pady=(0, 8))

        # Row 0: Disk selector
        row0 = ttk.Frame(params)
        row0.pack(fill=tk.X, pady=2)
        ttk.Label(row0, text="Disk:", width=12, anchor=tk.E).pack(side=tk.LEFT)
        self.disk_combo_var = tk.StringVar()
        self.disk_combo = ttk.Combobox(row0, textvariable=self.disk_combo_var,
                                        state="readonly", width=70)
        self.disk_combo.pack(side=tk.LEFT, padx=(6, 4), fill=tk.X, expand=True)
        self.disk_combo.bind("<<ComboboxSelected>>", self._on_disk_selected)
        ttk.Button(row0, text="Refresh", command=self._detect_disks,
                   style="TButton").pack(side=tk.LEFT, padx=(2, 0))

        # Row 0b: Disk info label
        row0b = ttk.Frame(params)
        row0b.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(row0b, text="", width=12).pack(side=tk.LEFT)
        self.disk_info_label = ttk.Label(row0b, text="", style="Status.TLabel")
        self.disk_info_label.pack(side=tk.LEFT, padx=(6, 0))

        # Row 1: Source (manual override or image file)
        row1 = ttk.Frame(params)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Source:", width=12, anchor=tk.E).pack(side=tk.LEFT)
        self.source_var = tk.StringVar()
        src_entry = ttk.Entry(row1, textvariable=self.source_var, width=50)
        src_entry.pack(side=tk.LEFT, padx=(6, 4), fill=tk.X, expand=True)
        ttk.Button(row1, text="Image file...", command=self._browse_image,
                   style="TButton").pack(side=tk.LEFT, padx=(2, 0))

        # Row 2: LBA range
        row2 = ttk.Frame(params)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Start LBA:", width=12, anchor=tk.E).pack(side=tk.LEFT)
        self.start_lba_var = tk.StringVar(value="0")
        ttk.Entry(row2, textvariable=self.start_lba_var, width=18).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Label(row2, text="End LBA:", anchor=tk.E).pack(side=tk.LEFT)
        self.end_lba_var = tk.StringVar(value="0")
        ttk.Entry(row2, textvariable=self.end_lba_var, width=18).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Label(row2, text="Sector size:", anchor=tk.E).pack(side=tk.LEFT)
        self.sector_size_var = tk.StringVar(value="512")
        ttk.Entry(row2, textvariable=self.sector_size_var, width=8).pack(side=tk.LEFT, padx=(6, 4))
        self.capacity_label = ttk.Label(row2, text="", style="Status.TLabel")
        self.capacity_label.pack(side=tk.LEFT, padx=(8, 0))

        # Row 3: Patterns & chunk
        row3 = ttk.Frame(params)
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="Patterns:", width=12, anchor=tk.E).pack(side=tk.LEFT)
        self.patterns_var = tk.StringVar(value="0x00 0xFF")
        ttk.Entry(row3, textvariable=self.patterns_var, width=36).pack(
            side=tk.LEFT, padx=(6, 12), fill=tk.X, expand=True)
        ttk.Label(row3, text="Chunk size:", anchor=tk.E).pack(side=tk.LEFT)
        self.chunk_var = tk.StringVar(value="2048")
        ttk.Entry(row3, textvariable=self.chunk_var, width=8).pack(side=tk.LEFT, padx=(6, 0))

        # ── Buttons row ──
        btn_row = ttk.Frame(main)
        btn_row.pack(fill=tk.X, pady=(0, 8))

        self.start_btn = ttk.Button(btn_row, text="Start Analysis", command=self._start_analysis)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.stop_btn = ttk.Button(btn_row, text="Stop", command=self._stop_analysis,
                                   style="Stop.TButton", state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.save_btn = ttk.Button(btn_row, text="Save Report", command=self._save_report,
                                   style="Save.TButton", state=tk.DISABLED)
        self.save_btn.pack(side=tk.LEFT, padx=(0, 6))

        # Admin status indicator
        admin_text = "Admin: Yes" if is_admin() else "Admin: No (limited)"
        admin_color = self.GREEN if is_admin() else self.RED
        ttk.Label(btn_row, text=admin_text, foreground=admin_color,
                  font=("Segoe UI", 9)).pack(side=tk.RIGHT)

        # ── Progress area ──
        prog_frame = ttk.Frame(main)
        prog_frame.pack(fill=tk.X, pady=(0, 4))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(prog_frame, variable=self.progress_var,
                                             maximum=100, mode="determinate")
        self.progress_bar.pack(fill=tk.X)

        # ── Live stats row ──
        stats_frame = ttk.Frame(main)
        stats_frame.pack(fill=tk.X, pady=(0, 8))

        self.status_label = ttk.Label(stats_frame, text="Ready", style="Status.TLabel")
        self.status_label.pack(side=tk.LEFT)

        self.eta_label = ttk.Label(stats_frame, text="", style="Status.TLabel")
        self.eta_label.pack(side=tk.RIGHT)

        self.speed_label = ttk.Label(stats_frame, text="", style="Status.TLabel")
        self.speed_label.pack(side=tk.RIGHT, padx=(0, 16))

        # ── Live counters ──
        counters_frame = ttk.LabelFrame(main, text="  Live Statistics  ", padding=8)
        counters_frame.pack(fill=tk.X, pady=(0, 8))

        self.counters_inner = ttk.Frame(counters_frame)
        self.counters_inner.pack(fill=tk.X)
        self.counter_labels = {}

        # ── Report output ──
        report_frame = ttk.LabelFrame(main, text="  Report  ", padding=4)
        report_frame.pack(fill=tk.BOTH, expand=True)

        self.report_text = scrolledtext.ScrolledText(
            report_frame,
            wrap=tk.NONE,
            font=("Consolas", 9),
            bg=self.BG_LIGHT,
            fg=self.FG,
            insertbackground=self.FG,
            selectbackground=self.ACCENT,
            selectforeground=self.BG,
            borderwidth=0,
            padx=8,
            pady=8,
        )
        self.report_text.pack(fill=tk.BOTH, expand=True)

        # Horizontal scrollbar
        h_scroll = ttk.Scrollbar(report_frame, orient=tk.HORIZONTAL,
                                  command=self.report_text.xview)
        h_scroll.pack(fill=tk.X)
        self.report_text.configure(xscrollcommand=h_scroll.set)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _detect_disks(self):
        """Detect physical disks and populate the combo box."""
        self.detected_disks = get_physical_disks()

        if self.detected_disks:
            display_list = [d["display"] for d in self.detected_disks]
            self.disk_combo["values"] = display_list
            self.disk_combo.current(0)
            self._on_disk_selected(None)
        else:
            self.disk_combo["values"] = ["(no disks detected — run as Administrator)"]
            self.disk_combo.current(0)
            self.disk_info_label.configure(
                text="Could not detect disks. Run as Administrator for physical disk access.",
                foreground=self.RED,
            )

    def _on_disk_selected(self, _event):
        """Handle disk selection from combo box — auto-fill source, LBA, sector size."""
        idx = self.disk_combo.current()
        if idx < 0 or idx >= len(self.detected_disks):
            return

        disk = self.detected_disks[idx]
        self.source_var.set(disk["path"])
        self.start_lba_var.set("0")
        self.sector_size_var.set(str(disk["sector_size"]))

        if disk["sectors"] > 0:
            end_lba = disk["sectors"] - 1
            self.end_lba_var.set(str(end_lba))
            self.disk_info_label.configure(
                text=f"{disk['model']}  |  {format_size(disk['size_bytes'])}  |  "
                     f"{disk['sectors']:,} sectors x {disk['sector_size']}B  |  "
                     f"LBA 0 \u2014 {end_lba:,}",
                foreground=self.GREEN,
            )
        else:
            self.end_lba_var.set("0")
            self.disk_info_label.configure(
                text=f"{disk['model']}  |  Size unknown",
                foreground=self.YELLOW,
            )

        self._update_capacity_label()

    def _update_capacity_label(self):
        """Show human-readable size of the selected LBA range."""
        try:
            start = int(self.start_lba_var.get())
            end = int(self.end_lba_var.get())
            ss = int(self.sector_size_var.get())
            if end >= start and ss > 0:
                total = (end - start + 1) * ss
                self.capacity_label.configure(
                    text=f"= {format_size(total)}  ({end - start + 1:,} sectors)",
                    foreground=self.FG_DIM,
                )
            else:
                self.capacity_label.configure(text="")
        except ValueError:
            self.capacity_label.configure(text="")

    def _browse_image(self):
        path = filedialog.askopenfilename(
            title="Select disk image file",
            filetypes=[
                ("Disk images", "*.dd *.img *.raw *.bin *.iso"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.source_var.set(path)
            # Auto-calculate end LBA from file size
            try:
                file_size = os.path.getsize(path)
                ss = int(self.sector_size_var.get()) if self.sector_size_var.get() else 512
                if file_size > 0 and ss > 0:
                    total_sectors = file_size // ss
                    self.start_lba_var.set("0")
                    self.end_lba_var.set(str(total_sectors - 1) if total_sectors > 0 else "0")
                    self.disk_info_label.configure(
                        text=f"Image file: {format_size(file_size)}  |  "
                             f"{total_sectors:,} sectors x {ss}B",
                        foreground=self.ACCENT,
                    )
                    self._update_capacity_label()
            except Exception:
                pass

    def _validate_inputs(self):
        errors = []
        try:
            start = int(self.start_lba_var.get())
            if start < 0:
                errors.append("Start LBA must be >= 0")
        except ValueError:
            errors.append("Start LBA must be an integer")
            start = None

        try:
            end = int(self.end_lba_var.get())
        except ValueError:
            errors.append("End LBA must be an integer")
            end = None

        if start is not None and end is not None and end < start:
            errors.append("End LBA must be >= Start LBA")

        try:
            ss = int(self.sector_size_var.get())
            if ss <= 0:
                errors.append("Sector size must be > 0")
        except ValueError:
            errors.append("Sector size must be an integer")

        try:
            ch = int(self.chunk_var.get())
            if ch <= 0:
                errors.append("Chunk size must be > 0")
        except ValueError:
            errors.append("Chunk size must be an integer")

        pat_str = self.patterns_var.get().strip()
        if not pat_str:
            errors.append("At least one pattern is required")
        else:
            for p in pat_str.split():
                try:
                    parse_pattern(p)
                except Exception:
                    errors.append(f"Invalid pattern: {p}")

        if not self.source_var.get().strip():
            errors.append("Source is required")

        return errors

    def _start_analysis(self):
        errors = self._validate_inputs()
        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors))
            return

        source = self.source_var.get().strip()
        start_lba = int(self.start_lba_var.get())
        end_lba = int(self.end_lba_var.get())
        sector_size = int(self.sector_size_var.get())
        chunk_sectors = int(self.chunk_var.get())
        patterns = [parse_pattern(p) for p in self.patterns_var.get().split()]

        # Reset UI
        self.stop_event.clear()
        self.last_stats = None
        self.progress_var.set(0)
        self.report_text.configure(state=tk.NORMAL)
        self.report_text.delete("1.0", tk.END)
        self._clear_counters()
        self.status_label.configure(text="Analyzing...", foreground=self.YELLOW)
        self.speed_label.configure(text="")
        self.eta_label.configure(text="")

        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.save_btn.configure(state=tk.DISABLED)

        self.analysis_thread = threading.Thread(
            target=analyze_disk_threaded,
            args=(source, start_lba, end_lba, sector_size, patterns,
                  chunk_sectors, self.msg_queue, self.stop_event),
            daemon=True,
        )
        self.analysis_thread.start()

    def _stop_analysis(self):
        self.stop_event.set()
        self.stop_btn.configure(state=tk.DISABLED)
        self.status_label.configure(text="Stopping...", foreground=self.YELLOW)

    def _save_report(self):
        if not self.last_stats:
            return
        path = filedialog.asksaveasfilename(
            title="Save Report",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            report = generate_report(self.last_stats)
            with open(path, "w", encoding="utf-8") as f:
                f.write(report + "\n")
            self.status_label.configure(text=f"Report saved: {path}", foreground=self.GREEN)

    # ── Queue polling ─────────────────────────────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                if msg_type == "progress":
                    self._on_progress(data)
                elif msg_type == "done":
                    self._on_done(data)
                elif msg_type == "stopped":
                    self._on_stopped()
                elif msg_type == "error":
                    self._on_error(data)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _on_progress(self, data):
        self.progress_var.set(data["pct"] * 100)
        self.status_label.configure(
            text=f"Sector {data['sectors']:,} / {data['total']:,}  "
                 f"({data['pct']*100:.1f}%)  |  Errors: {data['errors']}",
            foreground=self.YELLOW,
        )
        self.speed_label.configure(text=f"Speed: {format_size(data['speed'])}/s")
        self.eta_label.configure(text=f"ETA: {format_duration(data['eta'])}")
        self._update_counters(data["counts"], data["total"])

    def _on_done(self, stats):
        self.last_stats = stats
        self.progress_var.set(100)
        self.status_label.configure(
            text=f"Done in {format_duration(stats['elapsed'])}  |  "
                 f"Errors: {stats['read_errors']}",
            foreground=self.GREEN,
        )
        self.speed_label.configure(text="")
        self.eta_label.configure(text="")
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self.save_btn.configure(state=tk.NORMAL)

        report = generate_report(stats)
        self.report_text.configure(state=tk.NORMAL)
        self.report_text.delete("1.0", tk.END)
        self.report_text.insert(tk.END, report)
        self._update_counters(stats["counts"], stats["total_sectors"])

    def _on_stopped(self):
        self.status_label.configure(text="Analysis stopped by user", foreground=self.RED)
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)

    def _on_error(self, error_msg):
        self.status_label.configure(text=f"Error: {error_msg}", foreground=self.RED)
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        messagebox.showerror("Analysis Error", error_msg)

    # ── Live counters ─────────────────────────────────────────────────────────

    def _clear_counters(self):
        for widget in self.counters_inner.winfo_children():
            widget.destroy()
        self.counter_labels = {}

    def _update_counters(self, counts, total):
        # Rebuild if pattern set changed
        keys = sorted(counts.keys(), key=lambda x: (x != "DATA", -counts[x]))
        if set(keys) != set(self.counter_labels.keys()):
            self._clear_counters()
            for i, key in enumerate(keys):
                frame = ttk.Frame(self.counters_inner)
                frame.pack(side=tk.LEFT, padx=(0, 24), pady=2)
                color = self.GREEN if key == "DATA" else self.FG_DIM
                name_lbl = ttk.Label(frame, text=key, foreground=color,
                                      font=("Segoe UI", 9, "bold"))
                name_lbl.pack(anchor=tk.W)
                val_lbl = ttk.Label(frame, text="0", foreground=self.FG,
                                     font=("Consolas", 11))
                val_lbl.pack(anchor=tk.W)
                pct_lbl = ttk.Label(frame, text="0%", foreground=self.FG_DIM,
                                     font=("Segoe UI", 9))
                pct_lbl.pack(anchor=tk.W)
                self.counter_labels[key] = (val_lbl, pct_lbl)

        for key in keys:
            if key in self.counter_labels:
                count = counts.get(key, 0)
                pct = (count / total * 100) if total > 0 else 0
                val_lbl, pct_lbl = self.counter_labels[key]
                val_lbl.configure(text=f"{count:,}")
                pct_lbl.configure(text=f"{pct:.1f}%  ({format_size(count * 512)})")


# ─── Entry point ──────────────────────────────────────────────────────────────


def main():
    root = tk.Tk()

    # Set window icon (optional, skip if not available)
    try:
        root.iconbitmap(default="")
    except Exception:
        pass

    app = DiskAnalyzerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
