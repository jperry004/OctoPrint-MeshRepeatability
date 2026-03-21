# OctoPrint Mesh Repeatability

OctoPrint plugin for capturing Marlin `M420 V` bed mesh output after a print finishes, fails, or is cancelled, then comparing that mesh against the previous successful capture.

## What It Does

- Automatically captures the active bilinear mesh on:
  - `PRINT_DONE`
  - `PRINT_FAILED`
  - `PRINT_CANCELLED`
- Supports manual capture from the plugin tab
- Stores each capture as its own JSON file in the plugin data folder
- Compares each successful capture against the previous successful capture
- Shows:
  - parsed mesh
  - delta matrix
  - max absolute delta
  - mean absolute delta
- Exports capture history as CSV
- Keeps only the newest 50 saved captures

## Requirements

- OctoPrint 1.8+ recommended
- Python 3.7 to 3.x
- Marlin firmware with bilinear mesh output available from `M420 V`

## Install

### OctoPrint Plugin Manager

In OctoPrint:

1. Open `Settings -> Plugin Manager`
2. Click `Get More...`
3. Paste this URL into `... from URL`

```text
https://github.com/jperry004/OctoPrint-MeshRepeatability/archive/refs/heads/main.zip
```

4. Click `Install`
5. Restart OctoPrint when prompted

### Manual pip Install

```bash
pip install https://github.com/jperry004/OctoPrint-MeshRepeatability/archive/refs/heads/main.zip
```

## Usage

### Automatic Capture

Run or cancel a print normally. After the job ends, the plugin sends `M420 V`, parses the bilinear mesh, saves a JSON record, and updates the history list.

### Manual Capture

Open the `Mesh Repeatability` tab and click:

- `Capture Mesh Now`
- `Save Current Mesh`

### Review Results

The plugin tab shows:

- capture history
- trigger source
- parsed mesh
- delta matrix
- raw printer output

### Export CSV

Use `Export CSV` in the plugin tab to download summary history.

## Data Storage

Captures are stored in the OctoPrint plugin data folder as JSON files:

```text
~/.octoprint/data/mesh_repeatability/
```

Typical filenames:

```text
capture_1773981439371.json
capture_1773996358540.json
```

On some non-default OctoPrint installs, the base directory may differ, for example:

```text
~/.HypoCenter/data/mesh_repeatability/
```

## Supported Mesh Format

The parser is built for Marlin bilinear mesh output from `M420 V`, including printers that insert blank lines between rows.

Example:

```text
Bilinear Leveling Grid:

      0      1      2      3

 0 +0.543 +0.339 +0.322 +0.643

 1 +0.343 +0.137 +0.112 +0.304

 2 +0.353 +0.112 +0.098 +0.388

 3 +0.505 +0.128 +0.368 +1.030

echo:Bed Leveling ON
ok
```

The plugin intentionally reads only the bilinear grid section and ignores later subdivided mesh output.

## Limitations

- Designed for Marlin bilinear mesh output
- Not intended for UBL parsing
- Assumes `M420 V` is available and returns mesh rows
- If the printer never responds, the capture times out automatically

## Development Notes

- Package identifier: `mesh_repeatability`
- Python package: `octoprint_mesh_repeatability`
- Current version: `0.3.2`

## License

AGPLv3. See `LICENSE`.
