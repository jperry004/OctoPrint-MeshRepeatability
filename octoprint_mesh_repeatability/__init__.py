import octoprint.plugin
import octoprint.events
import os
import time
import json
import re
import csv
import io
import logging
from logging.handlers import RotatingFileHandler

class MeshRepeatabilityPlugin(
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.SimpleApiPlugin,
    octoprint.plugin.EventHandlerPlugin
):
    def __init__(self):
        self._capture_state = "idle"
        self._capture_buffer = []
        self._current_trigger = None
        self._current_filename = None
        self._capture_timestamp = None
        self._last_mesh = None  # Store the last captured mesh for UI display
        self._capture_count = 0
        self._file_logger = None  # Dedicated file logger
        self._log_file_path = None

    def on_after_startup(self):
        self._data_folder = self.get_plugin_data_folder()
        if not os.path.exists(self._data_folder):
            os.makedirs(self._data_folder)

        # Set up dedicated plugin log file
        self._log_file_path = os.path.join(self._data_folder, "mesh_repeatability.log")
        self._setup_file_logger()

        self._logger.info("=" * 70)
        self._logger.info(f"Mesh Repeatability v{self._plugin_version} initialized")
        self._logger.info(f"Data folder: {self._data_folder}")
        self._logger.info(f"Dedicated log file: {self._log_file_path}")
        self._logger.info("=" * 70)

        self._file_log("=" * 80)
        self._file_log("MESH REPEATABILITY PLUGIN STARTED")
        self._file_log("=" * 80)
        self._file_log(f"Version: {self._plugin_version}")
        self._file_log(f"Data folder: {self._data_folder}")
        self._file_log(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        self._file_log(f"Python process ID: {os.getpid()}")
        self._file_log("=" * 80)

    def _setup_file_logger(self):
        """Set up dedicated file logger with rotation."""
        try:
            self._file_logger = logging.getLogger("mesh_repeatability_dedicated")
            self._file_logger.setLevel(logging.DEBUG)
            self._file_logger.propagate = False

            # Remove and close existing handlers before reconfiguring.
            for handler in list(self._file_logger.handlers):
                self._file_logger.removeHandler(handler)
                try:
                    handler.close()
                except Exception:
                    pass

            # Create rotating file handler (max 5MB, keep 5 backups)
            handler = RotatingFileHandler(
                self._log_file_path,
                maxBytes=5 * 1024 * 1024,  # 5MB
                backupCount=5
            )
            handler.setLevel(logging.DEBUG)

            # Format: timestamp [LEVEL] message
            formatter = logging.Formatter(
                '%(asctime)s [%(levelname)-8s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            self._file_logger.addHandler(handler)

            self._logger.info(f"File logger initialized: {self._log_file_path}")
        except Exception as e:
            self._logger.error(f"Failed to set up file logger: {e}")

    def _file_log(self, message, level="INFO"):
        """Write to dedicated log file."""
        if self._file_logger:
            if level == "DEBUG":
                self._file_logger.debug(message)
            elif level == "INFO":
                self._file_logger.info(message)
            elif level == "WARNING":
                self._file_logger.warning(message)
            elif level == "ERROR":
                self._file_logger.error(message)
            else:
                self._file_logger.info(message)

    # -- Event Hook (Print Done / Failed / Cancelled) --
    def on_event(self, event, payload):
        payload = payload or {}

        # Log ALL events for debugging
        self._logger.debug(f"[EVENT] Received event: {event}")
        self._file_log(f"EVENT RECEIVED: {event}", "DEBUG")
        self._file_log(f"  Event payload: {payload}", "DEBUG")

        if event in (octoprint.events.Events.PRINT_DONE,
                     octoprint.events.Events.PRINT_FAILED,
                     octoprint.events.Events.PRINT_CANCELLED):
            filename = payload.get("name", "unknown")
            trigger_map = {
                octoprint.events.Events.PRINT_DONE: "print_done",
                octoprint.events.Events.PRINT_FAILED: "print_failed",
                octoprint.events.Events.PRINT_CANCELLED: "print_cancelled"
            }
            trigger = trigger_map.get(event, "unknown")

            self._logger.info("-" * 70)
            self._logger.info(f"[CAPTURE] {event}")
            self._logger.info(f"[CAPTURE] Filename: {filename}")
            self._logger.info(f"[CAPTURE] Trigger: {trigger}")
            self._logger.info(f"[CAPTURE] Current state: {self._capture_state}")
            self._logger.info(f"[CAPTURE] Queuing M420 V command...")
            self._logger.info("-" * 70)

            self._file_log("-" * 80)
            self._file_log(f"PRINT EVENT: {event}")
            self._file_log(f"  Filename: {filename}")
            self._file_log(f"  Trigger: {trigger}")
            self._file_log(f"  Current state: {self._capture_state}")
            self._file_log(f"  Will queue M420 V command...")
            self._file_log("-" * 80)

            self._start_capture(trigger=trigger, filename=filename)

    # -- Simple API --
    def get_api_commands(self):
        return dict(capture_now=[], export_csv=[], save_current_mesh=[])

    def on_api_command(self, command, data):
        self._logger.info(f"[API] Command received: {command}")
        self._file_log(f"API COMMAND: {command}", "INFO")
        self._file_log(f"  Data: {data}", "DEBUG")

        if command == "capture_now":
            self._logger.info("[API] Manual capture triggered by user button click")
            self._file_log("User clicked 'Capture Mesh Now' button", "INFO")
            self._file_log(f"  State before: {self._capture_state}", "DEBUG")
            self._start_capture(trigger="manual", filename=None)
            return octoprint.server.api.jsonify({"status": "capture_started", "message": "M420 V queued"})
        elif command == "save_current_mesh":
            self._logger.info("[API] 'Save Current Mesh' triggered - requesting M420 V from printer")
            self._file_log("User clicked 'Save Current Mesh' button", "INFO")
            self._file_log(f"  State before: {self._capture_state}", "DEBUG")
            # Same as manual capture, but with different UI label
            self._start_capture(trigger="manual_save", filename="current_mesh")
            return octoprint.server.api.jsonify({"status": "mesh_capture_started", "message": "Capturing current mesh from printer..."})
        elif command == "export_csv":
            history = self._load_history()
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["id", "timestamp", "trigger", "job_filename", "parse_status", "max_abs_delta", "mean_abs_delta"])
            for rec in history:
                stats = rec.get("stats_vs_previous") or {}
                max_d = stats.get("max_abs_delta", "N/A") if isinstance(stats, dict) else "N/A"
                mean_d = stats.get("mean_abs_delta", "N/A") if isinstance(stats, dict) else "N/A"
                writer.writerow([
                    rec.get("id", ""),
                    rec.get("timestamp", ""),
                    rec.get("trigger", ""),
                    rec.get("job_filename", ""),
                    rec.get("parse_status", ""),
                    max_d,
                    mean_d
                ])
            csv_content = output.getvalue()
            return octoprint.server.api.jsonify({
                "csv": csv_content,
                "filename": f"mesh_repeatability_history_{int(time.time())}.csv"
            })
        else:
            self._logger.warning(f"[API] Unknown command: {command}")
            import flask
            return flask.abort(400)

    def on_api_get(self, request):
        history = self._load_history()
        diagnostics = {
            "capture_state": self._capture_state,
            "total_captures": self._capture_count,
            "data_folder": self._data_folder,
            "last_capture_time": self._capture_timestamp,
            "history_count": len(history)
        }
        return octoprint.server.api.jsonify({
            "history": history,
            "diagnostics": diagnostics
        })

    # -- Capture Logic --
    def _start_capture(self, trigger, filename):
        self._logger.info(f"[CAPTURE_LOGIC] _start_capture() called")
        self._file_log("=" * 80)
        self._file_log("_START_CAPTURE() CALLED", "INFO")
        self._file_log(f"  Trigger: {trigger}", "INFO")
        self._file_log(f"  Filename: {filename}", "INFO")
        self._file_log(f"  Current state: {self._capture_state}", "DEBUG")

        if self._capture_state != "idle":
            self._logger.warning(f"[CAPTURE_LOGIC] Capture already in progress (state={self._capture_state}), ignoring request")
            self._file_log(f"  ⚠ Ignoring: capture already in progress (state={self._capture_state})", "WARNING")
            return

        self._current_trigger = trigger
        self._current_filename = filename
        self._capture_timestamp = time.time()
        self._file_log(f"  Capture timestamp: {self._capture_timestamp}", "DEBUG")
        self._file_log(f"  Timestamp (formatted): {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._capture_timestamp))}", "DEBUG")

        self._capture_state = "pending"
        self._capture_buffer = []

        self._logger.info(f"[CAPTURE_LOGIC] State changed to: pending")
        self._file_log("  State transition: idle/busy -> pending", "INFO")
        self._logger.info(f"[CAPTURE_LOGIC] Sending M420 V command to printer...")
        self._file_log("  Queuing M420 V command to printer...", "INFO")

        try:
            self._printer.commands(["M420 V"])
            self._logger.info(f"[CAPTURE_LOGIC] M420 V command queued successfully")
            self._file_log("  OK: M420 V command queued successfully", "INFO")
            self._file_log("  Waiting for serial response...", "DEBUG")
            self._file_log("=" * 80)
        except Exception as e:
            self._logger.error(f"[CAPTURE_LOGIC] ERROR: Failed to queue M420 V: {e}")
            self._file_log(f"  ERROR queuing M420 V: {e}", "ERROR")
            self._file_log(f"  Exception type: {type(e).__name__}", "DEBUG")
            self._capture_state = "idle"
            self._file_log(f"  State reset to idle due to error", "WARNING")
            self._file_log("=" * 80)

    def process_received_line(self, comm, line, *args, **kwargs):
        if self._capture_state == "idle":
            return line

        clean_line = line.replace("Recv:", "").strip()

        # Log all received lines when in pending or capturing state
        if self._capture_state in ("pending", "capturing"):
            self._logger.debug(f"[SERIAL] [{self._capture_state}] {line}")
            self._file_log(f"[{self._capture_state}] {line}", "DEBUG")

        if self._capture_state == "pending":
            if clean_line.startswith("Bilinear Leveling Grid:"):
                self._logger.info(f"[SERIAL] TRIGGER FOUND: 'Bilinear Leveling Grid:'")
                self._logger.info("[SERIAL] State changed: pending -> capturing")
                self._file_log("=" * 80, "INFO")
                self._file_log("OK: Trigger found: 'Bilinear Leveling Grid:'", "INFO")
                self._file_log("  Beginning to capture mesh data...", "INFO")
                self._file_log("  State transition: pending -> capturing", "INFO")
                self._capture_state = "capturing"
                self._capture_buffer.append(line)
                self._file_log(f"  Buffer has {len(self._capture_buffer)} line(s)", "DEBUG")
            return line

        if self._capture_state == "capturing":
            self._capture_buffer.append(line)
            self._file_log(f"  Buffered (total: {len(self._capture_buffer)} lines)", "DEBUG")

            if clean_line.startswith("ok"):
                self._logger.info(f"[SERIAL] END MARKER FOUND: 'ok'")
                self._logger.info(f"[SERIAL] Captured {len(self._capture_buffer)} lines total")
                self._logger.info("[SERIAL] State changed: capturing -> idle")
                self._file_log("=" * 80, "INFO")
                self._file_log("OK: End marker found: 'ok'", "INFO")
                self._file_log(f"  Total lines captured: {len(self._capture_buffer)}", "INFO")
                self._file_log(f"  Total bytes captured: {sum(len(l) for l in self._capture_buffer)}", "DEBUG")
                self._file_log("  State transition: capturing -> idle", "INFO")
                self._file_log("  Processing capture...", "DEBUG")
                self._file_log("=" * 80)
                self._finish_capture()
            return line

        return line

    def _finish_capture(self):
        self._logger.info("=" * 70)
        self._logger.info("[FINISH_CAPTURE] Processing captured data...")
        self._file_log("FINISH_CAPTURE: Processing captured data...", "INFO")

        raw_text = "\n".join(self._capture_buffer)
        self._capture_state = "idle"
        self._file_log(f"  Raw text length: {len(raw_text)} characters", "DEBUG")
        self._file_log(f"  Raw text line count: {len(self._capture_buffer)}", "DEBUG")
        self._file_log(f"  State set to: idle", "DEBUG")

        self._logger.info(f"[FINISH_CAPTURE] Raw text length: {len(raw_text)} characters")

        self._file_log("  Parsing M420 V output...", "DEBUG")
        parsed_mesh, status, error = self._parse_m420_output(raw_text)

        self._logger.info(f"[FINISH_CAPTURE] Parse status: {status}")
        self._file_log(f"  Parse result: {status}", "INFO")
        if error:
            self._logger.warning(f"[FINISH_CAPTURE] Parse error: {error}")
            self._file_log(f"  Parse error: {error}", "WARNING")
        if parsed_mesh:
            dims = f"{len(parsed_mesh)}x{len(parsed_mesh[0]) if parsed_mesh else 0}"
            self._logger.info(f"[FINISH_CAPTURE] Parsed mesh: {dims} grid")
            self._file_log(f"  Parsed mesh dimensions: {dims}", "INFO")
            self._file_log(f"  Sample values: {parsed_mesh[0] if parsed_mesh else 'N/A'}", "DEBUG")
            self._last_mesh = parsed_mesh  # Store for UI

        history = self._load_history()
        self._logger.info(f"[FINISH_CAPTURE] History records: {len(history)}")
        self._file_log(f"  History records found: {len(history)}", "DEBUG")

        previous_mesh = None
        for record in history:
            if record.get("parse_status") == "success" and record.get("parsed_mesh"):
                previous_mesh = record["parsed_mesh"]
                prev_trigger = record.get("trigger", "unknown")
                self._logger.info(f"[FINISH_CAPTURE] Found previous mesh from {prev_trigger}")
                self._file_log(f"  Found previous mesh from: {prev_trigger}", "DEBUG")
                break

        if not previous_mesh:
            self._file_log(f"  No valid previous mesh found (first capture or all previous failed)", "DEBUG")

        stats = None
        if parsed_mesh and previous_mesh:
            self._file_log("  Calculating delta statistics...", "DEBUG")
            stats = self._calculate_stats(parsed_mesh, previous_mesh)
            if stats:
                self._logger.info(f"[FINISH_CAPTURE] Delta stats: max={stats.get('max_abs_delta')}, mean={stats.get('mean_abs_delta')}")
                self._file_log(f"  ✓ Delta stats calculated", "INFO")
                self._file_log(f"    Max delta: {stats.get('max_abs_delta')}", "INFO")
                self._file_log(f"    Mean delta: {stats.get('mean_abs_delta')}", "INFO")
        if not stats:  # first capture or dimension mismatch
            self._logger.info(f"[FINISH_CAPTURE] No previous mesh for comparison")
            self._file_log(f"  No delta stats (N/A - first capture or dimension mismatch)", "INFO")
            stats = {
                "max_abs_delta": "N/A",
                "mean_abs_delta": "N/A",
                "delta_matrix": None
            }

        record_id = str(int(self._capture_timestamp * 1000))  # clean integer ID
        self._file_log(f"  Record ID: {record_id}", "DEBUG")
        self._file_log(f"  Trigger: {self._current_trigger}", "DEBUG")
        self._file_log(f"  Filename: {self._current_filename}", "DEBUG")

        data = {
            "id": record_id,
            "timestamp": self._capture_timestamp,
            "trigger": self._current_trigger,
            "job_filename": self._current_filename,
            "command_used": "M420 V",
            "raw_text": raw_text,
            "parsed_mesh": parsed_mesh,
            "parse_status": status,
            "parse_error": error,
            "stats_vs_previous": stats
        }

        filepath = os.path.join(self._data_folder, f"capture_{record_id}.json")
        self._capture_count += 1

        try:
            self._file_log(f"  Saving to: {filepath}", "DEBUG")
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            self._logger.info(f"[FINISH_CAPTURE] ✓ Saved to: {filepath}")
            self._file_log(f"  ✓ File saved successfully", "INFO")
            self._logger.info(f"[FINISH_CAPTURE] Total captures: {self._capture_count}")
            self._file_log(f"  Total captures (lifetime): {self._capture_count}", "INFO")
            self._file_log(f"  Running auto-prune...", "DEBUG")
            self._prune_old_records()
            self._file_log("=" * 80, "INFO")
            self._logger.info("=" * 70)
        except Exception as e:
            self._logger.error(f"[FINISH_CAPTURE] ✗ Failed to save: {e}")
            self._file_log(f"  ✗ ERROR saving file: {e}", "ERROR")
            self._file_log(f"    Exception type: {type(e).__name__}", "DEBUG")
            self._logger.info("=" * 70)
            self._file_log("=" * 80, "ERROR")

    def _prune_old_records(self):
        self._file_log("AUTO-PRUNE: Checking for old records...", "DEBUG")

        files = []
        for filename in os.listdir(self._data_folder):
            if filename.startswith("capture_") and filename.endswith(".json"):
                try:
                    id_part = filename.split("_", 1)[1].split(".")[0]
                    ts_int = int(id_part)
                    files.append((ts_int, filename))
                except Exception as e:
                    self._file_log(f"  Error parsing filename {filename}: {e}", "WARNING")
                    continue

        file_count = len(files)
        self._logger.debug(f"[PRUNE] Total files: {file_count}")
        self._file_log(f"  Total JSON files found: {file_count}", "DEBUG")

        if file_count > 50:
            files.sort()  # oldest first
            to_delete = file_count - 50
            self._file_log(f"  ⚠ Over limit! Will delete {to_delete} oldest file(s)", "WARNING")
            deleted = 0
            for ts, old_file in files[:-50]:
                try:
                    filepath = os.path.join(self._data_folder, old_file)
                    os.remove(filepath)
                    deleted += 1
                    old_date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts/1000))
                    self._file_log(f"    Deleted: {old_file} ({old_date})", "DEBUG")
                except Exception as e:
                    self._logger.warning(f"[PRUNE] Failed to delete {old_file}: {e}")
                    self._file_log(f"    ✗ Failed to delete {old_file}: {e}", "WARNING")
            self._logger.info(f"[PRUNE] Deleted {deleted} old records (keeping max 50, rotating buffer)")
            self._file_log(f"  ✓ Pruned {deleted} old record(s), keeping max 50", "INFO")
        else:
            self._file_log(f"  ✓ Under limit, no pruning needed", "DEBUG")

    # -- Parser & Math --
    def _parse_m420_output(self, raw_text):
        self._logger.debug("[PARSER] Starting parse of M420 V output")
        self._file_log("PARSE_M420_OUTPUT: Parsing bilinear leveling grid", "DEBUG")

        grid = []
        in_grid = False
        lines = raw_text.split('\n')
        self._logger.debug(f"[PARSER] Total lines: {len(lines)}")
        self._file_log(f"  Total input lines: {len(lines)}", "DEBUG")

        for line_num, line in enumerate(lines):
            clean_line = line.replace("Recv:", "").strip()

            if clean_line.startswith("Bilinear Leveling Grid:"):
                self._logger.debug(f"[PARSER] Found 'Bilinear Leveling Grid:' at line {line_num}")
                self._file_log(f"  Found 'Bilinear Leveling Grid:' at line {line_num}", "DEBUG")
                in_grid = True
                continue

            if in_grid:
                # Skip header line (0 1 2 3...)
                if re.match(r'^\s*0\s+1\s+2', clean_line):
                    self._logger.debug(f"[PARSER] Skipped header line at {line_num}")
                    self._file_log(f"  Skipped header line at {line_num}", "DEBUG")
                    continue

                parts = clean_line.split()

                # Try to parse as data row
                if len(parts) > 1 and parts[0].isdigit():
                    try:
                        row = [float(x) for x in parts[1:]]
                        grid.append(row)
                        self._logger.debug(f"[PARSER] Parsed row {line_num}: {len(row)} values")
                        self._file_log(f"  Line {line_num} → Row {len(grid)-1}: {len(row)} values", "DEBUG")
                    except ValueError as e:
                        self._logger.warning(f"[PARSER] ValueError parsing row {line_num}: {e}")
                        self._file_log(f"  ValueError at line {line_num}: {e}", "WARNING")
                        break
                # Stop on empty or non-grid line after data started
                elif len(grid) > 0:
                    self._logger.debug(f"[PARSER] End of grid at line {line_num}")
                    self._file_log(f"  End of grid detected at line {line_num}", "DEBUG")
                    break

        self._logger.debug(f"[PARSER] Total rows parsed: {len(grid)}")
        self._file_log(f"  Total rows parsed: {len(grid)}", "DEBUG")

        if len(grid) == 0:
            error_msg = "No grid data found or failed to parse."
            self._logger.warning(f"[PARSER] {error_msg}")
            self._file_log(f"  ✗ Parse failed: {error_msg}", "WARNING")
            return None, "failed", error_msg

        row_len = len(grid[0])
        self._logger.debug(f"[PARSER] Grid dimensions: {len(grid)} rows x {row_len} columns")
        self._file_log(f"  Grid dimensions: {len(grid)} rows x {row_len} columns", "DEBUG")

        # Validate all rows have same length
        for idx, r in enumerate(grid):
            if len(r) != row_len:
                error_msg = f"Inconsistent row lengths detected (row {idx} has {len(r)}, expected {row_len})"
                self._logger.warning(f"[PARSER] {error_msg}")
                self._file_log(f"  ✗ Validation failed: {error_msg}", "WARNING")
                return grid, "failed", error_msg

        self._logger.info(f"[PARSER] ✓ Successfully parsed {len(grid)}x{row_len} mesh grid")
        self._file_log(f"  ✓ Successfully parsed {len(grid)}x{row_len} mesh grid", "INFO")
        self._file_log(f"    Sample row 0: {grid[0]}", "DEBUG")
        return grid, "success", None

    def _calculate_stats(self, current_mesh, prev_mesh):
        if len(current_mesh) != len(prev_mesh) or len(current_mesh[0]) != len(prev_mesh[0]):
            return None
        delta_matrix = []
        max_delta = 0.0
        sum_delta = 0.0
        count = 0
        for r in range(len(current_mesh)):
            row_deltas = []
            for c in range(len(current_mesh[r])):
                diff = round(current_mesh[r][c] - prev_mesh[r][c], 4)
                row_deltas.append(diff)
                abs_diff = abs(diff)
                if abs_diff > max_delta:
                    max_delta = abs_diff
                sum_delta += abs_diff
                count += 1
            delta_matrix.append(row_deltas)
        mean_delta = round(sum_delta / count, 4) if count > 0 else 0
        return {
            "max_abs_delta": round(max_delta, 4),
            "mean_abs_delta": mean_delta,
            "delta_matrix": delta_matrix
        }

    def _load_history(self):
        records = []
        if not os.path.exists(self._data_folder):
            self._logger.warning(f"[HISTORY] Data folder does not exist: {self._data_folder}")
            self._file_log(f"LOAD_HISTORY: Data folder does not exist!", "WARNING")
            return records

        self._file_log("LOAD_HISTORY: Loading all capture records...", "DEBUG")

        json_files = [f for f in os.listdir(self._data_folder)
                     if f.startswith("capture_") and f.endswith(".json")]
        self._file_log(f"  JSON files found: {len(json_files)}", "DEBUG")

        for filename in json_files:
            try:
                filepath = os.path.join(self._data_folder, filename)
                with open(filepath, "r") as f:
                    data = json.load(f)
                    records.append(data)
                    self._file_log(f"  ✓ Loaded: {filename}", "DEBUG")
            except Exception as e:
                self._logger.error(f"[HISTORY] Error loading {filename}: {e}")
                self._file_log(f"  ✗ Error loading {filename}: {e}", "ERROR")

        self._logger.debug(f"[HISTORY] Loaded {len(records)} records")
        self._file_log(f"  Total records loaded: {len(records)}", "DEBUG")

        records.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        self._file_log(f"  Records sorted by timestamp (newest first)", "DEBUG")
        return records

    # -- UI Mixins --
    def get_template_configs(self):
        return [dict(type="tab", name="Mesh Repeatability", custom_bindings=True)]

    def get_assets(self):
        return dict(js=["js/mesh_repeatability.js"])

    # -- Software Update Hook --
    def get_update_information(self):
        return dict(
            mesh_repeatability=dict(
                displayName="Mesh Repeatability",
                displayVersion=self._plugin_version,
                type="github_release",
                user="jperry004",
                repo="OctoPrint-MeshRepeatability",
                current=self._plugin_version,
                pip="https://github.com/jperry004/OctoPrint-MeshRepeatability/archive/{target_version}.zip",
            )
        )

__plugin_name__ = "Mesh Repeatability"
__plugin_version__ = "0.2.1"
__plugin_pythoncompat__ = ">=3.7,<4"

def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = MeshRepeatabilityPlugin()
    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.comm.protocol.gcode.received": __plugin_implementation__.process_received_line,
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
