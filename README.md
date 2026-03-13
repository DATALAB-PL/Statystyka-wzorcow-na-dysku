# Disk Sector Pattern Statistics Analyzer

Narzędzie forensyczne do analizy statystycznej zawartości sektorów dysku twardego. Skanuje surowe sektory w podanym zakresie LBA i klasyfikuje je według zawartości — pozwala szybko ocenić ile danych zostało na dysku po ataku hakerskim, wipe'ie lub uszkodzeniu.

Dostępne w dwóch wersjach:
- **CLI** (`disk_sector_stats.py`) — wersja konsolowa, idealna do skryptowania i automatyzacji
- **GUI** (`disk_sector_stats_gui.py`) — wersja graficzna z ciemnym interfejsem, paskiem postępu i podglądem statystyk na żywo

## Problem

Po ataku hakerskim lub operacji wipe dysk może wyglądać na "pusty", ale ręczne scrollowanie w edytorze heksadecymalnym ujawnia rozproszone fragmenty danych pomiędzy dużymi blokami zer. Potrzebna jest automatyczna statystyka, żeby odpowiedzieć na pytania:

- Jaki procent dysku zawiera faktyczne dane?
- Ile miejsca zajmują sektory wypełnione zerami (0x00) lub jedynkami (0xFF)?
- Gdzie na dysku znajdują się największe ciągłe bloki danych?
- Jaki jest stosunek danych do pustych obszarów?

## Funkcjonalności

- **Bezpośredni odczyt z dysku fizycznego** (`\\.\PhysicalDriveN`) lub z obrazu dysku (`.dd`, `.img`, `.raw`)
- **Klasyfikacja sektorów** — każdy sektor jest sprawdzany czy pasuje do wzorca (np. cały `0x00`, cały `0xFF`) czy zawiera dane
- **Konfigurowalne wzorce** — domyślnie `0x00` i `0xFF`, ale można dodać dowolne (np. `0xAA`, `0x55`, `0xDEADBEEF`)
- **Analiza ciągłych regionów** — identyfikuje największe bloki danych i pustki
- **Pasek postępu** z ETA i prędkością odczytu
- **Obsługa błędów odczytu** — przy bad sectorach przechodzi na odczyt sektor-po-sektorze
- **Zapis raportu do pliku** (`--output`)
- **Brak zależności zewnętrznych** — czysty Python 3, biblioteka standardowa

## Wersja GUI

Wersja graficzna (`disk_sector_stats_gui.py`) oferuje:

- **Ciemny interfejs** (dark theme) z kolorowym oznaczeniem stanów
- **Podgląd statystyk na żywo** — liczniki sektorów aktualizowane w trakcie analizy
- **Pasek postępu** z prędkością i ETA
- **Przycisk Stop** — bezpieczne przerwanie analizy w dowolnym momencie
- **Przycisk List Disks** — wyświetla dostępne dyski fizyczne (Windows)
- **Przeglądarka obrazów** — dialog wyboru pliku `.dd`/`.img`/`.raw`
- **Zapis raportu** do pliku tekstowego po zakończeniu analizy
- **Walidacja danych wejściowych** przed rozpoczęciem

```bash
python disk_sector_stats_gui.py
```

## Wymagania

- Python 3.6+ (z tkinter — dołączony standardowo na Windows)
- **Uprawnienia Administratora** (Windows) lub root (Linux) do odczytu dysku fizycznego
- Brak zewnętrznych bibliotek

## Instalacja

```bash
git clone <repo-url>
cd "Statystyka wzorców na dysku"
```

Nie wymaga instalacji — uruchamiany bezpośrednio jako skrypt Python.

## Użycie

### Podstawowe

```bash
# Analiza pierwszych 1M sektorów dysku (domyślne wzorce: 0x00, 0xFF)
python disk_sector_stats.py \\.\PhysicalDrive1 0 1000000

# Analiza całego dysku 500GB (976 562 500 sektorów po 512B)
python disk_sector_stats.py \\.\PhysicalDrive1 0 976562499
```

### Dodatkowe wzorce

```bash
# Szukaj także sektorów wypełnionych 0xAA, 0x55 (typowe po secure erase)
python disk_sector_stats.py \\.\PhysicalDrive1 0 1000000 --patterns 0x00 0xFF 0xAA 0x55

# Szukaj wielobajtowego wzorca powtarzanego w sektorze
python disk_sector_stats.py \\.\PhysicalDrive1 0 1000000 --patterns 0x00 0xFF 0xDEADBEEF
```

