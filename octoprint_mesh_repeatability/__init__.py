import octoprint.plugin
import octoprint.events
import os
import time
import json
import re
import csv
import io
import threading


CAPTURE_TIMEOUT_SECONDS = 30
MAX_HISTORY_RECORDS = 50


class MeshRepeatabilityPlugin(
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.SimpleApiPlugin,
    octoprint.plugin.EventHandlerPlugin,
):
    def __init__(self):
        self._capture_state = "idle"
        self._capture_buffer = []
        self._current_trigger = None
        self._current_filename = None
        self._capture_timestamp = None
        self._capture_count = 0
        self._timeout_timer = None

    # ── Lifecycle ──────────────────────────────────────────────────────

    def on_after_startup(self):
        self._data_folder = self.get_plugin_data_folder()
        os.makedirs(self._data_folder, exist_ok=True)
        self._logger.info(
            "Mesh Repeatability v%s started  (data: %s)",
            self._plugin_version,
            self._data_folder,
        )

    # ── Events ─────────────────────────────────────────────────────────

    def on_event(self, event, payload):
        if event not in (
            octoprint.events.Events.PRINT_DONE,
            octoprint.events.Events.PRINT_FAILED,
            octoprint.events.Events.PRINT_CANCELLED,
        ):
            return

        payload = payload or {}
        trigger_map = {
            octoprint.events.Events.PRINT_DONE: "print_done",
            octoprint.events.Events.PRINT_FAILED: "print_failed",
            octoprint.events.Events.PRINT_CANCELLED: "print_cancelled",
        }
        trigger = trigger_map.get(event, "unknown")
        filename = payload.get("name", "unknown")
        self._logger.info("Print event %s — starting mesh capture", trigger)
        self._start_capture(trigger=trigger, filename=filename)

    # ── Simple API ─────────────────────────────────────────────────────

    def get_api_commands(self):
        return dict(capture_now=[], export_csv=[], save_current_mesh=[])

    def on_api_command(self, command, data):
        if command == "capture_now":
            self._logger.info("Manual capture requested")
            self._start_capture(trigger="manual", filename=None)
            return octoprint.server.api.jsonify(
                {"status": "capture_started", "message": "M420 V queued"}
            )

        if command == "save_current_mesh":
            self._logger.info("Save-current-mesh requested")
            self._start_capture(trigger="manual_save", filename="current_mesh")
            return octoprint.server.api.jsonify(
                {"status": "capture_started", "message": "Capturing current mesh…"}
            )

        if command == "export_csv":
            return self._handle_export_csv()

        from flask import abort
        abort(400)

    def on_api_get(self, request):
        history = self._load_history()
        diagnostics = {
            "capture_state": self._capture_state,
            "total_captures": self._capture_count,
            "history_count": len(history),
        }
        return octoprint.server.api.jsonify(
            {"history": history, "diagnostics": diagnostics}
        )

    # ── Capture logic ──────────────────────────────────────────────────

    def _start_capture(self, trigger, filename):
        if self._capture_state != "idle":
            self._logger.warning(
                "Capture already in progress (state=%s), ignoring", self._capture_state
            )
            return

        self._current_trigger = trigger
        self._current_filename = filename
        self._capture_timestamp = time.time()
        self._capture_state = "pending"
        self._capture_buffer = []

        self._logger.info("Sending M420 V  (trigger=%s)", trigger)
        try:
            self._printer.commands(["M420 V"])
        except Exception as e:
            self._logger.error("Failed to send M420 V: %s", e)
            self._reset_capture()
            return

        self._start_timeout()

    def _start_timeout(self):
        """Reset state if the printer doesn't respond in time."""
        self._cancel_timeout()
        self._timeout_timer = threading.Timer(
            CAPTURE_TIMEOUT_SECONDS, self._on_capture_timeout
        )
        self._timeout_timer.daemon = True
        self._timeout_timer.start()

    def _cancel_timeout(self):
        if self._timeout_timer is not None:
            self._timeout_timer.cancel()
            self._timeout_timer = None

    def _on_capture_timeout(self):
        if self._capture_state in ("pending", "capturing"):
            self._logger.warning(
                "Capture timed out after %ds (state was %s)",
                CAPTURE_TIMEOUT_SECONDS,
                self._capture_state,
            )
            self._reset_capture()
            self._send_ui_message("capture_timeout", {
                "message": "Capture timed out — printer did not respond in time."
            })

    def _reset_capture(self):
        self._capture_state = "idle"
        self._capture_buffer = []
        self._cancel_timeout()

    # ── Serial hook ────────────────────────────────────────────────────

    def process_received_line(self, comm, line, *args, **kwargs):
        if self._capture_state == "idle":
            return line

        clean = line.replace("Recv:", "").strip()

        if self._capture_state == "pending":
            if clean.startswith("Bilinear Leveling Grid:"):
                self._logger.debug("Grid header detected — capturing")
                self._capture_state = "capturing"
                self._capture_buffer.append(line)
            return line

        if self._capture_state == "capturing":
            self._capture_buffer.append(line)
            if clean.startswith("ok"):
                self._logger.debug(
                    "End marker received — %d lines captured", len(self._capture_buffer)
                )
                self._finish_capture()
            return line

        return line

    # ── Finish & persist ───────────────────────────────────────────────

    def _finish_capture(self):
        self._cancel_timeout()
        raw_text = "\n".join(self._capture_buffer)
        self._capture_state = "idle"

        parsed_mesh, status, error = self._parse_m420_output(raw_text)
        if error:
            self._logger.warning("Parse error: %s", error)

        history = self._load_history()
        previous_mesh = None
        for record in history:
            if record.get("parse_status") == "success" and record.get("parsed_mesh"):
                previous_mesh = record["parsed_mesh"]
                break

        stats = None
        if parsed_mesh and previous_mesh:
            stats = self._calculate_stats(parsed_mesh, previous_mesh)

        if stats is None:
            stats = {"max_abs_delta": "N/A", "mean_abs_delta": "N/A", "delta_matrix": None}

        record_id = str(int(self._capture_timestamp * 1000))

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
            "stats_vs_previous": stats,
        }

        filepath = os.path.join(self._data_folder, f"capture_{record_id}.json")
        try:
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            self._capture_count += 1
            self._logger.info(
                "Capture #%d saved  (status=%s, file=%s)",
                self._capture_count,
                status,
                filepath,
            )
            self._prune_old_records()
        except Exception as e:
            self._logger.error("Failed to save capture: %s", e)

        # Push real-time update to UI
        self._send_ui_message("capture_complete", {
            "record": data,
            "capture_count": self._capture_count,
        })

    def _send_ui_message(self, event_type, payload):
        """Push a message to the frontend via OctoPrint's plugin messaging."""
        try:
            self._plugin_manager.send_plugin_message(
                self._identifier, {"type": event_type, **payload}
            )
        except Exception as e:
            self._logger.error("Failed to send UI message: %s", e)

    # ── Pruning ────────────────────────────────────────────────────────

    def _prune_old_records(self):
        files = []
        for fname in os.listdir(self._data_folder):
            if fname.startswith("capture_") and fname.endswith(".json"):
                try:
                    ts = int(fname.split("_", 1)[1].split(".")[0])
                    files.append((ts, fname))
                except (ValueError, IndexError):
                    continue

        if len(files) <= MAX_HISTORY_RECORDS:
            return

        files.sort()
        to_delete = files[: len(files) - MAX_HISTORY_RECORDS]
        deleted = 0
        for _ts, old_file in to_delete:
            try:
                os.remove(os.path.join(self._data_folder, old_file))
                deleted += 1
            except OSError as e:
                self._logger.warning("Failed to prune %s: %s", old_file, e)

        if deleted:
            self._logger.info("Pruned %d old capture(s)", deleted)

    # ── Parser ─────────────────────────────────────────────────────────

    def _parse_m420_output(self, raw_text):
        grid = []
        in_grid = False

        for line in raw_text.split("\n"):
            clean = line.replace("Recv:", "").strip()

            if clean.startswith("Bilinear Leveling Grid:"):
                in_grid = True
                continue

            if not in_grid:
                continue

            if clean == "":
                continue

            # Column header row (0  1  2  3 …)
            if re.match(r"^\s*0\s+1\s+2", clean):
                continue

            # End markers
            if (
                clean.startswith("Subdivided with")
                or clean.startswith("echo:")
                or clean.startswith("ok")
            ):
                break

            parts = clean.split()
            if len(parts) > 1 and parts[0].isdigit():
                try:
                    row = [float(x) for x in parts[1:]]
                    grid.append(row)
                except ValueError:
                    break
            elif grid:
                # Non-data line after we already have rows → end of grid
                break

        if not grid:
            return None, "failed", "No grid data found in M420 V output."

        expected_cols = len(grid[0])
        for idx, row in enumerate(grid):
            if len(row) != expected_cols:
                return (
                    grid,
                    "failed",
                    f"Row {idx} has {len(row)} columns, expected {expected_cols}.",
                )

        return grid, "success", None

    # ── Stats ──────────────────────────────────────────────────────────

    def _calculate_stats(self, current_mesh, prev_mesh):
        if len(current_mesh) != len(prev_mesh):
            return None
        if len(current_mesh[0]) != len(prev_mesh[0]):
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

        mean_delta = round(sum_delta / count, 4) if count > 0 else 0.0

        return {
            "max_abs_delta": round(max_delta, 4),
            "mean_abs_delta": mean_delta,
            "delta_matrix": delta_matrix,
        }

    # ── History I/O ────────────────────────────────────────────────────

    def _load_history(self):
        if not os.path.exists(self._data_folder):
            return []

        records = []
        for fname in os.listdir(self._data_folder):
            if not (fname.startswith("capture_") and fname.endswith(".json")):
                continue
            try:
                with open(os.path.join(self._data_folder, fname), "r") as f:
                    records.append(json.load(f))
            except Exception as e:
                self._logger.error("Error loading %s: %s", fname, e)

        records.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return records

    def _handle_export_csv(self):
        history = self._load_history()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "id", "timestamp", "trigger", "job_filename",
            "parse_status", "max_abs_delta", "mean_abs_delta",
        ])
        for rec in history:
            stats = rec.get("stats_vs_previous") or {}
            writer.writerow([
                rec.get("id", ""),
                rec.get("timestamp", ""),
                rec.get("trigger", ""),
                rec.get("job_filename", ""),
                rec.get("parse_status", ""),
                stats.get("max_abs_delta", "N/A") if isinstance(stats, dict) else "N/A",
                stats.get("mean_abs_delta", "N/A") if isinstance(stats, dict) else "N/A",
            ])
        return octoprint.server.api.jsonify({
            "csv": output.getvalue(),
            "filename": f"mesh_repeatability_history_{int(time.time())}.csv",
        })

    # ── UI mixins ──────────────────────────────────────────────────────

    def get_template_configs(self):
        return [dict(type="tab", name="Mesh Repeatability")]

    def get_assets(self):
        return dict(js=["js/mesh_repeatability.js"])

    # ── Software Update ────────────────────────────────────────────────

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
__plugin_version__ = "0.3.0"
__plugin_pythoncompat__ = ">=3.7,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = MeshRepeatabilityPlugin()
    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.comm.protocol.gcode.received": __plugin_implementation__.process_received_line,
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
    }
