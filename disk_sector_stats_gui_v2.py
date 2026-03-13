#!/usr/bin/env python3
"""
Disk Sector Pattern Statistics Analyzer — GUI Version 2

Tkinter-based graphical interface for analyzing raw disk sectors
within a specified LBA range and generating pattern statistics.

Features: pause/resume, disk auto-detection, live statistics, dark theme,
           Polish/English language support, visual disk map with real-time
           scan progress display, editable pattern colors.

Requires Administrator privileges for physical disk access on Windows.
"""

__version__ = "2.0.0"
__author__ = "Dariusz Jarczynski"

import ctypes
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, scrolledtext, ttk
from collections import defaultdict


SECTOR_SIZE_DEFAULT = 512

# Default colors for pattern visualization on the disk map
DEFAULT_PATTERN_COLORS = {
    "DATA": "#a6e3a1",         # Green
    "0X00": "#45475a",         # Dark gray
    "0XFF": "#9399b2",         # Light gray
    "0XAA": "#cba6f7",         # Mauve
    "0X55": "#74c7ec",         # Sapphire
    "0XDEADBEEF": "#f9e2af",   # Yellow
    "READ_ERROR": "#f38ba8",   # Red
}

MAP_BLOCK_SIZE = 3
MAP_HEIGHT = 150


# ─── Translations ─────────────────────────────────────────────────────────────

