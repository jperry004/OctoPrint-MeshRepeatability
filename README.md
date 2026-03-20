# OctoPrint Mesh Repeatability Plugin (MVP v0.2.1)

A powerful OctoPrint plugin for capturing and comparing Marlin bed leveling mesh data to test printer repeatability. Perfect for troubleshooting leveling issues and validating mechanical stability.

## Features

### ✅ Core Functionality
- **Automatic Mesh Capture**: Captures M420 V output automatically when:
  - Print finishes successfully (`PRINT_DONE`)
  - Print fails (`PRINT_FAILED`)
  - Print is cancelled (`PRINT_CANCELLED`)
  - Manual trigger via UI button
- **Robust GCODE Parsing**: Strict, defensive parser for Marlin bilinear leveling grids
  - Handles `Recv:` prefixes (with or without)
  - Skips headers and formatting lines automatically
  - Validates rectangular grid consistency
  - Graceful error handling with detailed parse status

### 📊 Analysis & Comparison
- **Delta Statistics**: Compares current mesh against most recent successful capture
  - Max absolute delta (largest change)
  - Mean absolute delta (average change)
  - Full delta matrix showing change at each probe point
- **Per-Record JSON Storage**: Each capture saved as individual JSON for data integrity
- **Persistent History**: Browse all 50 most recent captures in the UI

### 🔄 Data Management
- **Rotating Buffer**: Automatic pruning keeps max 50 records (oldest deleted automatically)
- **CSV Export**: Download full history with one click for Excel/analysis
- **No Data Loss**: One corrupted JSON file won't affect history

### 🖥️ User Interface
- **History Browser**: Chronological list of all captures with trigger source
- **Tabbed View**:
  - **Stats & Mesh**: Compare meshes, view delta matrix, inspect parsed grid
  - **Raw Text**: See exact serial output from printer for debugging
- **Clean N/A Handling**: First capture clearly shows "no previous mesh for comparison"
- **Formatted Matrix Display**: Nicely aligned grid output for readability

---

## Installation

### Install From OctoPrint "Get More..."

In OctoPrint:

1. Open **Settings -> Plugin Manager**
2. Click **Get More...**
3. Paste this URL into **... from URL**

```text
https://github.com/jperry004/OctoPrint-MeshRepeatability/archive/refs/heads/main.zip
```

4. Click **Install**
5. Restart OctoPrint when prompted

After restart, look for the new **Mesh Repeatability** tab.

### Manual Install

If you prefer the command line:

```bash
pip install https://github.com/jperry004/OctoPrint-MeshRepeatability/archive/refs/heads/main.zip
```

---

## Usage

### Manual Capture
1. In OctoPrint, go to the **"Mesh Repeatability"** tab
2. Click **"Capture Mesh Now"** button
3. Wait 2–3 seconds for the printer to respond
4. Your capture appears in the history list

### Automatic Capture
- Every time a print finishes (successfully, fails, or is cancelled), a capture is automatically triggered
- Appears in history immediately

### View Results
1. Click on any capture in the **History** list (left panel)
2. Select the **"Stats & Mesh"** tab to see:
   - **Trigger**: What caused the capture (print_done, print_failed, manual, etc.)
   - **Max Absolute Delta**: Largest change from previous mesh
   - **Mean Absolute Delta**: Average change across all points
   - **Delta Matrix**: Row-by-row comparison
   - **Current Parsed Mesh**: The grid values captured
3. Select **"Raw Text"** tab to see the exact serial output for debugging

### Export History
1. Click the **"Export History as CSV"** button
2. File downloads automatically as `mesh_repeatability_history_TIMESTAMP.csv`
3. Open in Excel or your favorite analysis tool
4. Columns: `id`, `timestamp`, `trigger`, `job_filename`, `parse_status`, `max_abs_delta`, `mean_abs_delta`

### Refresh History
- Click **"Refresh History"** to reload the list (usually automatic, but useful if you manually delete files)

---

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│  OctoPrint Core                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │ EventHandlerPlugin mixin                         │   │
│  │ - PRINT_DONE / PRINT_FAILED / PRINT_CANCELLED  │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  MeshRepeatabilityPlugin (__init__.py)                 │
│  ┌──────────────────────────────────────────────────┐   │
│  │ State Machine                                    │   │
│  │ idle → pending → capturing → idle              │   │
│  │                                                  │   │
│  │ + M420 V Parser (strict Bilinear format)       │   │
│  │ + Delta Statistics Calculator                   │   │
│  │ + Auto-Pruning (max 50 records)                │   │
│  │ + CSV Export                                    │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Data Storage                                           │
│  ~/.octoprint/data/mesh_repeatability/                 │
│  ├── capture_1741234567890.json                        │
│  ├── capture_1741234567891.json                        │
│  └── ... (max 50 files, rotating buffer)              │
└─────────────────────────────────────────────────────────┘
```

### Capture Flow

1. **Event Trigger**: Print finishes or manual button clicked
2. **M420 V Sent**: Plugin sends "M420 V" to printer command queue
3. **Serial Hook**: Plugin listens to incoming serial data via `octoprint.comm.protocol.gcode.received`
4. **State Pending**: Waiting for "Bilinear Leveling Grid:" marker
5. **State Capturing**: Buffering all lines until "ok" (end-of-command marker)
6. **Parse & Save**: Extract grid values, calculate stats vs. previous, save JSON
7. **Auto-Prune**: If >50 records exist, delete oldest
8. **UI Update**: History refreshed, new capture visible

### JSON Record Example

```json
{
  "id": "1741234567890",
  "timestamp": 1741234567.890,
  "trigger": "print_done",
  "job_filename": "benchy.gcode",
  "command_used": "M420 V",
  "raw_text": "Recv: Bilinear Leveling Grid:\nRecv: 0 1 2 3\n...",
  "parsed_mesh": [
    [0.105, -0.113, -0.115, 0.172],
    [0.0, -0.149, -0.158, -0.025],
    ...
  ],
  "parse_status": "success",
  "parse_error": null,
  "stats_vs_previous": {
    "max_abs_delta": 0.012,
    "mean_abs_delta": 0.005,
    "delta_matrix": [
      [0.001, -0.002, 0.000, 0.005],
      ...
    ]
  }
}
```

---

## Parser Logic (M420 V Format)

The plugin expects standard Marlin bilinear leveling grid output:

```
Bilinear Leveling Grid:
 0   1   2   3
