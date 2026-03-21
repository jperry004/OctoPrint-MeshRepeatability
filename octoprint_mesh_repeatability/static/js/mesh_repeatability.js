$(function () {
    function MeshRepeatabilityViewModel(parameters) {
        var self = this;
        var PLUGIN_ID = "mesh_repeatability";
        var rootSelector = "#tab_plugin_mesh_repeatability";

        self.history = [];
        self.selectedRecord = null;
        self.isCapturing = false;

        // ── Formatting helpers ────────────────────────────────────────

        self.formatMatrix = function (matrix) {
            if (!matrix || !matrix.length) return "No data";
            return matrix
                .map(function (row) {
                    return row
                        .map(function (val) {
                            return Number(val).toFixed(3).padStart(8, " ");
                        })
                        .join(" ");
                })
                .join("\n");
        };

        // ── UI rendering ─────────────────────────────────────────────

        self.setUiStatus = function (message) {
            $("#mesh_repeatability_ui_status span").text(message);
        };

        self.renderDiagnostics = function (diagnostics) {
            var box = $("#mesh_repeatability_backend_status");
            if (!diagnostics) {
                box.hide();
                return;
            }
            box.find("span").text(
                "State: " + diagnostics.capture_state +
                " | Captures: " + diagnostics.total_captures +
                " | History: " + diagnostics.history_count
            );
            box.show();
        };

        self.renderDetails = function (record) {
            var emptyState = $("#mesh_repeatability_empty_state");
            var details = $("#mesh_repeatability_details");

            if (!record) {
                emptyState.show();
                details.hide();
                return;
            }

            emptyState.hide();
            details.show();

            $("#mesh_repeatability_detail_timestamp").text(
                new Date(record.timestamp * 1000).toLocaleString()
            );
            $("#mesh_repeatability_detail_status").text(record.parse_status || "");

            if (record.parse_error) {
                $("#mesh_repeatability_detail_error").text(record.parse_error).show();
            } else {
                $("#mesh_repeatability_detail_error").hide().text("");
            }

            var stats = record.stats_vs_previous || {};
            if (stats.max_abs_delta !== undefined && stats.max_abs_delta !== "N/A") {
                $("#mesh_repeatability_stats_box").show();
                $("#mesh_repeatability_stats_na").hide();
                $("#mesh_repeatability_detail_max_delta").text(stats.max_abs_delta);
                $("#mesh_repeatability_detail_mean_delta").text(stats.mean_abs_delta);
            } else {
                $("#mesh_repeatability_stats_box").hide();
                $("#mesh_repeatability_stats_na").show();
            }

            $("#mesh_repeatability_detail_delta").text(self.formatMatrix(stats.delta_matrix));
            $("#mesh_repeatability_detail_mesh").text(self.formatMatrix(record.parsed_mesh));
            $("#mesh_repeatability_detail_raw").text(record.raw_text || "");
        };

        self.renderHistory = function () {
            var list = $("#mesh_repeatability_history");
            list.empty();

            if (!self.history.length) {
                self.renderDetails(null);
                return;
            }

            self.history.forEach(function (record) {
                var item = $("<li>");
                if (self.selectedRecord && self.selectedRecord.id === record.id) {
                    item.addClass("active");
                }

                var link = $("<a href='#'></a>");
                link.append($("<span>").text(new Date(record.timestamp * 1000).toLocaleString()));
                link.append("<br>");
                link.append($("<small class='muted'>").text("Trigger: " + record.trigger));
                link.on("click", function (e) {
                    e.preventDefault();
                    self.selectedRecord = record;
                    self.renderHistory();
                    self.renderDetails(record);
                });

                item.append(link);
                list.append(item);
            });

            self.renderDetails(self.selectedRecord || self.history[0]);
        };

        self.updateActionButtons = function () {
            var capturing = self.isCapturing;
            $("#mesh_repeatability_capture_now").prop("disabled", capturing);
            $("#mesh_repeatability_save_current").prop("disabled", capturing);
            $("#mesh_repeatability_refresh_history").prop("disabled", capturing);
            $("#mesh_repeatability_export_csv").prop("disabled", capturing);
            $("#mesh_repeatability_capture_now_label").text(
                capturing ? "Capturing\u2026" : "Capture Mesh Now"
            );
        };

        // ── Data fetching ─────────────────────────────────────────────

        self.fetchHistory = function () {
            self.setUiStatus("Loading history\u2026");
            OctoPrint.simpleApiGet(PLUGIN_ID)
                .done(function (response) {
                    var previousId = self.selectedRecord ? self.selectedRecord.id : null;
                    self.history = response.history || [];

                    self.selectedRecord = null;
                    if (previousId) {
                        self.history.forEach(function (record) {
                            if (record.id === previousId) self.selectedRecord = record;
                        });
                    }
                    if (!self.selectedRecord && self.history.length) {
                        self.selectedRecord = self.history[0];
                    }

                    self.renderDiagnostics(response.diagnostics);
                    self.renderHistory();
                    self.setUiStatus("Ready");
                })
                .fail(function (xhr) {
                    console.error("[MeshRepeat] fetchHistory failed:", xhr.status);
                    self.setUiStatus("Failed to load history");
                });
        };

        // ── Commands ──────────────────────────────────────────────────

        self.runCommand = function (command, pendingMessage, failMessage) {
            self.isCapturing = true;
            self.updateActionButtons();
            self.setUiStatus(pendingMessage);

            OctoPrint.simpleApiCommand(PLUGIN_ID, command, {})
                .done(function (response) {
                    console.log("[MeshRepeat] command OK:", command, response);
                    new PNotify({
                        title: "Mesh Repeatability",
                        text: pendingMessage,
                        type: "info",
                        hide: true,
                        delay: 3000,
                    });
                    // Don't blindly wait - the websocket handler will refresh
                    // when capture_complete arrives.  But set a safety fallback
                    // in case the message is missed.
                    self._fallbackTimer = window.setTimeout(function () {
                        if (self.isCapturing) {
                            self.isCapturing = false;
                            self.updateActionButtons();
                            self.fetchHistory();
                        }
                    }, 35000); // slightly longer than server-side timeout
                })
                .fail(function (xhr) {
                    console.error("[MeshRepeat] command failed:", command, xhr.status);
                    new PNotify({
                        title: "Mesh Repeatability",
                        text: failMessage + " (HTTP " + xhr.status + ")",
                        type: "error",
                        hide: true,
                        delay: 5000,
                    });
                    self.isCapturing = false;
                    self.updateActionButtons();
                    self.setUiStatus(failMessage);
                });
        };

        self.exportCsv = function () {
            self.setUiStatus("Exporting CSV\u2026");
            OctoPrint.simpleApiCommand(PLUGIN_ID, "export_csv", {})
                .done(function (response) {
                    if (response && response.csv) {
                        var blob = new Blob([response.csv], { type: "text/csv;charset=utf-8" });
                        var url = URL.createObjectURL(blob);
                        var a = document.createElement("a");
                        a.href = url;
                        a.download = response.filename || "mesh_history.csv";
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        URL.revokeObjectURL(url);
                        self.setUiStatus("CSV exported");
                    }
                })
                .fail(function (xhr) {
                    console.error("[MeshRepeat] CSV export failed:", xhr.status);
                    self.setUiStatus("CSV export failed");
                });
        };

        // ── Event handlers ────────────────────────────────────────────

        self.attachHandlers = function () {
            $(rootSelector).off("click.meshrepeat");

            $(rootSelector).on("click.meshrepeat", "#mesh_repeatability_capture_now", function (e) {
                e.preventDefault();
                self.runCommand("capture_now", "Capturing mesh from printer\u2026", "Failed to start capture");
            });
            $(rootSelector).on("click.meshrepeat", "#mesh_repeatability_save_current", function (e) {
                e.preventDefault();
                self.runCommand("save_current_mesh", "Capturing current mesh\u2026", "Failed to save mesh");
            });
            $(rootSelector).on("click.meshrepeat", "#mesh_repeatability_refresh_history", function (e) {
                e.preventDefault();
                self.fetchHistory();
            });
            $(rootSelector).on("click.meshrepeat", "#mesh_repeatability_export_csv", function (e) {
                e.preventDefault();
                self.exportCsv();
            });

            self.updateActionButtons();
        };

        // ── OctoPrint ViewModel lifecycle ─────────────────────────────

        self.onAfterBinding = function () {
            self.attachHandlers();
            self.fetchHistory();
        };

        self.onDataUpdaterPluginMessage = function (plugin, data) {
            if (plugin !== PLUGIN_ID || !data || !data.type) return;

            if (data.type === "capture_complete") {
                // Clear any fallback timer
                if (self._fallbackTimer) {
                    window.clearTimeout(self._fallbackTimer);
                    self._fallbackTimer = null;
                }

                self.isCapturing = false;
                self.updateActionButtons();
                self.fetchHistory();

                var record = data.record;
                if (record && record.parse_status === "success") {
                    new PNotify({
                        title: "Mesh Repeatability",
                        text: "Mesh captured successfully.",
                        type: "success",
                        hide: true,
                        delay: 3000,
                    });
                } else {
                    new PNotify({
                        title: "Mesh Repeatability",
                        text: "Capture finished but parsing failed.",
                        type: "warning",
                        hide: true,
                        delay: 5000,
                    });
                }
            }

            if (data.type === "capture_timeout") {
                if (self._fallbackTimer) {
                    window.clearTimeout(self._fallbackTimer);
                    self._fallbackTimer = null;
                }

                self.isCapturing = false;
                self.updateActionButtons();
                self.setUiStatus("Capture timed out");

                new PNotify({
                    title: "Mesh Repeatability",
                    text: data.message || "Capture timed out.",
                    type: "error",
                    hide: true,
                    delay: 5000,
                });
            }
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: MeshRepeatabilityViewModel,
        elements: ["#tab_plugin_mesh_repeatability"],
    });
});