LANGUAGES = {
    "pl": {
        "lang_name": "Polski",
        # Window
        "window_title": "Analizator Wzorców Sektorów Dysku",
        "header": "Analizator Wzorców Sektorów Dysku",
        # Menu
        "menu_file": "Plik",
        "menu_save_report": "Zapisz raport...",
        "menu_exit": "Wyjście",
        "menu_analysis": "Analiza",
        "menu_start": "Start",
        "menu_pause": "Pauza",
        "menu_resume": "Wznów",
        "menu_stop": "Stop",
        "menu_language": "Język",
        "menu_help": "Pomoc",
        "menu_help_item": "Pomoc",
        "menu_about": "O programie",
        # Parameters
        "params_title": "  Parametry  ",
        "lbl_disk": "Dysk:",
        "btn_refresh": "Odśwież",
        "lbl_source": "Źródło:",
        "btn_image_file": "Plik obrazu...",
        "lbl_start_lba": "Początek LBA:",
        "lbl_end_lba": "Koniec LBA:",
        "lbl_sector_size": "Rozmiar sektora:",
        "lbl_patterns": "Wzorce:",
        "lbl_chunk_size": "Rozmiar bloku:",
        # Buttons
        "btn_start": "Start (F5)",
        "btn_pause": "Pauza (F6)",
        "btn_resume": "Wznów (F7)",
        "btn_stop": "Stop (F8)",
        "btn_save_report": "Zapisz raport",
        "admin_yes": "Admin: Tak",
        "admin_no": "Admin: Nie (ograniczony)",
        # Live stats
        "live_stats_title": "  Statystyki na żywo  ",
        "report_title": "  Raport  ",
        "status_ready": "Gotowy",
        # Progress messages
        "status_analyzing": "Analizowanie...",
        "status_resuming": "Wznawianie analizy...",
        "status_pausing": "Wstrzymywanie...",
        "status_stopping": "Zatrzymywanie...",
        "status_done": "Zakończono w {time}  |  Błędy: {errors}",
        "status_paused": "PAUZA na LBA {lba}  |  {done}/{total} sektorów ({pct}%)  |  Czas: {time}  |  Naciśnij F7 aby wznowić",
        "status_stopped": "Analiza zatrzymana przez użytkownika",
        "status_cancelled": "Analiza anulowana. Stan pauzy odrzucony.",
        "status_error": "Błąd: {msg}",
        "status_progress": "Sektor {sectors}/{total}  ({pct}%)  |  LBA: {lba}  |  Błędy: {errors}",
        "status_saved": "Raport zapisany: {path}",
        # Disk detection
        "no_disks": "(brak wykrytych dysków — uruchom jako Administrator)",
        "no_disks_msg": "Nie wykryto dysków. Uruchom jako Administrator aby uzyskać dostęp do dysków fizycznych.",
        "disk_size_unknown": "Rozmiar nieznany",
        "image_file_info": "Plik obrazu: {size}  |  {sectors} sektorów x {ss}B",
        # Validation
        "val_error_title": "Błąd walidacji",
        "val_start_negative": "Początek LBA musi być >= 0",
        "val_start_int": "Początek LBA musi być liczbą całkowitą",
        "val_end_int": "Koniec LBA musi być liczbą całkowitą",
        "val_end_less": "Koniec LBA musi być >= Początek LBA",
        "val_sector_positive": "Rozmiar sektora musi być > 0",
        "val_sector_int": "Rozmiar sektora musi być liczbą całkowitą",
        "val_chunk_positive": "Rozmiar bloku musi być > 0",
        "val_chunk_int": "Rozmiar bloku musi być liczbą całkowitą",
        "val_pattern_required": "Wymagany co najmniej jeden wzorzec",
        "val_pattern_invalid": "Nieprawidłowy wzorzec: {p}",
        "val_source_required": "Źródło jest wymagane",
        # Resume
        "resume_title": "Wznów",
        "resume_nothing": "Nie ma czego wznawiać. Najpierw rozpocznij nową analizę.",
        # Exit
        "exit_title": "Wyjście",
        "exit_confirm": "Analiza jest w toku. Czy na pewno chcesz wyjść?",
        # Error dialog
        "error_title": "Błąd analizy",
        # Browse
        "browse_title": "Wybierz plik obrazu dysku",
        "save_title": "Zapisz raport",
        # Disk errors
        "err_admin": "Dostęp do dysku fizycznego wymaga uprawnień Administratora.\nUruchom program jako Administrator.",
        "err_file_not_found": "Plik '{path}' nie istnieje.",
        # Report
        "rpt_title": "RAPORT ANALIZY WZORCÓW SEKTORÓW DYSKU",
        "rpt_source": "Źródło",
        "rpt_lba_range": "Zakres LBA",
        "rpt_sector_size": "Rozmiar sektora",
        "rpt_total": "Łącznie",
        "rpt_scan_time": "Czas skanu",
        "rpt_avg_speed": "Śr. prędkość",
        "rpt_read_errors": "*** BŁĘDY ODCZYTU: {n} sektorów nie udało się odczytać ***",
        "rpt_first_errors": "Pierwsze błędne LBA",
        "rpt_classification": "KLASYFIKACJA SEKTORÓW",
        "rpt_pattern": "Wzorzec",
        "rpt_count": "Ilość",
        "rpt_size": "Rozmiar",
        "rpt_percentage": "Procent",
        "rpt_useful_data": "<-- DANE",
        "rpt_summary": "PODSUMOWANIE",
        "rpt_data_sectors": "Sektory z danymi",
        "rpt_empty_sectors": "Puste sektory (wzorce)",
        "rpt_ratio": "Proporcja dane:puste",
        "rpt_ratio_na": "N/D (brak sektorów z danymi)",
        "rpt_top_regions": "TOP {n} NAJWIĘKSZYCH CIĄGŁYCH REGIONÓW",
        "rpt_type": "Typ",
        "rpt_start_lba": "Początek LBA",
        "rpt_end_lba": "Koniec LBA",
        "rpt_sectors": "Sektory",
        "rpt_data_regions": "REGIONY DANYCH ({n} łącznie):",
        "rpt_more_regions": "... i {n} więcej regionów z danymi",
        # Help
        "help_title": "Pomoc — Analizator Wzorców Sektorów Dysku",
        "help_content": """\
ANALIZATOR WZORCÓW SEKTORÓW DYSKU — POMOC
==========================================

OPIS
----
Narzędzie odczytuje surowe sektory z dysku fizycznego lub pliku
obrazu, klasyfikuje każdy sektor według zawartości i generuje
statystyki. Zaprojektowane do analizy forensycznej dysków po
atakach hakerskich, przypadkowym wyczyszczeniu lub zniszczeniu.

Każdy sektor jest sprawdzany czy jest całkowicie wypełniony znanym
wzorcem (np. same 0x00, same 0xFF). Jeśli nie — jest klasyfikowany
jako DATA (potencjalnie odzyskiwalne dane).


SZYBKI START
------------
1. Wybierz dysk fizyczny z listy "Dysk"
   (zakres LBA wypełni się automatycznie)
2. Dostosuj Początek/Koniec LBA jeśli chcesz skanować fragment
3. Kliknij "Start (F5)"
4. Obserwuj statystyki na żywo i pasek postępu
5. Po zakończeniu przejrzyj raport i zapisz go


SKRÓTY KLAWISZOWE
-----------------
  F1          — Pokaż tę pomoc
  F5          — Rozpocznij analizę (od nowa)
  F6          — Wstrzymaj analizę
  F7          — Wznów wstrzymaną analizę
  F8          — Zatrzymaj analizę
  Ctrl+S      — Zapisz raport do pliku


PARAMETRY
---------
Dysk:
    Lista rozwijana z wykrytymi dyskami fizycznymi. Automatycznie
    wypełnia Źródło, Rozmiar sektora i zakres LBA.
    Kliknij "Odśwież" aby ponownie wykryć dyski.

Źródło:
    Ścieżka do dysku fizycznego (np. \\\\.\\PhysicalDrive1) lub
    pliku obrazu (.dd, .img, .raw). Możesz wpisać ręcznie lub
    użyć przycisku "Plik obrazu...".

Początek LBA / Koniec LBA:
    Pierwszy i ostatni sektor do analizy (włącznie). Automatycznie
    wypełniane po wybraniu dysku (0 do ostatniego sektora).
    Edytowalne — możesz zawęzić zakres.

Rozmiar sektora:
    Bajty na sektor (domyślnie 512). Niektóre dyski używają 4096.
    Automatycznie wykrywany z WMI po wybraniu dysku.

Wzorce:
    Wzorce hex oddzielone spacjami. Domyślnie: 0x00 0xFF.
    Każdy sektor jest sprawdzany czy jest wypełniony powtarzającym
    się wzorcem. Można dodać dowolny wzorzec:
        0x00 0xFF 0xAA 0x55 0xDEADBEEF

Rozmiar bloku:
    Liczba sektorów czytanych jednocześnie (domyślnie 2048 = 1 MB).
    Większe wartości = szybsze I/O, więcej zużytej pamięci.


PAUZA / WZNOWIENIE
------------------
Możesz wstrzymać analizę w dowolnym momencie klawiszem F6.
Bieżący postęp (liczniki sektorów, regiony, pozycja) jest zapisany.

Aby kontynuować od miejsca wstrzymania: "Wznów (F7)".
Aby zacząć od nowa: "Start (F5)" — odrzuca stan pauzy.
Aby anulować całkowicie: "Stop (F8)" podczas pauzy.


RAPORT
------
Po zakończeniu analizy pojawia się pełny raport:
  - Tabela klasyfikacji sektorów (ilość, rozmiar, procent)
  - Podsumowanie (proporcja danych do pustych)
  - Top 30 największych ciągłych regionów
  - Osobna lista regionów DATA (do celowanego odzyskiwania)


WYMAGANIA
---------
  - Python 3.6+ z tkinter
  - Uprawnienia Administratora do dostępu do dysku (Windows)
  - Brak zewnętrznych bibliotek


WSKAZÓWKI
---------
  - Dla dużych dysków (>1 TB) rozważ skanowanie segmentami
    z własnymi zakresami LBA dla częściowych wyników.
  - Używaj Pauza+Wznów dla długich skanów wymagających przerw.
  - Zwiększ rozmiar bloku do 4096-8192 dla szybszych SSD.
  - Po znalezieniu regionów DATA użyj edytora hex aby sprawdzić
    faktyczną zawartość pod tymi adresami LBA.
""",
        # About
        "about_title": "O programie",
        "about_description": (
            "Narzędzie forensyczne do statystycznej analizy\n"
            "zawartości sektorów dysku twardego. Skanuje surowe\n"
            "sektory w podanym zakresie LBA i klasyfikuje je\n"
            "według wzorca — przydatne do oceny przetrwania danych\n"
            "po atakach hakerskich, przypadkowym wyczyszczeniu\n"
            "lub zniszczeniu dysku.\n"
        ),
        "about_license": "Licencja: MIT",
        "about_deps": "Python + Tkinter | Bez zewnętrznych zależności",
        "btn_close": "Zamknij",
        # V2: Disk map & pattern colors
        "disk_map_title": "  Mapa dysku  ",
        "lbl_pattern_colors": "Kolory wzorców:",
        "color_picker_title": "Wybierz kolor — {pattern}",
    },

    "en": {
        "lang_name": "English",
        # Window
        "window_title": "Disk Sector Pattern Analyzer",
        "header": "Disk Sector Pattern Analyzer",
        # Menu
        "menu_file": "File",
        "menu_save_report": "Save Report...",
        "menu_exit": "Exit",
        "menu_analysis": "Analysis",
        "menu_start": "Start",
        "menu_pause": "Pause",
        "menu_resume": "Resume",
        "menu_stop": "Stop",
        "menu_language": "Language",
        "menu_help": "Help",
        "menu_help_item": "Help",
        "menu_about": "About",
        # Parameters
        "params_title": "  Parameters  ",
        "lbl_disk": "Disk:",
        "btn_refresh": "Refresh",
        "lbl_source": "Source:",
        "btn_image_file": "Image file...",
        "lbl_start_lba": "Start LBA:",
        "lbl_end_lba": "End LBA:",
        "lbl_sector_size": "Sector size:",
        "lbl_patterns": "Patterns:",
        "lbl_chunk_size": "Chunk size:",
        # Buttons
        "btn_start": "Start (F5)",
        "btn_pause": "Pause (F6)",
        "btn_resume": "Resume (F7)",
        "btn_stop": "Stop (F8)",
        "btn_save_report": "Save Report",
        "admin_yes": "Admin: Yes",
        "admin_no": "Admin: No (limited)",
        # Live stats
        "live_stats_title": "  Live Statistics  ",
        "report_title": "  Report  ",
        "status_ready": "Ready",
        # Progress messages
        "status_analyzing": "Analyzing...",
        "status_resuming": "Resuming analysis...",
        "status_pausing": "Pausing...",
        "status_stopping": "Stopping...",
        "status_done": "Done in {time}  |  Errors: {errors}",
        "status_paused": "PAUSED at LBA {lba}  |  {done}/{total} sectors ({pct}%)  |  Time: {time}  |  Press F7 to resume",
        "status_stopped": "Analysis stopped by user",
        "status_cancelled": "Analysis cancelled. Paused state discarded.",
        "status_error": "Error: {msg}",
        "status_progress": "Sector {sectors}/{total}  ({pct}%)  |  LBA: {lba}  |  Errors: {errors}",
        "status_saved": "Report saved: {path}",
        # Disk detection
        "no_disks": "(no disks detected \u2014 run as Administrator)",
        "no_disks_msg": "Could not detect disks. Run as Administrator for physical disk access.",
        "disk_size_unknown": "Size unknown",
        "image_file_info": "Image file: {size}  |  {sectors} sectors x {ss}B",
        # Validation
        "val_error_title": "Validation Error",
        "val_start_negative": "Start LBA must be >= 0",
        "val_start_int": "Start LBA must be an integer",
        "val_end_int": "End LBA must be an integer",
        "val_end_less": "End LBA must be >= Start LBA",
        "val_sector_positive": "Sector size must be > 0",
        "val_sector_int": "Sector size must be an integer",
        "val_chunk_positive": "Chunk size must be > 0",
        "val_chunk_int": "Chunk size must be an integer",
        "val_pattern_required": "At least one pattern is required",
        "val_pattern_invalid": "Invalid pattern: {p}",
        "val_source_required": "Source is required",
        # Resume
        "resume_title": "Resume",
        "resume_nothing": "Nothing to resume. Start a new analysis first.",
        # Exit
        "exit_title": "Exit",
        "exit_confirm": "Analysis is running. Are you sure you want to exit?",
        # Error dialog
        "error_title": "Analysis Error",
        # Browse
        "browse_title": "Select disk image file",
        "save_title": "Save Report",
        # Disk errors
        "err_admin": "Physical disk access requires Administrator privileges.\nRun the program as Administrator.",
        "err_file_not_found": "File '{path}' not found.",
        # Report
        "rpt_title": "DISK SECTOR PATTERN ANALYSIS REPORT",
        "rpt_source": "Source",
        "rpt_lba_range": "LBA range",
        "rpt_sector_size": "Sector size",
        "rpt_total": "Total",
        "rpt_scan_time": "Scan time",
        "rpt_avg_speed": "Avg speed",
        "rpt_read_errors": "*** READ ERRORS: {n} sectors could not be read ***",
        "rpt_first_errors": "First error LBAs",
        "rpt_classification": "SECTOR CLASSIFICATION",
        "rpt_pattern": "Pattern",
        "rpt_count": "Count",
        "rpt_size": "Size",
        "rpt_percentage": "Percentage",
        "rpt_useful_data": "<-- USEFUL DATA",
        "rpt_summary": "SUMMARY",
        "rpt_data_sectors": "Sectors with useful data",
        "rpt_empty_sectors": "Empty/pattern sectors",
        "rpt_ratio": "Ratio data:empty",
        "rpt_ratio_na": "N/A (no data sectors found)",
        "rpt_top_regions": "TOP {n} LARGEST CONTIGUOUS REGIONS",
        "rpt_type": "Type",
        "rpt_start_lba": "Start LBA",
        "rpt_end_lba": "End LBA",
        "rpt_sectors": "Sectors",
        "rpt_data_regions": "DATA REGIONS ({n} total):",
        "rpt_more_regions": "... and {n} more data regions",
        # Help
        "help_title": "Help \u2014 Disk Sector Pattern Analyzer",
        "help_content": """\
DISK SECTOR PATTERN ANALYZER — HELP
====================================

OVERVIEW
--------
This tool reads raw sectors from a physical disk or image file,
classifies each sector by its content pattern, and generates
statistics. Designed for forensic analysis of disks after hacker
attacks, accidental wipes, or data destruction.

Each sector is checked whether it is entirely filled with a known
pattern (e.g. all 0x00, all 0xFF). If not — it is classified as
DATA (potentially recoverable information).


QUICK START
-----------
1. Select a physical disk from the "Disk" dropdown
   (LBA range fills automatically)
2. Adjust Start/End LBA if you want to scan only a part
3. Click "Start (F5)"
4. Watch live statistics and progress bar
5. When done, review the report and save it


KEYBOARD SHORTCUTS
------------------
  F1          — Show this help
  F5          — Start analysis (fresh)
  F6          — Pause analysis
  F7          — Resume paused analysis
  F8          — Stop analysis
  Ctrl+S      — Save report to file


PARAMETERS
----------
Disk:
    Dropdown with detected physical disks. Auto-fills Source,
    Sector size, and LBA range. Click "Refresh" to re-detect.

Source:
    Path to physical disk (e.g. \\\\.\\PhysicalDrive1) or image
    file (.dd, .img, .raw). You can type manually or use the
    "Image file..." button.

Start LBA / End LBA:
    First and last sector to analyze (inclusive). Auto-filled
    when selecting a disk (0 to last sector = full disk).
    Editable — you can narrow the range as needed.

Sector size:
    Bytes per sector (default 512). Some modern disks use 4096.
    Auto-detected from WMI when selecting a disk.

Patterns:
    Space-separated hex patterns to detect. Default: 0x00 0xFF.
    Each sector is checked if it is entirely filled with the
    repeating pattern. You can add any pattern:
        0x00 0xFF 0xAA 0x55 0xDEADBEEF

Chunk size:
    Number of sectors read at once (default 2048 = 1 MB).
    Larger values = faster I/O, more memory usage.


PAUSE / RESUME
--------------
You can pause analysis at any time with F6 or the Pause button.
The current progress (sector counts, regions, position) is saved.

To continue from where you left off, click "Resume (F7)".
To start over, click "Start (F5)" — this discards paused state.
To cancel completely, click "Stop (F8)" while paused.


REPORT
------
After analysis completes, a full report appears in the text area:
  - Sector classification table (count, size, percentage)
  - Summary (data vs empty ratio)
  - Top 30 largest contiguous regions
  - Separate list of DATA regions (for targeted recovery)


REQUIREMENTS
------------
  - Python 3.6+ with tkinter
  - Administrator privileges for physical disk access (Windows)
  - No external libraries required


TIPS
----
  - For large disks (>1 TB), consider scanning in segments
    using custom LBA ranges to get intermediate results.
  - Use Pause+Resume for long scans that may need interruption.
  - Increase chunk size to 4096-8192 for faster SSD scans.
  - After finding DATA regions, use a hex editor to inspect
    the actual content at those LBA offsets.
""",
        # About
        "about_title": "About",
        "about_description": (
            "Forensic tool for statistical analysis of hard drive\n"
            "sector content. Scans raw sectors within a specified\n"
            "LBA range and classifies them by pattern \u2014 useful for\n"
            "assessing data survival after hacker attacks, accidental\n"
            "wipes, or disk destruction.\n"
        ),
        "about_license": "License: MIT",
        "about_deps": "Python + Tkinter | No external dependencies",
        "btn_close": "Close",
        # V2: Disk map & pattern colors
        "disk_map_title": "  Disk Map  ",
        "lbl_pattern_colors": "Pattern colors:",
        "color_picker_title": "Choose color — {pattern}",
    },
}


