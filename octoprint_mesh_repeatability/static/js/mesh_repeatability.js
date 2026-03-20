$(function() {
    function MeshRepeatabilityViewModel(parameters) {
        var self = this;
        var PLUGIN_ID = "mesh_repeatability";
        var rootSelector = "#tab_plugin_mesh_repeatability";

        self.history = [];
        self.selectedRecord = null;
        self.isCapturing = false;

        self.formatMatrix = function(matrix) {
            if (!matrix || !matrix.length) {
                return "No data";
            }

            return matrix.map(function(row) {
                return row.map(function(val) {
                    return Number(val).toFixed(3).padStart(8, " ");
                }).join(" ");
            }).join("\n");
        };

        self.setUiStatus = function(message) {
            $("#mesh_repeatability_ui_status span").text(message);
        };

        self.renderDiagnostics = function(diagnostics) {
            var statusBox = $("#mesh_repeatability_backend_status");

            if (!diagnostics) {
                statusBox.hide();
                return;
            }

            statusBox.find("span").text(
                "State: " + diagnostics.capture_state +
                " | Total Captures: " + diagnostics.total_captures +
                " | History: " + diagnostics.history_count + " records"
            );
            statusBox.show();
        };

        self.renderBindingDiagnostics = function() {
            var rootCount = $(rootSelector).length;
            var buttonCount = $(rootSelector).find("button").length;
            var bindingBox = $("#mesh_repeatability_binding_status");

            bindingBox.find("span").text(
                "Roots: " + rootCount +
                " | Buttons: " + buttonCount +
                " | Handlers: attached"
            );
            bindingBox.show();
        };

        self.renderDetails = function(record) {
            var emptyState = $("#mesh_repeatability_empty_state");
            var details = $("#mesh_repeatability_details");

            if (!record) {
                emptyState.show();
                details.hide();
                return;
            }

            emptyState.hide();
            details.show();

            $("#mesh_repeatability_detail_timestamp").text(new Date(record.timestamp * 1000).toLocaleString());
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

        self.renderHistory = function() {
            var list = $("#mesh_repeatability_history");
            list.empty();

            if (!self.history.length) {
                self.renderDetails(null);
                return;
            }

            self.history.forEach(function(record) {
                var item = $("<li>");
                if (self.selectedRecord && self.selectedRecord.id === record.id) {
                    item.addClass("active");
                }

                var link = $("<a href='#'></a>");
                link.append($("<span>").text(new Date(record.timestamp * 1000).toLocaleString()));
                link.append("<br>");
                link.append($("<small class='muted'>").text("Trigger: " + record.trigger));
                link.on("click", function(e) {
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

        self.updateActionButtons = function() {
            $("#mesh_repeatability_capture_now").prop("disabled", self.isCapturing);
            $("#mesh_repeatability_save_current").prop("disabled", self.isCapturing);
            $("#mesh_repeatability_refresh_history").prop("disabled", self.isCapturing);
            $("#mesh_repeatability_export_csv").prop("disabled", self.isCapturing);
            $("#mesh_repeatability_capture_now_label").text(self.isCapturing ? "Capturing..." : "Capture Mesh Now");
        };

        self.fetchHistory = function() {
            self.setUiStatus("Loading history...");
            OctoPrint.simpleApiGet(PLUGIN_ID)
                .done(function(response) {
                    var previousId = self.selectedRecord ? self.selectedRecord.id : null;
                    self.history = response.history || [];

                    if (previousId) {
                        self.selectedRecord = null;
                        self.history.forEach(function(record) {
                            if (record.id === previousId) {
                                self.selectedRecord = record;
                            }
                        });
                    }

                    if (!self.selectedRecord && self.history.length) {
                        self.selectedRecord = self.history[0];
                    }

                    self.renderDiagnostics(response.diagnostics);
                    self.renderHistory();
                    self.setUiStatus("Ready");
                })
                .fail(function(xhr) {
                    console.error("[MeshRepeat] fetchHistory FAILED:", xhr.status, xhr.responseText);
                    self.setUiStatus("History request failed");
                });
        };

        self.runCommand = function(command, successMessage, failureMessage) {
            self.isCapturing = true;
            self.updateActionButtons();
            self.setUiStatus(successMessage);

            OctoPrint.simpleApiCommand(PLUGIN_ID, command, {})
                .done(function(response) {
                    console.log("[MeshRepeat] command OK:", command, response);
                    new PNotify({
                        title: "Mesh Repeatability",
                        text: successMessage,
                        type: "info",
                        hide: true,
                        delay: 3000
                    });

                    window.setTimeout(function() {
                        self.isCapturing = false;
                        self.updateActionButtons();
                        self.fetchHistory();
                    }, 3000);
                })
                .fail(function(xhr) {
                    console.error("[MeshRepeat] command FAILED:", command, xhr.status, xhr.responseText);
                    new PNotify({
                        title: "Mesh Repeatability",
                        text: failureMessage + " (HTTP " + xhr.status + ")",
                        type: "error",
                        hide: true,
                        delay: 5000
                    });
                    self.isCapturing = false;
                    self.updateActionButtons();
                    self.setUiStatus(failureMessage);
                });
        };

        self.exportCsv = function() {
            self.setUiStatus("Exporting CSV...");
            OctoPrint.simpleApiCommand(PLUGIN_ID, "export_csv", {})
                .done(function(response) {
                    if (response && response.csv) {
                        var blob = new Blob([response.csv], { type: "text/csv;charset=utf-8" });
                        var url = URL.createObjectURL(blob);
                        var link = document.createElement("a");
                        link.href = url;
                        link.download = response.filename || "mesh_history.csv";
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                        URL.revokeObjectURL(url);
                        self.setUiStatus("CSV exported");
                    }
                })
                .fail(function(xhr) {
                    console.error("[MeshRepeat] exportCsv FAILED:", xhr.status, xhr.responseText);
                    self.setUiStatus("CSV export failed");
                });
        };

        self.attachHandlers = function() {
            $(rootSelector).off("click.meshrepeat");
            $(rootSelector).on("click.meshrepeat", "#mesh_repeatability_capture_now", function(e) {
                e.preventDefault();
                self.runCommand("capture_now", "Capturing mesh from printer...", "Failed to start capture");
            });
            $(rootSelector).on("click.meshrepeat", "#mesh_repeatability_save_current", function(e) {
                e.preventDefault();
                self.runCommand("save_current_mesh", "Capturing current mesh from printer...", "Failed to save mesh");
            });
            $(rootSelector).on("click.meshrepeat", "#mesh_repeatability_refresh_history", function(e) {
                e.preventDefault();
                self.fetchHistory();
            });
            $(rootSelector).on("click.meshrepeat", "#mesh_repeatability_export_csv", function(e) {
                e.preventDefault();
                self.exportCsv();
            });

            self.renderBindingDiagnostics();
            self.updateActionButtons();
        };

        self.onBeforeBinding = function() {
            self.attachHandlers();
            self.fetchHistory();
        };

        self.onAfterBinding = function() {
            self.attachHandlers();
            self.fetchHistory();
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: MeshRepeatabilityViewModel,
        elements: ["#tab_plugin_mesh_repeatability"]
    });
});
