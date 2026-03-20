import octoprint.plugin
import octoprint.events
import os
import time
import json
import re
import csv
import io

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

    def on_after_startup(self):
        self._data_folder = self.get_plugin_data_folder()
        if not os.path.exists(self._data_folder):
            os.makedirs(self._data_folder)
        self._logger.info("Mesh Repeatability MVP v0.2.0 initialized (with pruning + CSV export).")

    # -- Event Hook (Print Done / Failed / Cancelled) --
    def on_event(self, event, payload):
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
            self._logger.info(f"{event} ({filename}). Triggering mesh capture.")
            self._start_capture(trigger=trigger, filename=filename)

    # -- Simple API --
    def get_api_commands(self):
        return dict(capture_now=[], export_csv=[])

    def on_api_command(self, command, data):
        if command == "capture_now":
            self._start_capture(trigger="manual", filename=None)
            return octoprint.server.api.jsonify({"status": "capture_started"})
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

    def on_api_get(self, request):
        history = self._load_history()
        return octoprint.server.api.jsonify({"history": history})

    # -- Capture Logic --
    def _start_capture(self, trigger, filename):
        self._current_trigger = trigger
        self._current_filename = filename
        self._capture_timestamp = time.time()
        self._capture_state = "pending"
        self._capture_buffer = []
        self._printer.commands(["M420 V"])

    def process_received_line(self, comm, line, *args, **kwargs):
        if self._capture_state == "idle":
            return line

        clean_line = line.replace("Recv:", "").strip()

        if self._capture_state == "pending":
            if clean_line.startswith("Bilinear Leveling Grid:"):
                self._capture_state = "capturing"
                self._capture_buffer.append(line)
            return line

        if self._capture_state == "capturing":
            self._capture_buffer.append(line)
            if clean_line.startswith("ok"):
                self._finish_capture()
            return line

        return line

    def _finish_capture(self):
        raw_text = "\n".join(self._capture_buffer)
        self._capture_state = "idle"

        parsed_mesh, status, error = self._parse_m420_output(raw_text)

        history = self._load_history()
        previous_mesh = None
        for record in history:
            if record.get("parse_status") == "success" and record.get("parsed_mesh"):
                previous_mesh = record["parsed_mesh"]
                break

        stats = None
        if parsed_mesh and previous_mesh:
            stats = self._calculate_stats(parsed_mesh, previous_mesh)
        if not stats:  # first capture or dimension mismatch
            stats = {
                "max_abs_delta": "N/A",
                "mean_abs_delta": "N/A",
                "delta_matrix": None
            }

        record_id = str(int(self._capture_timestamp * 1000))  # clean integer ID
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
        try:
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            self._prune_old_records()
        except Exception as e:
            self._logger.error(f"Failed to save mesh record: {e}")

    def _prune_old_records(self):
        files = []
        for filename in os.listdir(self._data_folder):
            if filename.startswith("capture_") and filename.endswith(".json"):
                try:
                    id_part = filename.split("_", 1)[1].split(".")[0]
                    ts_int = int(id_part)
                    files.append((ts_int, filename))
                except:
                    continue
        if len(files) > 50:
            files.sort()  # oldest first
            for _, old_file in files[:-50]:
                try:
                    os.remove(os.path.join(self._data_folder, old_file))
                except:
                    pass
            self._logger.info(f"Pruned mesh history to 50 records (rotating buffer).")

    # -- Parser & Math --
    def _parse_m420_output(self, raw_text):
        grid = []
        in_grid = False
        lines = raw_text.split('\n')
        for line in lines:
            clean_line = line.replace("Recv:", "").strip()
            if clean_line.startswith("Bilinear Leveling Grid:"):
                in_grid = True
                continue
            if in_grid:
                if re.match(r'^\s*0\s+1\s+2', clean_line):
                    continue
                parts = clean_line.split()
                if len(parts) > 1 and parts[0].isdigit():
                    try:
                        row = [float(x) for x in parts[1:]]
                        grid.append(row)
                    except ValueError:
                        break
                elif len(grid) > 0:
                    break
        if len(grid) == 0:
            return None, "failed", "No grid data found or failed to parse."
        row_len = len(grid[0])
        for r in grid:
            if len(r) != row_len:
                return grid, "failed", "Inconsistent row lengths detected."
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
            "max_abs_delta": max_delta,
            "mean_abs_delta": mean_delta,
            "delta_matrix": delta_matrix
        }

    def _load_history(self):
        records = []
        if not os.path.exists(self._data_folder):
            return records
        for filename in os.listdir(self._data_folder):
            if filename.startswith("capture_") and filename.endswith(".json"):
                try:
                    with open(os.path.join(self._data_folder, filename), "r") as f:
                        records.append(json.load(f))
                except Exception as e:
                    self._logger.error(f"Error loading {filename}: {e}")
        records.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return records

    # -- UI Mixins --
    def get_template_configs(self):
        return [dict(type="tab", name="Mesh Repeatability", custom_bindings=True)]

    def get_assets(self):
        return dict(js=["js/mesh_repeatability.js"])

__plugin_name__ = "Mesh Repeatability MVP"
__plugin_pythoncompat__ = ">=3.7,<4"

def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = MeshRepeatabilityPlugin()
    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.comm.protocol.gcode.received": __plugin_implementation__.process_received_line
    }