def t(key, lang="pl", **kwargs):
    """Get translated string by key, with optional format arguments."""
    text = LANGUAGES.get(lang, LANGUAGES["pl"]).get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text


# ─── Backend (analysis logic) ────────────────────────────────────────────────


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except AttributeError:
        return True


def get_physical_disks():
    """Detect physical disks and their sizes using WMI (Windows)."""
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

    disks.sort(key=lambda d: d["path"])
    return disks


def open_disk(source, lang="pl"):
    if source.startswith("\\\\.\\") or source.startswith("//./"):
        if not is_admin():
            raise PermissionError(t("err_admin", lang))
        return open(source, "rb")
    else:
        if not os.path.isfile(source):
            raise FileNotFoundError(t("err_file_not_found", lang, path=source))
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
                          chunk_sectors, msg_queue, stop_event, pause_event,
                          resume_state=None, lang="pl"):
    """Run analysis in a background thread, posting updates to msg_queue."""
    try:
        pattern_sectors = [build_pattern_sector(p, sector_size) for p, _ in patterns]
        pattern_names = [name for _, name in patterns]

        total_sectors = end_lba - start_lba + 1

        if resume_state:
            counts = defaultdict(int, resume_state["counts"])
            regions = list(resume_state["regions"])
            current_region_type = resume_state["last_region_type"]
            current_region_start = resume_state["last_region_start"]
            read_errors = resume_state["read_errors"]
            error_sectors = list(resume_state["error_sectors"])
            current_lba = resume_state["current_lba"]
            elapsed_before = resume_state["elapsed_before"]
            sectors_processed = current_lba - start_lba
        else:
            counts = defaultdict(int)
            regions = []
            current_region_type = None
            current_region_start = start_lba
            read_errors = 0
            error_sectors = []
            current_lba = start_lba
            elapsed_before = 0.0
            sectors_processed = 0

        map_segments = []  # RLE of (lba, count, type) for disk map

        remaining = end_lba - current_lba + 1

        f = open_disk(source, lang)
        start_time = time.time()
        last_update = 0

        try:
            f.seek(current_lba * sector_size)

            while remaining > 0:
                if pause_event.is_set():
                    elapsed_this_run = time.time() - start_time
                    partial = {
                        "current_lba": current_lba,
                        "counts": dict(counts),
                        "regions": list(regions),
                        "last_region_type": current_region_type,
                        "last_region_start": current_region_start,
                        "read_errors": read_errors,
                        "error_sectors": list(error_sectors),
                        "elapsed_before": elapsed_before + elapsed_this_run,
                        "sectors_processed": sectors_processed,
                        "total_sectors": total_sectors,
                    }
                    msg_queue.put(("paused", partial))
                    return

                if stop_event.is_set():
                    msg_queue.put(("stopped", None))
                    return

                to_read = min(chunk_sectors, remaining)

                try:
                    data = f.read(to_read * sector_size)
                except OSError:
                    data = b""
                    for i in range(to_read):
                        if pause_event.is_set() or stop_event.is_set():
                            break
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

                    # Track for disk map visualization
                    if map_segments and map_segments[-1][2] == sector_type:
                        s = map_segments[-1]
                        map_segments[-1] = (s[0], s[1] + 1, s[2])
                    else:
                        map_segments.append((current_lba + i, 1, sector_type))

                    if sector_type != current_region_type:
                        if current_region_type is not None:
                            regions.append((current_region_start,
                                            current_lba + i - 1,
                                            current_region_type))
                        current_region_type = sector_type
                        current_region_start = current_lba + i

                current_lba += actual_sectors
                remaining -= actual_sectors
                sectors_processed += actual_sectors

                now = time.time()
                if now - last_update >= 0.25:
                    elapsed_total = elapsed_before + (now - start_time)
                    pct = sectors_processed / total_sectors
                    speed = (sectors_processed * sector_size / elapsed_total
                             if elapsed_total > 0 else 0)
                    eta = (elapsed_total / pct - elapsed_total) if pct > 0 else 0
                    msg_queue.put(("progress", {
                        "pct": pct,
                        "sectors": sectors_processed,
                        "total": total_sectors,
                        "speed": speed,
                        "eta": eta,
                        "counts": dict(counts),
                        "errors": read_errors,
                        "current_lba": current_lba,
                        "map_segments": map_segments,
                    }))
                    map_segments = []
                    last_update = now

        finally:
            f.close()

        if current_region_type is not None:
            regions.append((current_region_start, end_lba, current_region_type))

        elapsed_total = elapsed_before + (time.time() - start_time)

        stats = {
            "counts": dict(counts),
            "total_sectors": total_sectors,
            "sector_size": sector_size,
            "elapsed": elapsed_total,
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


def generate_report(stats, lang="pl", top_regions=30):
    """Generate the text report from stats dict."""
    _ = lambda key, **kw: t(key, lang, **kw)
    lines = []
    out = lines.append
    dash = "\u2014"

    out("=" * 78)
    out(f"  {_('rpt_title')}")
    out("=" * 78)
    out("")
    out(f"  {_('rpt_source')+':':<16}{stats['source']}")
    out(f"  {_('rpt_lba_range')+':':<16}{stats['start_lba']:,} \u2014 {stats['end_lba']:,}")
    out(f"  {_('rpt_sector_size')+':':<16}{stats['sector_size']} bytes")
    out(f"  {_('rpt_total')+':':<16}{stats['total_sectors']:,} sectors "
        f"({format_size(stats['total_sectors'] * stats['sector_size'])})")
    out(f"  {_('rpt_scan_time')+':':<16}{format_duration(stats['elapsed'])}")
    if stats["elapsed"] > 0:
        speed = stats["total_sectors"] * stats["sector_size"] / stats["elapsed"]
        out(f"  {_('rpt_avg_speed')+':':<16}{format_size(speed)}/s")
    out("")

    if stats["read_errors"] > 0:
        out(f"  {_('rpt_read_errors', n=stats['read_errors'])}")
        if stats["error_sectors"]:
            out(f"  {_('rpt_first_errors')}: "
                f"{', '.join(str(s) for s in stats['error_sectors'][:20])}")
        out("")

    out("-" * 78)
    out(f"  {_('rpt_classification')}")
    out("-" * 78)
    out("")
    out(f"  {_('rpt_pattern'):<20} {_('rpt_count'):>15} "
        f"{_('rpt_size'):>12} {_('rpt_percentage'):>12}")
    out(f"  {dash*20} {dash*15} {dash*12} {dash*12}")

    total = stats["total_sectors"]
    sorted_types = sorted(stats["counts"].items(),
                          key=lambda x: (x[0] != "DATA", -x[1]))
    data_sectors = 0
    non_data_sectors = 0

    for ptype, count in sorted_types:
        pct = (count / total * 100) if total > 0 else 0
        size = format_size(count * stats["sector_size"])
        marker = f" {_('rpt_useful_data')}" if ptype == "DATA" else ""
        out(f"  {ptype:<20} {count:>15,} {size:>12} {pct:>11.2f}%{marker}")
        if ptype == "DATA":
            data_sectors = count
        else:
            non_data_sectors += count

    out(f"  {dash*20} {dash*15} {dash*12} {dash*12}")
    out(f"  {'TOTAL':<20} {total:>15,} "
        f"{format_size(total * stats['sector_size']):>12} {'100.00%':>12}")
    out("")

    out("-" * 78)
    out(f"  {_('rpt_summary')}")
    out("-" * 78)
    out("")
    data_pct = (data_sectors / total * 100) if total > 0 else 0
    empty_pct = (non_data_sectors / total * 100) if total > 0 else 0
    out(f"  {_('rpt_data_sectors')+':':<30}{data_sectors:>15,} ({data_pct:.2f}%)")
    out(f"  {_('rpt_empty_sectors')+':':<30}{non_data_sectors:>15,} ({empty_pct:.2f}%)")
    if data_sectors > 0:
        out(f"  {_('rpt_ratio')+':':<30}1 : {non_data_sectors/data_sectors:.1f}")
    else:
        out(f"  {_('rpt_ratio')+':':<30}{_('rpt_ratio_na')}")
    out("")

    if stats["regions"]:
        out("-" * 78)
        out(f"  {_('rpt_top_regions', n=top_regions)}")
        out("-" * 78)
        out("")

        region_sizes = []
        for start, end, rtype in stats["regions"]:
            size = end - start + 1
            region_sizes.append((start, end, size, rtype))
        region_sizes.sort(key=lambda x: -x[2])

        out(f"  {'#':>4} {_('rpt_type'):<15} {_('rpt_start_lba'):>15} "
            f"{_('rpt_end_lba'):>15} {_('rpt_sectors'):>12} {_('rpt_size'):>12}")
        out(f"  {dash*4} {dash*15} {dash*15} {dash*15} "
            f"{dash*12} {dash*12}")

        for i, (start, end, size, rtype) in enumerate(region_sizes[:top_regions]):
            out(f"  {i+1:>4} {rtype:<15} {start:>15,} {end:>15,} "
                f"{size:>12,} {format_size(size * stats['sector_size']):>12}")
        out("")

        data_regions = [(s, e, sz, t_) for s, e, sz, t_ in region_sizes
                        if t_ == "DATA"]
        if data_regions:
            out(f"  {_('rpt_data_regions', n=len(data_regions))}")
            out(f"  {'#':>4} {_('rpt_start_lba'):>15} {_('rpt_end_lba'):>15} "
                f"{_('rpt_sectors'):>12} {_('rpt_size'):>12}")
            out(f"  {dash*4} {dash*15} {dash*15} "
                f"{dash*12} {dash*12}")
            for i, (start, end, size, _x) in enumerate(data_regions[:top_regions]):
                out(f"  {i+1:>4} {start:>15,} {end:>15,} {size:>12,} "
                    f"{format_size(size * stats['sector_size']):>12}")
            if len(data_regions) > top_regions:
                out(f"  {_('rpt_more_regions', n=len(data_regions) - top_regions)}")
            out("")

    out("=" * 78)
    return "\n".join(lines)


# ─── GUI ──────────────────────────────────────────────────────────────────────


class DiskAnalyzerGUI:
    """Main application window."""

    # Colors (Catppuccin Mocha inspired)
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

    STATE_IDLE = "idle"
    STATE_RUNNING = "running"
    STATE_PAUSED = "paused"

    def __init__(self, root):
        self.root = root
        self.lang = "pl"  # default language
        self.root.geometry("960x960")
        self.root.minsize(800, 700)
        self.root.configure(bg=self.BG)

        self.msg_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.analysis_thread = None
        self.last_stats = None
        self.detected_disks = []
        self.state = self.STATE_IDLE

        self.paused_state = None
        self.paused_params = None

        # V2: disk map & pattern colors
        self.pattern_colors = dict(DEFAULT_PATTERN_COLORS)
        self.map_region_data = []   # [(start_lba, count, type), ...]
        self.map_start_lba = 0
        self.map_total_sectors = 0
        self.map_photo = None

        self._apply_style()
        self._build_all()
        self._detect_disks()
        self._poll_queue()

    def _t(self, key, **kwargs):
        """Shortcut for translation with current language."""
        return t(key, self.lang, **kwargs)

    # ── Styles ────────────────────────────────────────────────────────────────

    def _apply_style(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".", background=self.BG, foreground=self.FG,
                         fieldbackground=self.BG_INPUT)
        style.configure("TFrame", background=self.BG)
        style.configure("TLabel", background=self.BG, foreground=self.FG,
                         font=("Segoe UI", 10))
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
        style.configure("Pause.TButton", background=self.YELLOW, foreground=self.BG)
        style.map("Pause.TButton",
                   background=[("active", "#fbe9c0"), ("disabled", self.BG_LIGHT)])
        style.configure("Resume.TButton", background=self.PEACH, foreground=self.BG)
        style.map("Resume.TButton",
                   background=[("active", "#fcc5a0"), ("disabled", self.BG_LIGHT)])
        style.configure("Stop.TButton", background=self.RED, foreground=self.BG)
        style.map("Stop.TButton",
                   background=[("active", "#f5a0b8"), ("disabled", self.BG_LIGHT)])
        style.configure("Save.TButton", background=self.GREEN, foreground=self.BG)
        style.map("Save.TButton",
                   background=[("active", "#bee8b7"), ("disabled", self.BG_LIGHT)])
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

    # ── Build / Rebuild UI ────────────────────────────────────────────────────

    def _build_all(self):
        """Build or rebuild the entire UI (used for language switching)."""
        # Preserve field values if rebuilding
        saved = {}
        for attr in ("source_var", "start_lba_var", "end_lba_var",
                      "sector_size_var", "patterns_var", "chunk_var"):
            var = getattr(self, attr, None)
            if var:
                saved[attr] = var.get()

        # Destroy existing widgets
        for widget in self.root.winfo_children():
            widget.destroy()

        self.root.title(self._t("window_title"))
        self._build_menu()
        self._build_ui()

        # Restore field values
        for attr, val in saved.items():
            getattr(self, attr).set(val)

    def _build_menu(self):
        menubar = tk.Menu(self.root, bg=self.BG_LIGHT, fg=self.FG,
                          activebackground=self.ACCENT, activeforeground=self.BG,
                          borderwidth=0)

        file_menu = tk.Menu(menubar, tearoff=0, bg=self.BG_LIGHT, fg=self.FG,
                            activebackground=self.ACCENT, activeforeground=self.BG)
        file_menu.add_command(label=self._t("menu_save_report"),
                              command=self._save_report, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label=self._t("menu_exit"),
                              command=self._on_exit, accelerator="Alt+F4")
        menubar.add_cascade(label=self._t("menu_file"), menu=file_menu)

        analysis_menu = tk.Menu(menubar, tearoff=0, bg=self.BG_LIGHT, fg=self.FG,
                                activebackground=self.ACCENT, activeforeground=self.BG)
        analysis_menu.add_command(label=self._t("menu_start"),
                                  command=self._start_analysis, accelerator="F5")
        analysis_menu.add_command(label=self._t("menu_pause"),
                                  command=self._pause_analysis, accelerator="F6")
        analysis_menu.add_command(label=self._t("menu_resume"),
                                  command=self._resume_analysis, accelerator="F7")
        analysis_menu.add_command(label=self._t("menu_stop"),
                                  command=self._stop_analysis, accelerator="F8")
        menubar.add_cascade(label=self._t("menu_analysis"), menu=analysis_menu)

        lang_menu = tk.Menu(menubar, tearoff=0, bg=self.BG_LIGHT, fg=self.FG,
                            activebackground=self.ACCENT, activeforeground=self.BG)
        lang_menu.add_command(label="Polski",
                              command=lambda: self._switch_language("pl"))
        lang_menu.add_command(label="English",
                              command=lambda: self._switch_language("en"))
        menubar.add_cascade(label=self._t("menu_language"), menu=lang_menu)

        help_menu = tk.Menu(menubar, tearoff=0, bg=self.BG_LIGHT, fg=self.FG,
                            activebackground=self.ACCENT, activeforeground=self.BG)
        help_menu.add_command(label=self._t("menu_help_item"),
                              command=self._show_help, accelerator="F1")
        help_menu.add_separator()
        help_menu.add_command(label=self._t("menu_about"),
                              command=self._show_about)
        menubar.add_cascade(label=self._t("menu_help"), menu=help_menu)

        self.root.config(menu=menubar)

        self.root.bind("<F1>", lambda e: self._show_help())
        self.root.bind("<F5>", lambda e: self._start_analysis())
        self.root.bind("<F6>", lambda e: self._pause_analysis())
        self.root.bind("<F7>", lambda e: self._resume_analysis())
        self.root.bind("<F8>", lambda e: self._stop_analysis())
        self.root.bind("<Control-s>", lambda e: self._save_report())

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text=self._t("header"),
                  style="Header.TLabel").pack(anchor=tk.W, pady=(0, 8))

        # Parameters
        params = ttk.LabelFrame(main, text=self._t("params_title"), padding=10)
        params.pack(fill=tk.X, pady=(0, 8))

        # Disk selector
        row0 = ttk.Frame(params)
        row0.pack(fill=tk.X, pady=2)
        ttk.Label(row0, text=self._t("lbl_disk"), width=14,
                  anchor=tk.E).pack(side=tk.LEFT)
        self.disk_combo_var = tk.StringVar()
        self.disk_combo = ttk.Combobox(row0, textvariable=self.disk_combo_var,
                                        state="readonly", width=70)
        self.disk_combo.pack(side=tk.LEFT, padx=(6, 4), fill=tk.X, expand=True)
        self.disk_combo.bind("<<ComboboxSelected>>", self._on_disk_selected)
        ttk.Button(row0, text=self._t("btn_refresh"),
                   command=self._detect_disks).pack(side=tk.LEFT, padx=(2, 0))

        row0b = ttk.Frame(params)
        row0b.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(row0b, text="", width=14).pack(side=tk.LEFT)
        self.disk_info_label = ttk.Label(row0b, text="", style="Status.TLabel")
        self.disk_info_label.pack(side=tk.LEFT, padx=(6, 0))

        # Source
        row1 = ttk.Frame(params)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text=self._t("lbl_source"), width=14,
                  anchor=tk.E).pack(side=tk.LEFT)
        self.source_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.source_var, width=50).pack(
            side=tk.LEFT, padx=(6, 4), fill=tk.X, expand=True)
        ttk.Button(row1, text=self._t("btn_image_file"),
                   command=self._browse_image).pack(side=tk.LEFT, padx=(2, 0))

        # LBA range
        row2 = ttk.Frame(params)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text=self._t("lbl_start_lba"), width=14,
                  anchor=tk.E).pack(side=tk.LEFT)
        self.start_lba_var = tk.StringVar(value="0")
        ttk.Entry(row2, textvariable=self.start_lba_var, width=18).pack(
            side=tk.LEFT, padx=(6, 12))
        ttk.Label(row2, text=self._t("lbl_end_lba"),
                  anchor=tk.E).pack(side=tk.LEFT)
        self.end_lba_var = tk.StringVar(value="0")
        ttk.Entry(row2, textvariable=self.end_lba_var, width=18).pack(
            side=tk.LEFT, padx=(6, 12))
        ttk.Label(row2, text=self._t("lbl_sector_size"),
                  anchor=tk.E).pack(side=tk.LEFT)
        self.sector_size_var = tk.StringVar(value="512")
        ttk.Entry(row2, textvariable=self.sector_size_var, width=8).pack(
            side=tk.LEFT, padx=(6, 4))
        self.capacity_label = ttk.Label(row2, text="", style="Status.TLabel")
        self.capacity_label.pack(side=tk.LEFT, padx=(8, 0))

        # Patterns
        row3 = ttk.Frame(params)
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text=self._t("lbl_patterns"), width=14,
                  anchor=tk.E).pack(side=tk.LEFT)
        self.patterns_var = tk.StringVar(value="0x00 0xFF")
        ttk.Entry(row3, textvariable=self.patterns_var, width=36).pack(
            side=tk.LEFT, padx=(6, 12), fill=tk.X, expand=True)
        ttk.Label(row3, text=self._t("lbl_chunk_size"),
                  anchor=tk.E).pack(side=tk.LEFT)
        self.chunk_var = tk.StringVar(value="2048")
        ttk.Entry(row3, textvariable=self.chunk_var, width=8).pack(
            side=tk.LEFT, padx=(6, 0))

        # Pattern colors
        row4 = ttk.Frame(params)
        row4.pack(fill=tk.X, pady=2)
        ttk.Label(row4, text=self._t("lbl_pattern_colors"), width=14,
                  anchor=tk.E).pack(side=tk.LEFT)
        self.colors_frame = ttk.Frame(row4)
        self.colors_frame.pack(side=tk.LEFT, padx=(6, 0), fill=tk.X)
        self._rebuild_color_swatches()

        # Buttons
        btn_row = ttk.Frame(main)
        btn_row.pack(fill=tk.X, pady=(0, 8))

        self.start_btn = ttk.Button(btn_row, text=self._t("btn_start"),
                                     command=self._start_analysis)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.pause_btn = ttk.Button(btn_row, text=self._t("btn_pause"),
                                     command=self._pause_analysis,
                                     style="Pause.TButton", state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.resume_btn = ttk.Button(btn_row, text=self._t("btn_resume"),
                                      command=self._resume_analysis,
                                      style="Resume.TButton", state=tk.DISABLED)
        self.resume_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.stop_btn = ttk.Button(btn_row, text=self._t("btn_stop"),
                                    command=self._stop_analysis,
                                    style="Stop.TButton", state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.save_btn = ttk.Button(btn_row, text=self._t("btn_save_report"),
                                    command=self._save_report,
                                    style="Save.TButton", state=tk.DISABLED)
        self.save_btn.pack(side=tk.LEFT, padx=(0, 6))

        admin_key = "admin_yes" if is_admin() else "admin_no"
        admin_color = self.GREEN if is_admin() else self.RED
        ttk.Label(btn_row, text=self._t(admin_key), foreground=admin_color,
                  font=("Segoe UI", 9)).pack(side=tk.RIGHT)

        # Progress
        prog_frame = ttk.Frame(main)
        prog_frame.pack(fill=tk.X, pady=(0, 4))
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(prog_frame, variable=self.progress_var,
                                             maximum=100, mode="determinate")
        self.progress_bar.pack(fill=tk.X)

        stats_frame = ttk.Frame(main)
        stats_frame.pack(fill=tk.X, pady=(0, 8))
        self.status_label = ttk.Label(stats_frame, text=self._t("status_ready"),
                                       style="Status.TLabel")
        self.status_label.pack(side=tk.LEFT)
        self.eta_label = ttk.Label(stats_frame, text="", style="Status.TLabel")
        self.eta_label.pack(side=tk.RIGHT)
        self.speed_label = ttk.Label(stats_frame, text="", style="Status.TLabel")
        self.speed_label.pack(side=tk.RIGHT, padx=(0, 16))

        # Disk Map
        map_lf = ttk.LabelFrame(main, text=self._t("disk_map_title"), padding=4)
        map_lf.pack(fill=tk.X, pady=(0, 8))
        self.map_canvas = tk.Canvas(map_lf, height=MAP_HEIGHT,
                                     bg=self.BG, highlightthickness=0,
                                     cursor="crosshair")
        self.map_canvas.pack(fill=tk.X)
        self.map_canvas.bind("<Configure>", self._on_map_configure)
        self.legend_frame = ttk.Frame(map_lf)
        self.legend_frame.pack(fill=tk.X, pady=(4, 0))
        self._rebuild_legend()

        # Live counters
        counters_frame = ttk.LabelFrame(main, text=self._t("live_stats_title"),
                                         padding=8)
        counters_frame.pack(fill=tk.X, pady=(0, 8))
        self.counters_inner = ttk.Frame(counters_frame)
        self.counters_inner.pack(fill=tk.X)
        self.counter_labels = {}

        # Report
        report_frame = ttk.LabelFrame(main, text=self._t("report_title"),
                                       padding=4)
        report_frame.pack(fill=tk.BOTH, expand=True)
        self.report_text = scrolledtext.ScrolledText(
            report_frame, wrap=tk.NONE, font=("Consolas", 9),
            bg=self.BG_LIGHT, fg=self.FG, insertbackground=self.FG,
            selectbackground=self.ACCENT, selectforeground=self.BG,
            borderwidth=0, padx=8, pady=8,
        )
        self.report_text.pack(fill=tk.BOTH, expand=True)
        h_scroll = ttk.Scrollbar(report_frame, orient=tk.HORIZONTAL,
                                  command=self.report_text.xview)
        h_scroll.pack(fill=tk.X)
        self.report_text.configure(xscrollcommand=h_scroll.set)

    # ── Language switching ────────────────────────────────────────────────────

    def _switch_language(self, lang):
        if lang == self.lang:
            return
        # Save field values before rebuild
        saved = {}
        for attr in ("source_var", "start_lba_var", "end_lba_var",
                      "sector_size_var", "patterns_var", "chunk_var"):
            var = getattr(self, attr, None)
            if var:
                saved[attr] = var.get()

        self.lang = lang
        self._build_all()
        self._detect_disks()

        # Restore field values AFTER detect_disks (which overwrites them)
        for attr, val in saved.items():
            getattr(self, attr).set(val)
        self._update_capacity_label()

        # Restore button states
        self._set_state(self.state)
        # Re-render report if exists
        stats = self._get_report_stats()
        if stats:
            report = generate_report(stats, lang=self.lang)
            self.report_text.configure(state=tk.NORMAL)
            self.report_text.delete("1.0", tk.END)
            self.report_text.insert(tk.END, report)

    # ── Button state management ───────────────────────────────────────────────

    def _set_state(self, state):
        self.state = state
        if state == self.STATE_IDLE:
            self.start_btn.configure(state=tk.NORMAL)
            self.pause_btn.configure(state=tk.DISABLED)
            self.resume_btn.configure(
                state=tk.NORMAL if self.paused_state else tk.DISABLED)
            self.stop_btn.configure(state=tk.DISABLED)
            self.save_btn.configure(
                state=tk.NORMAL if self.last_stats else tk.DISABLED)
        elif state == self.STATE_RUNNING:
            self.start_btn.configure(state=tk.DISABLED)
            self.pause_btn.configure(state=tk.NORMAL)
            self.resume_btn.configure(state=tk.DISABLED)
            self.stop_btn.configure(state=tk.NORMAL)
            self.save_btn.configure(state=tk.DISABLED)
        elif state == self.STATE_PAUSED:
            self.start_btn.configure(state=tk.NORMAL)
            self.pause_btn.configure(state=tk.DISABLED)
            self.resume_btn.configure(state=tk.NORMAL)
            self.stop_btn.configure(state=tk.NORMAL)
            self.save_btn.configure(state=tk.NORMAL)

    # ── Disk detection ────────────────────────────────────────────────────────

    def _detect_disks(self):
        self.detected_disks = get_physical_disks()
        if self.detected_disks:
            display_list = [d["display"] for d in self.detected_disks]
            self.disk_combo["values"] = display_list
            self.disk_combo.current(0)
            self._on_disk_selected(None)
        else:
            self.disk_combo["values"] = [self._t("no_disks")]
            self.disk_combo.current(0)
            self.disk_info_label.configure(
                text=self._t("no_disks_msg"), foreground=self.RED)

    def _on_disk_selected(self, _event):
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
                foreground=self.GREEN)
        else:
            self.end_lba_var.set("0")
            self.disk_info_label.configure(
                text=f"{disk['model']}  |  {self._t('disk_size_unknown')}",
                foreground=self.YELLOW)
        self._update_capacity_label()

    def _update_capacity_label(self):
        try:
            start = int(self.start_lba_var.get())
            end = int(self.end_lba_var.get())
            ss = int(self.sector_size_var.get())
            if end >= start and ss > 0:
                total = (end - start + 1) * ss
                self.capacity_label.configure(
                    text=f"= {format_size(total)}  ({end - start + 1:,} sectors)",
                    foreground=self.FG_DIM)
            else:
                self.capacity_label.configure(text="")
        except ValueError:
            self.capacity_label.configure(text="")

    def _browse_image(self):
        path = filedialog.askopenfilename(
            title=self._t("browse_title"),
            filetypes=[
                ("Disk images", "*.dd *.img *.raw *.bin *.iso"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.source_var.set(path)
            try:
                file_size = os.path.getsize(path)
                ss = int(self.sector_size_var.get()) if self.sector_size_var.get() else 512
                if file_size > 0 and ss > 0:
                    total_sectors = file_size // ss
                    self.start_lba_var.set("0")
                    self.end_lba_var.set(
                        str(total_sectors - 1) if total_sectors > 0 else "0")
                    self.disk_info_label.configure(
                        text=self._t("image_file_info",
                                     size=format_size(file_size),
                                     sectors=f"{total_sectors:,}", ss=ss),
                        foreground=self.ACCENT)
                    self._update_capacity_label()
            except Exception:
                pass

    # ── Validation ────────────────────────────────────────────────────────────

    def _validate_inputs(self):
        errors = []
        try:
            start = int(self.start_lba_var.get())
            if start < 0:
                errors.append(self._t("val_start_negative"))
        except ValueError:
            errors.append(self._t("val_start_int"))
            start = None
        try:
            end = int(self.end_lba_var.get())
        except ValueError:
            errors.append(self._t("val_end_int"))
            end = None
        if start is not None and end is not None and end < start:
            errors.append(self._t("val_end_less"))
        try:
            ss = int(self.sector_size_var.get())
            if ss <= 0:
                errors.append(self._t("val_sector_positive"))
        except ValueError:
            errors.append(self._t("val_sector_int"))
        try:
            ch = int(self.chunk_var.get())
            if ch <= 0:
                errors.append(self._t("val_chunk_positive"))
        except ValueError:
            errors.append(self._t("val_chunk_int"))
        pat_str = self.patterns_var.get().strip()
        if not pat_str:
            errors.append(self._t("val_pattern_required"))
        else:
            for p in pat_str.split():
                try:
                    parse_pattern(p)
                except Exception:
                    errors.append(self._t("val_pattern_invalid", p=p))
        if not self.source_var.get().strip():
            errors.append(self._t("val_source_required"))
        return errors

    # ── Analysis control ──────────────────────────────────────────────────────

    def _get_source_display_name(self, source):
        """Get human-friendly name for the source (disk model or file name)."""
        # Check if source matches a detected physical disk
        for disk in self.detected_disks:
            if disk["path"].lower() == source.lower():
                return f"{disk['model']} ({disk['path']})"
        # For image files, show filename
        if os.path.isfile(source):
            return f"{os.path.basename(source)} ({source})"
        return source

    def _start_analysis(self):
        if self.state == self.STATE_RUNNING:
            return
        errors = self._validate_inputs()
        if errors:
            messagebox.showerror(self._t("val_error_title"), "\n".join(errors))
            return
        source = self.source_var.get().strip()
        start_lba = int(self.start_lba_var.get())
        end_lba = int(self.end_lba_var.get())
        sector_size = int(self.sector_size_var.get())
        chunk_sectors = int(self.chunk_var.get())
        patterns = [parse_pattern(p) for p in self.patterns_var.get().split()]

        self.paused_state = None
        self.paused_params = None
        self.last_stats = None
        self.source_display_name = self._get_source_display_name(source)
        self.paused_params = (source, start_lba, end_lba, sector_size,
                              patterns, chunk_sectors)

        # V2: ensure colors for all patterns and init map
        for _, name in patterns:
            if name not in self.pattern_colors:
                self.pattern_colors[name] = "#ffffff"
        self._rebuild_color_swatches()
        self._rebuild_legend()
        self._init_map(start_lba, end_lba)

        self._launch_thread(source, start_lba, end_lba, sector_size,
                            patterns, chunk_sectors, resume_state=None)

    def _pause_analysis(self):
        if self.state != self.STATE_RUNNING:
            return
        self.pause_event.set()
        self.pause_btn.configure(state=tk.DISABLED)
        self.status_label.configure(text=self._t("status_pausing"),
                                     foreground=self.YELLOW)

    def _resume_analysis(self):
        if self.state == self.STATE_RUNNING:
            return
        if not self.paused_state or not self.paused_params:
            messagebox.showinfo(self._t("resume_title"),
                                self._t("resume_nothing"))
            return
        source, start_lba, end_lba, sector_size, patterns, chunk_sectors = \
            self.paused_params
        # V2: rebuild map from stored regions before resuming
        if self.paused_state and self.paused_state.get("regions"):
            self._rebuild_map_from_regions(
                self.paused_state["regions"], start_lba, end_lba)
        self._launch_thread(source, start_lba, end_lba, sector_size,
                            patterns, chunk_sectors,
                            resume_state=self.paused_state)

    def _stop_analysis(self):
        if self.state == self.STATE_RUNNING:
            self.stop_event.set()
            self.stop_btn.configure(state=tk.DISABLED)
            self.status_label.configure(text=self._t("status_stopping"),
                                         foreground=self.YELLOW)
        elif self.state == self.STATE_PAUSED:
            self.paused_state = None
            self.paused_params = None
            self._set_state(self.STATE_IDLE)
            self.status_label.configure(text=self._t("status_cancelled"),
                                         foreground=self.RED)

    def _launch_thread(self, source, start_lba, end_lba, sector_size,
                       patterns, chunk_sectors, resume_state):
        self.stop_event.clear()
        self.pause_event.clear()
        if not resume_state:
            self.progress_var.set(0)
            self.report_text.configure(state=tk.NORMAL)
            self.report_text.delete("1.0", tk.END)
            self._clear_counters()
        status_key = "status_resuming" if resume_state else "status_analyzing"
        self.status_label.configure(text=self._t(status_key),
                                     foreground=self.YELLOW)
        self.speed_label.configure(text="")
        self.eta_label.configure(text="")
        self._set_state(self.STATE_RUNNING)
        self.analysis_thread = threading.Thread(
            target=analyze_disk_threaded,
            args=(source, start_lba, end_lba, sector_size, patterns,
                  chunk_sectors, self.msg_queue, self.stop_event,
                  self.pause_event, resume_state, self.lang),
            daemon=True,
        )
        self.analysis_thread.start()

    # ── Save / Exit ───────────────────────────────────────────────────────────

    def _get_report_stats(self):
        """Get stats for report — from finished analysis or from paused state."""
        if self.last_stats:
            return self.last_stats
        if self.paused_state and self.paused_params:
            # Build partial stats from paused state
            source, start_lba, end_lba, sector_size, patterns, chunk = \
                self.paused_params
            partial = self.paused_state
            display_name = getattr(self, "source_display_name", source)
            return {
                "counts": partial["counts"],
                "total_sectors": partial["total_sectors"],
                "sector_size": sector_size,
                "elapsed": partial["elapsed_before"],
                "regions": partial["regions"],
                "read_errors": partial["read_errors"],
                "error_sectors": partial["error_sectors"],
                "start_lba": start_lba,
                "end_lba": partial["current_lba"] - 1,
                "source": display_name,
                "pattern_names": [name for _, name in patterns],
            }
        return None

    def _save_report(self):
        stats = self._get_report_stats()
        if not stats:
            return
        path = filedialog.asksaveasfilename(
            title=self._t("save_title"), defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            report = generate_report(stats, lang=self.lang)
            with open(path, "w", encoding="utf-8") as f:
                f.write(report + "\n")
            self.status_label.configure(
                text=self._t("status_saved", path=path), foreground=self.GREEN)

    def _on_exit(self):
        if self.state == self.STATE_RUNNING:
            if not messagebox.askyesno(self._t("exit_title"),
                                        self._t("exit_confirm")):
                return
            self.stop_event.set()
        self.root.destroy()

    # ── Help & About ──────────────────────────────────────────────────────────

    def _show_help(self):
        help_win = tk.Toplevel(self.root)
        help_win.title(self._t("help_title"))
        help_win.geometry("680x580")
        help_win.configure(bg=self.BG)
        help_win.transient(self.root)
        help_win.grab_set()

        text = scrolledtext.ScrolledText(
            help_win, wrap=tk.WORD, font=("Consolas", 10),
            bg=self.BG_LIGHT, fg=self.FG, borderwidth=0, padx=16, pady=16)
        text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        text.insert(tk.END, self._t("help_content"))
        text.configure(state=tk.DISABLED)

        ttk.Button(help_win, text=self._t("btn_close"), style="TButton",
                   command=help_win.destroy).pack(pady=(0, 12))

    def _show_about(self):
        about_win = tk.Toplevel(self.root)
        about_win.title(self._t("about_title"))
        about_win.geometry("460x340")
        about_win.configure(bg=self.BG)
        about_win.resizable(False, False)
        about_win.transient(self.root)
        about_win.grab_set()

        frame = ttk.Frame(about_win, padding=24)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text=self._t("header"), foreground=self.ACCENT,
                  font=("Segoe UI", 16, "bold")).pack(pady=(0, 4))
        ttk.Label(frame, text=f"Version {__version__}", foreground=self.FG_DIM,
                  font=("Segoe UI", 10)).pack(pady=(0, 16))
        ttk.Label(frame, text=self._t("about_description"), foreground=self.FG,
                  font=("Segoe UI", 10), justify=tk.CENTER).pack(pady=(0, 16))
        ttk.Label(frame, text=f"Author: {__author__}", foreground=self.PEACH,
                  font=("Segoe UI", 10, "bold")).pack(pady=(0, 4))
        ttk.Label(frame, text=self._t("about_license"), foreground=self.FG_DIM,
                  font=("Segoe UI", 9)).pack(pady=(0, 4))
        ttk.Label(frame, text=self._t("about_deps"), foreground=self.FG_DIM,
                  font=("Segoe UI", 9)).pack(pady=(0, 16))
        ttk.Button(frame, text=self._t("btn_close"), style="TButton",
                   command=about_win.destroy).pack()

    # ── Disk Map ──────────────────────────────────────────────────────────────

    def _rebuild_color_swatches(self):
        """Rebuild pattern color swatch buttons in the parameters section."""
        for w in self.colors_frame.winfo_children():
            w.destroy()

        patterns = ["DATA"]
        pat_str = getattr(self, "patterns_var", None)
        pat_str = pat_str.get().strip() if pat_str else "0x00 0xFF"
        for p in pat_str.split():
            try:
                _, name = parse_pattern(p)
                if name not in patterns:
                    patterns.append(name)
            except Exception:
                pass

        for name in patterns:
            color = self.pattern_colors.get(name, "#ffffff")
            fr = ttk.Frame(self.colors_frame)
            fr.pack(side=tk.LEFT, padx=(0, 10))
            swatch = tk.Canvas(fr, width=18, height=18, bg=color,
                               highlightthickness=1,
                               highlightbackground=self.FG_DIM,
                               cursor="hand2")
            swatch.pack(side=tk.LEFT, padx=(0, 3))
            swatch.bind("<Button-1>", lambda e, n=name: self._pick_color(n))
            ttk.Label(fr, text=name, font=("Segoe UI", 8)).pack(side=tk.LEFT)

    def _pick_color(self, pattern_name):
        """Open color chooser for a pattern."""
        current = self.pattern_colors.get(pattern_name, "#ffffff")
        result = colorchooser.askcolor(
            color=current,
            title=self._t("color_picker_title", pattern=pattern_name))
        if result[1]:
            self.pattern_colors[pattern_name] = result[1]
            self._rebuild_color_swatches()
            self._rebuild_legend()
            self._redraw_map()

    def _rebuild_legend(self):
        """Rebuild the color legend below the disk map."""
        for w in self.legend_frame.winfo_children():
            w.destroy()

        patterns = ["DATA"]
        pat_str = getattr(self, "patterns_var", None)
        pat_str = pat_str.get().strip() if pat_str else "0x00 0xFF"
        for p in pat_str.split():
            try:
                _, name = parse_pattern(p)
                if name not in patterns:
                    patterns.append(name)
            except Exception:
                pass

        for name in patterns:
            color = self.pattern_colors.get(name, "#ffffff")
            fr = ttk.Frame(self.legend_frame)
            fr.pack(side=tk.LEFT, padx=(0, 14))
            sw = tk.Canvas(fr, width=12, height=12, bg=color,
                           highlightthickness=1,
                           highlightbackground=self.FG_DIM)
            sw.pack(side=tk.LEFT, padx=(0, 3))
            ttk.Label(fr, text=name, font=("Segoe UI", 8)).pack(side=tk.LEFT)

    def _init_map(self, start_lba, end_lba):
        """Initialize map for a new analysis run."""
        self.map_start_lba = start_lba
        self.map_total_sectors = end_lba - start_lba + 1
        self.map_region_data = []
        self._create_map_photo()

    def _create_map_photo(self):
        """Create/recreate the PhotoImage backing the disk map."""
        w = max(self.map_canvas.winfo_width(), 200)
        h = max(self.map_canvas.winfo_height(), MAP_HEIGHT)
        self.map_photo = tk.PhotoImage(width=w, height=h)
        self.map_photo.put(self.BG, to=(0, 0, w, h))
        self.map_canvas.delete("all")
        self.map_canvas.create_image(0, 0, image=self.map_photo, anchor=tk.NW)

    def _on_map_configure(self, event):
        """Handle map canvas resize — redraw all stored data."""
        if self.map_region_data:
            self._create_map_photo()
            self._draw_map_segments(self.map_region_data)

    def _update_map(self, new_segments):
        """Append new segments and draw them on the map."""
        if not new_segments:
            return
        self.map_region_data.extend(new_segments)
        self._draw_map_segments(new_segments)

    def _draw_map_segments(self, segments):
        """Draw a list of (start_lba, count, type) segments onto the map."""
        if not segments or self.map_total_sectors <= 0 or not self.map_photo:
            return
        w = self.map_photo.width()
        h = self.map_photo.height()
        cols = w // MAP_BLOCK_SIZE
        rows = h // MAP_BLOCK_SIZE
        total_blocks = cols * rows
        if total_blocks <= 0:
            return
        spb = self.map_total_sectors / total_blocks  # sectors per block

        for seg_start, seg_count, seg_type in segments:
            offset = seg_start - self.map_start_lba
            b_start = max(0, int(offset / spb))
            b_end = min(total_blocks - 1,
                        int((offset + seg_count - 1) / spb))
            color = self.pattern_colors.get(seg_type, "#ffffff")

            # Batch by row for efficiency
            b = b_start
            while b <= b_end:
                row = b // cols
                col = b % cols
                # How many blocks in this row?
                row_last = min(b_end, (row + 1) * cols - 1)
                end_col = row_last % cols
                x1 = col * MAP_BLOCK_SIZE
                y1 = row * MAP_BLOCK_SIZE
                x2 = (end_col + 1) * MAP_BLOCK_SIZE
                y2 = y1 + MAP_BLOCK_SIZE
                self.map_photo.put(color, to=(x1, y1, x2, y2))
                b = row_last + 1

    def _redraw_map(self):
        """Full redraw of the map (e.g., after color change)."""
        if not self.map_region_data or not self.map_photo:
            return
        w = self.map_photo.width()
        h = self.map_photo.height()
        self.map_photo.put(self.BG, to=(0, 0, w, h))
        self._draw_map_segments(self.map_region_data)

    def _rebuild_map_from_regions(self, regions, start_lba, end_lba):
        """Reconstruct disk map from region data (for resume)."""
        self._init_map(start_lba, end_lba)
        if regions:
            segs = [(s, e - s + 1, rtype) for s, e, rtype in regions]
            self._update_map(segs)

    # ── Queue polling ─────────────────────────────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                if msg_type == "progress":
                    self._on_progress(data)
                elif msg_type == "done":
                    self._on_done(data)
                elif msg_type == "paused":
                    self._on_paused(data)
                elif msg_type == "stopped":
                    self._on_stopped()
                elif msg_type == "error":
                    self._on_error(data)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _on_progress(self, data):
        self.progress_var.set(data["pct"] * 100)
        current_lba = data.get("current_lba", "?")
        self.status_label.configure(
            text=self._t("status_progress",
                         sectors=f"{data['sectors']:,}",
                         total=f"{data['total']:,}",
                         pct=f"{data['pct']*100:.1f}",
                         lba=f"{current_lba:,}",
                         errors=data["errors"]),
            foreground=self.YELLOW)
        self.speed_label.configure(text=f"Speed: {format_size(data['speed'])}/s")
        self.eta_label.configure(text=f"ETA: {format_duration(data['eta'])}")
        self._update_counters(data["counts"], data["total"])
        # V2: update disk map
        if "map_segments" in data:
            self._update_map(data["map_segments"])

    def _on_done(self, stats):
        # Replace raw device path with friendly name in report
        if hasattr(self, "source_display_name"):
            stats["source"] = self.source_display_name
        self.last_stats = stats
        self.paused_state = None
        self.paused_params = None
        self.progress_var.set(100)
        self.status_label.configure(
            text=self._t("status_done",
                         time=format_duration(stats["elapsed"]),
                         errors=stats["read_errors"]),
            foreground=self.GREEN)
        self.speed_label.configure(text="")
        self.eta_label.configure(text="")
        self._set_state(self.STATE_IDLE)
        report = generate_report(stats, lang=self.lang)
        self.report_text.configure(state=tk.NORMAL)
        self.report_text.delete("1.0", tk.END)
        self.report_text.insert(tk.END, report)
        self._update_counters(stats["counts"], stats["total_sectors"])

    def _on_paused(self, partial):
        self.paused_state = partial
        sectors_done = partial["sectors_processed"]
        total = partial["total_sectors"]
        pct = (sectors_done / total * 100) if total > 0 else 0
        self.status_label.configure(
            text=self._t("status_paused",
                         lba=f"{partial['current_lba']:,}",
                         done=f"{sectors_done:,}",
                         total=f"{total:,}",
                         pct=f"{pct:.1f}",
                         time=format_duration(partial["elapsed_before"])),
            foreground=self.PEACH)
        self.speed_label.configure(text="")
        self.eta_label.configure(text="")
        self._set_state(self.STATE_PAUSED)
        self._update_counters(partial["counts"], total)

        # Generate and display partial report
        stats = self._get_report_stats()
        if stats:
            report = generate_report(stats, lang=self.lang)
            self.report_text.configure(state=tk.NORMAL)
            self.report_text.delete("1.0", tk.END)
            self.report_text.insert(tk.END, report)

    def _on_stopped(self):
        self.paused_state = None
        self.paused_params = None
        self.status_label.configure(text=self._t("status_stopped"),
                                     foreground=self.RED)
        self.speed_label.configure(text="")
        self.eta_label.configure(text="")
        self._set_state(self.STATE_IDLE)

    def _on_error(self, error_msg):
        self.status_label.configure(text=self._t("status_error", msg=error_msg),
                                     foreground=self.RED)
        self.speed_label.configure(text="")
        self.eta_label.configure(text="")
        self._set_state(self.STATE_IDLE)
        messagebox.showerror(self._t("error_title"), error_msg)

    # ── Live counters ─────────────────────────────────────────────────────────

    def _clear_counters(self):
        for widget in self.counters_inner.winfo_children():
            widget.destroy()
        self.counter_labels = {}

    def _update_counters(self, counts, total):
        keys = sorted(counts.keys(), key=lambda x: (x != "DATA", -counts[x]))
        if set(keys) != set(self.counter_labels.keys()):
            self._clear_counters()
            for key in keys:
                frame = ttk.Frame(self.counters_inner)
                frame.pack(side=tk.LEFT, padx=(0, 24), pady=2)
                color = self.GREEN if key == "DATA" else self.FG_DIM
                ttk.Label(frame, text=key, foreground=color,
                          font=("Segoe UI", 9, "bold")).pack(anchor=tk.W)
                val_lbl = ttk.Label(frame, text="0", foreground=self.FG,
                                     font=("Consolas", 11))
                val_lbl.pack(anchor=tk.W)
                pct_lbl = ttk.Label(frame, text="0%", foreground=self.FG_DIM,
                                     font=("Segoe UI", 9))
                pct_lbl.pack(anchor=tk.W)
                self.counter_labels[key] = (val_lbl, pct_lbl)

        sector_size = int(self.sector_size_var.get()) if self.sector_size_var.get() else 512
        for key in keys:
            if key in self.counter_labels:
                count = counts.get(key, 0)
                pct = (count / total * 100) if total > 0 else 0
                val_lbl, pct_lbl = self.counter_labels[key]
                val_lbl.configure(text=f"{count:,}")
                pct_lbl.configure(
                    text=f"{pct:.1f}%  ({format_size(count * sector_size)})")


# ─── Entry point ──────────────────────────────────────────────────────────────


def main():
    root = tk.Tk()
    try:
        root.iconbitmap(default="")
    except Exception:
        pass

    app = DiskAnalyzerGUI(root)
    root.protocol("WM_DELETE_WINDOW", app._on_exit)
    root.mainloop()


if __name__ == "__main__":
    main()
