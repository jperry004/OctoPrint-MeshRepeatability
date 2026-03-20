$(function() {
    function MeshRepeatabilityViewModel(parameters) {
        var self = this;
        var PLUGIN_ID = "mesh_repeatability";

        console.log("[MeshRepeat] ViewModel constructor called");

        self.history = ko.observableArray([]);
        self.selectedRecord = ko.observable(null);
        self.isCapturing = ko.observable(false);
        self.diagnostics = ko.observable(null);

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
                })
                .fail(function(xhr) {
                    console.error("[MeshRepeat] fetchHistory FAILED:", xhr.status, xhr.responseText);
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
            self.fetchHistory();
        };

        self.onAfterBinding = function() {
            console.log("[MeshRepeat] onAfterBinding - bindings applied, UI ready");
        };

        console.log("[MeshRepeat] ViewModel constructed OK");
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: MeshRepeatabilityViewModel,
        elements: ["#tab_plugin_mesh_repeatability"]
    });
});
