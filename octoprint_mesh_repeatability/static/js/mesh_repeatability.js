$(function() {
    function MeshRepeatabilityViewModel(parameters) {
        var self = this;
        var PLUGIN_ID = "mesh_repeatability";
        var rootSelector = "#tab_plugin_mesh_repeatability";

        console.log("[MeshRepeat] ViewModel constructor called");

        self.history = ko.observableArray([]);
        self.selectedRecord = ko.observable(null);
        self.isCapturing = ko.observable(false);
        self.diagnostics = ko.observable(null);
        self.uiStatus = ko.observable("Initializing...");
        self.bindingDiagnostics = ko.observable({
            rootCount: 0,
            buttonCount: 0,
            buttonContexts: [],
            lastBoundAt: null,
            handlersAttached: false
        });

        self.updateActionButtons = function() {
            var capturing = self.isCapturing();
            $("#mesh_repeatability_capture_now").prop("disabled", capturing);
            $("#mesh_repeatability_save_current").prop("disabled", capturing);
            $("#mesh_repeatability_refresh_history").prop("disabled", capturing);
            $("#mesh_repeatability_export_csv").prop("disabled", capturing);
            $("#mesh_repeatability_capture_now_label").text(capturing ? "Capturing..." : "Capture Mesh Now");
            self.uiStatus(capturing ? "Capture in progress..." : "Ready");
        };

        self.inspectUiState = function(reason) {
            var roots = $(rootSelector);
            var buttons = roots.find("button");
            var buttonContexts = [];

            buttons.each(function(index, button) {
                var context = ko.contextFor(button);
                buttonContexts.push({
                    index: index,
                    id: button.id || "(no id)",
                    hasContext: !!context
                });
            });

            var snapshot = {
                rootCount: roots.length,
                buttonCount: buttons.length,
                buttonContexts: buttonContexts,
                lastBoundAt: new Date().toISOString(),
                handlersAttached: true
            };

            self.bindingDiagnostics(snapshot);
            console.log("[MeshRepeat] UI inspection (" + reason + "):", snapshot);

            if (roots.length !== 1) {
                console.warn("[MeshRepeat] Expected exactly one tab root, found", roots.length);
                self.uiStatus("UI warning: expected 1 tab root, found " + roots.length);
            } else if (buttonContexts.some(function(entry) { return !entry.hasContext; })) {
                console.warn("[MeshRepeat] Some buttons have no Knockout context:", buttonContexts);
                self.uiStatus("UI warning: button context mismatch detected");
            } else if (!self.isCapturing()) {
                self.uiStatus("Ready");
            }
        };

        self.attachActionHandlers = function() {
            var root = $(rootSelector);

            root.off("click.meshrepeat");
            root.on("click.meshrepeat", "#mesh_repeatability_capture_now", function(e) {
                e.preventDefault();
                console.log("[MeshRepeat] Delegated click: capture");
                self.captureNow();
            });
            root.on("click.meshrepeat", "#mesh_repeatability_save_current", function(e) {
                e.preventDefault();
                console.log("[MeshRepeat] Delegated click: save current");
                self.saveCurrentMesh();
            });
            root.on("click.meshrepeat", "#mesh_repeatability_refresh_history", function(e) {
                e.preventDefault();
                console.log("[MeshRepeat] Delegated click: refresh history");
                self.fetchHistory();
            });
            root.on("click.meshrepeat", "#mesh_repeatability_export_csv", function(e) {
                e.preventDefault();
                console.log("[MeshRepeat] Delegated click: export csv");
                self.exportCsv();
            });

            self.inspectUiState("attachActionHandlers");
        };

        // ── Fetch History (GET) ──────────────────────────────────
        self.fetchHistory = function() {
            console.log("[MeshRepeat] fetchHistory() called");
            OctoPrint.simpleApiGet(PLUGIN_ID)
                .done(function(response) {
                    console.log("[MeshRepeat] fetchHistory OK:", response);
                    self.history(response.history || []);
                    if (response.diagnostics) {
                        self.diagnostics(response.diagnostics);
                    }
                    if (self.history().length > 0 && !self.selectedRecord()) {
                        self.selectedRecord(self.history()[0]);
                    }
                    if (!self.isCapturing()) {
                        self.uiStatus("Ready");
                    }
                })
                .fail(function(xhr) {
                    console.error("[MeshRepeat] fetchHistory FAILED:", xhr.status, xhr.responseText);
                    self.uiStatus("History request failed");
                });
        };

        // ── Capture Now (POST) ───────────────────────────────────
        self.captureNow = function() {
            console.log("[MeshRepeat] captureNow() clicked");
            self.isCapturing(true);
            OctoPrint.simpleApiCommand(PLUGIN_ID, "capture_now", {})
                .done(function(response) {
                    console.log("[MeshRepeat] captureNow OK:", response);
                    new PNotify({
                        title: "Mesh Repeatability",
                        text: "Capturing mesh from printer...",
                        type: "info",
                        hide: true,
                        delay: 3000
                    });
                    setTimeout(function() {
                        self.isCapturing(false);
                        self.fetchHistory();
                    }, 3000);
                })
                .fail(function(xhr) {
                    console.error("[MeshRepeat] captureNow FAILED:", xhr.status, xhr.responseText);
                    new PNotify({
                        title: "Mesh Repeatability",
                        text: "Failed to start capture (HTTP " + xhr.status + ")",
                        type: "error",
                        hide: true,
                        delay: 5000
                    });
                    self.isCapturing(false);
                    self.uiStatus("Capture failed");
                });
        };

        // ── Save Current Mesh (POST) ─────────────────────────────
        self.saveCurrentMesh = function() {
            console.log("[MeshRepeat] saveCurrentMesh() clicked");
            self.isCapturing(true);
            OctoPrint.simpleApiCommand(PLUGIN_ID, "save_current_mesh", {})
                .done(function(response) {
                    console.log("[MeshRepeat] saveCurrentMesh OK:", response);
                    new PNotify({
                        title: "Mesh Repeatability",
                        text: "Capturing current mesh from printer...",
                        type: "info",
                        hide: true,
                        delay: 3000
                    });
                    setTimeout(function() {
                        self.isCapturing(false);
                        self.fetchHistory();
                    }, 3000);
                })
                .fail(function(xhr) {
                    console.error("[MeshRepeat] saveCurrentMesh FAILED:", xhr.status, xhr.responseText);
                    new PNotify({
                        title: "Mesh Repeatability",
                        text: "Failed to save mesh (HTTP " + xhr.status + ")",
                        type: "error",
                        hide: true,
                        delay: 5000
                    });
                    self.isCapturing(false);
                    self.uiStatus("Save current mesh failed");
                });
        };

        // ── Export CSV (POST) ────────────────────────────────────
        self.exportCsv = function() {
            console.log("[MeshRepeat] exportCsv() clicked");
            OctoPrint.simpleApiCommand(PLUGIN_ID, "export_csv", {})
                .done(function(response) {
                    console.log("[MeshRepeat] exportCsv OK");
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
                        new PNotify({
                            title: "Mesh Repeatability",
                            text: "CSV exported successfully",
                            type: "success",
                            hide: true,
                            delay: 3000
                        });
                    }
                })
                .fail(function(xhr) {
                    console.error("[MeshRepeat] exportCsv FAILED:", xhr.status, xhr.responseText);
                    new PNotify({
                        title: "Mesh Repeatability",
                        text: "CSV export failed (HTTP " + xhr.status + ")",
                        type: "error",
                        hide: true,
                        delay: 5000
                    });
                    self.uiStatus("CSV export failed");
                });
        };

        // ── Select Record ────────────────────────────────────────
        self.selectRecord = function(record) {
            console.log("[MeshRepeat] selectRecord():", record.id);
            self.selectedRecord(record);
        };

        // ── Format Matrix for display ────────────────────────────
        self.formatMatrix = function(matrix) {
            if (!matrix || matrix.length === 0) return "No data";
            return matrix.map(function(row) {
                return row.map(function(val) {
                    return Number(val).toFixed(3).padStart(8, ' ');
                }).join(" ");
            }).join("\n");
        };

        // ── Lifecycle ────────────────────────────────────────────
        self.onBeforeBinding = function() {
            console.log("[MeshRepeat] onBeforeBinding - plugin initializing");
            self.uiStatus("Loading history...");
            self.fetchHistory();
        };

        self.onAfterBinding = function() {
            console.log("[MeshRepeat] onAfterBinding - bindings applied, UI ready");
            self.attachActionHandlers();
            self.updateActionButtons();
        };

        self.isCapturing.subscribe(function() {
            self.updateActionButtons();
        });

        $(document).off("shown.meshrepeat", 'a[href="#tab_plugin_mesh_repeatability"]');
        $(document).on("shown.meshrepeat", 'a[href="#tab_plugin_mesh_repeatability"]', function() {
            console.log("[MeshRepeat] Tab shown event detected");
            self.attachActionHandlers();
            self.updateActionButtons();
        });

        $(window).off("focus.meshrepeat");
        $(window).on("focus.meshrepeat", function() {
            console.log("[MeshRepeat] Window focus event detected");
            self.inspectUiState("window-focus");
        });

        console.log("[MeshRepeat] ViewModel constructed OK");
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: MeshRepeatabilityViewModel,
        elements: ["#tab_plugin_mesh_repeatability"]
    });
});