0 +0.105 -0.113 -0.115 +0.172
1 +0.000 -0.149 -0.158 -0.025
2 -0.009 -0.166 -0.160 +0.040
3 +0.079 -0.219 -0.068 +0.488

Fade Height 5.00
ok
```

**Parser Steps:**
1. Strip `Recv:` prefixes (if present)
2. Wait for "Bilinear Leveling Grid:" trigger line
3. Skip column headers (line starting with "0 1 2")
4. Parse data rows: first token must be integer (row index), remaining tokens floats
5. Stop on empty line or first non-grid line after data collection

**Features:**
- Handles positive/negative values: `+0.105`, `-0.113`
- Defensive line handling: skips junk gracefully
- Dimension validation: all rows must have same column count
- Error reporting: parse failures logged with details

---

## Limitations & Known Issues

### Current MVP Scope
- **Bilinear Only**: Works strictly with Marlin bilinear leveling. UBL (Unified Bed Leveling) not supported yet.
- **Sequential Assumption**: Assumes M420 V commands don't overlap. Rapid-fire M420 V spam could theoretically blend captures, though the `ok` terminator prevents infinite loops.
- **Manual Pruning**: If you want to clean up history, delete files manually from `~/.octoprint/data/mesh_repeatability/`
- **5-Second Wait**: UI waits 5 seconds before refreshing after manual capture (M420 V is instant, but added buffer). Click "Refresh History" if you want to see results immediately.

### Next Steps (Future Versions)
- UBL/Linear leveling format support
- Chart of max_delta over time
- Delete-all history button
- Import historical data from external sources
- Automatic export on schedule (daily/weekly CSV)
- Webhook notifications on drift threshold

---

## Troubleshooting

### "No grid data found" in parse_status

**Cause**: Parser didn't find "Bilinear Leveling Grid:" in the output.

**Fix**:
1. Verify your printer is Marlin with bilinear leveling enabled
2. Check OctoPrint terminal: manually type `M420 V` and confirm output
3. Look at the "Raw Text" tab for the failed capture to see what was received
4. If the printer isn't outputting the grid, check Marlin firmware config

### Mesh capturing doesn't trigger on print done

**Cause**: OctoPrint event system not firing, or printer commands not accessible.

**Fix**:
1. Check OctoPrint logs: `tail -f ~/.octoprint/logs/octoprint.log`
2. Verify printer is connected and idle (not mid-print)
3. Try manual capture button to verify the plugin is loaded
4. Restart OctoPrint and retry

### CSV export is empty or shows "N/A"

**Cause**: First capture has no previous mesh to compare against (expected).

**Fix**: This is normal for the first capture. Run a second capture after the first, and the CSV will show delta stats in the second row.

### History keeps showing old data after restart

**Cause**: Browser caching the UI.

**Fix**: Hard refresh your browser (Ctrl+Shift+R or Cmd+Shift+R on Mac).

---

## File Structure

```
OctoPrint-MeshRepeatability/
├── README.md                                  # This file
├── setup.py                                   # Installation config
├── .gitignore                                 # Git ignore rules
└── octoprint_mesh_repeatability/
    ├── __init__.py                            # Main plugin logic
    ├── templates/
    │   └── mesh_repeatability.jinja2          # UI template
    └── static/
        └── js/
            └── mesh_repeatability.js          # Frontend logic
```

---

## Development & Contributing

### Local Testing

1. Clone this repo
2. Create a Python venv: `python3 -m venv venv`
3. Activate: `source venv/bin/activate`
4. Install in editable mode: `pip install -e .`
5. Run OctoPrint (if you have a test instance): `octoprint serve`

### Parser Unit Tests

A simple test script is included in the code comments. To verify parsing:

```python
import re

raw_sample = """Recv: Bilinear Leveling Grid:
Recv: 0 1 2 3
Recv: 0 +0.105 -0.113 -0.115 +0.172
...
Recv: ok"""

# Copy the _parse_m420_output logic and test
```

### Submitting Improvements

1. Fork this repo
2. Create a feature branch: `git checkout -b feature/your-idea`
3. Commit changes: `git commit -am "Add your feature"`
4. Push: `git push origin feature/your-idea`
5. Open a Pull Request

---

## License

AGPLv3 — See `LICENSE` file for details.

---

## Support

- **Issues**: Open an issue on GitHub
- **Feature Requests**: Describe your use case and desired behavior
- **Questions**: Check the troubleshooting section above first

---

## Changelog

### v0.2.0 (Current)
- ✅ Added capture on PRINT_FAILED and PRINT_CANCELLED
- ✅ Auto-pruning: rotating buffer of 50 records max
- ✅ CSV export functionality
- ✅ Fixed first-capture N/A handling in UI
- ✅ Clean integer filenames (no float timestamps)

### v0.1.0 (Initial MVP)
- ✅ Core capture on PRINT_DONE
- ✅ M420 V parser with strict bilinear validation
- ✅ Delta stats (max, mean, matrix)
- ✅ Manual capture trigger
- ✅ History browser with raw text view

---

**Enjoy precision repeatability testing!** 🖨️📊