### Analiza obrazu dysku

```bash
python disk_sector_stats.py disk_image.dd 0 2048
python disk_sector_stats.py backup.raw 0 500000 --sector-size 4096
```

### Opcje zapisu i wydajności

```bash
# Zapis raportu do pliku
python disk_sector_stats.py \\.\PhysicalDrive1 0 1000000 --output raport.txt

# Pomiń analizę regionów (szybciej, mniej RAM)
python disk_sector_stats.py \\.\PhysicalDrive1 0 1000000 --no-regions

# Większy chunk = szybszy odczyt (domyślnie 2048 sektorów = 1MB)
python disk_sector_stats.py \\.\PhysicalDrive1 0 1000000 --chunk-size 8192
```

## Identyfikacja numeru dysku (Windows)

```cmd
wmic diskdrive list brief
wmic diskdrive get name,size,model
```

Lub w PowerShell:

```powershell
Get-PhysicalDisk | Format-Table DeviceId, FriendlyName, Size, MediaType
```

## Przykładowy raport

```
==============================================================================
  DISK SECTOR PATTERN ANALYSIS REPORT
==============================================================================

  Source:        \\.\PhysicalDrive1
  LBA range:    0 — 999,999
  Sector size:  512 bytes
  Total:        1,000,000 sectors (488.28 MB)
  Scan time:    45.3s
  Avg speed:    10.78 MB/s

------------------------------------------------------------------------------
  SECTOR CLASSIFICATION
------------------------------------------------------------------------------

  Pattern                  Count         Size   Percentage
  ————————————————————— ——————————————— ———————————— ————————————
  DATA                   142,857     69.75 MB       14.29% <-- USEFUL DATA
  0X00                   714,286    348.77 MB       71.43%
  0XFF                   142,857     69.75 MB       14.29%
  ————————————————————— ——————————————— ———————————— ————————————
  TOTAL                1,000,000    488.28 MB      100.00%

------------------------------------------------------------------------------
  SUMMARY
------------------------------------------------------------------------------

  Sectors with useful data:         142,857 (14.29%)
  Empty/pattern sectors:            857,143 (85.71%)
  Ratio data:empty:           1 : 6.0

------------------------------------------------------------------------------
  TOP 30 LARGEST CONTIGUOUS REGIONS
------------------------------------------------------------------------------

     # Type             Start LBA         End LBA      Sectors         Size
  ———— ——————————————— ——————————————— ——————————————— ———————————— ————————————
     1 0X00                      0         500,000      500,001    244.14 MB
     2 DATA                500,001         642,857      142,857     69.75 MB
     3 0XFF                642,858         785,714      142,857     69.75 MB
     4 0X00                785,715         999,999      214,285    104.63 MB
```

## Parametry

| Parametr | Domyślnie | Opis |
|---|---|---|
| `source` | (wymagany) | Ścieżka do dysku (`\\.\PhysicalDrive1`) lub pliku obrazu |
| `start_lba` | (wymagany) | Pierwszy sektor LBA do analizy (włącznie) |
| `end_lba` | (wymagany) | Ostatni sektor LBA do analizy (włącznie) |
| `--sector-size` | `512` | Rozmiar sektora w bajtach |
| `--patterns` | `0x00 0xFF` | Lista wzorców hex do wykrywania |
| `--chunk-size` | `2048` | Liczba sektorów czytanych jednocześnie |
| `--output`, `-o` | brak | Ścieżka do pliku z raportem |
| `--no-regions` | wyłączony | Pomiń analizę ciągłych regionów |
| `--top-regions` | `30` | Ile największych regionów pokazać |

## Jak to działa

1. Otwiera dysk/obraz w trybie binarnym (read-only)
2. Seekuje do pozycji `start_lba * sector_size`
3. Czyta dane w chunkach (domyślnie 1MB) dla wydajności
4. Każdy 512-bajtowy sektor jest porównywany z wzorcami:
   - Jeśli cały sektor = powtórzony wzorzec → klasyfikacja jako ten wzorzec
   - W przeciwnym razie → klasyfikacja jako `DATA`
5. Śledzi ciągłe regiony tego samego typu
6. Generuje raport ze statystykami i mapą regionów

## Bezpieczeństwo

- Program otwiera dysk **wyłącznie do odczytu** (`"rb"`) — nie modyfikuje żadnych danych
- Nie wymaga instalacji dodatkowych sterowników
- Działa z uprawnieniami Administratora tylko dlatego, że Windows wymaga tego do raw disk access

## Licencja

MIT
