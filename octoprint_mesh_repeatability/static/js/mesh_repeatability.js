$(function() {
    function MeshRepeatabilityViewModel(parameters) {
        var self = this;

        self.history = ko.observableArray([]);
        self.selectedRecord = ko.observable(null);
        self.isCapturing = ko.observable(false);
        self.diagnostics = ko.observable(null);

        self.fetchHistory = function() {
            $.ajax({
                url: API_BASEURL + "plugin/mesh_repeatability",
                type: "GET",
                success: function(response) {
                    self.history(response.history);
                    if (response.diagnostics) {
                        self.diagnostics(response.diagnostics);
                    }
                    if (self.history().length > 0 && !self.selectedRecord()) {
                        self.selectedRecord(self.history()[0]);
                    }
                    console.log("[Mesh Repeatability] History fetched:", response);
                },
                error: function(err) {
                    console.error("[Mesh Repeatability] Failed to fetch history:", err);
                }
            });
        };

        self.captureNow = function() {
            self.isCapturing(true);
            console.log("[Mesh Repeatability] Manual capture triggered");
            $.ajax({
                url: API_BASEURL + "plugin/mesh_repeatability",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({ "command": "capture_now" }),
                contentType: "application/json; charset=UTF-8",
                success: function(response) {
                    console.log("[Mesh Repeatability] Capture response:", response);
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
                },
                error: function(err) {
                    console.error("[Mesh Repeatability] Capture error:", err);
                    new PNotify({
                        title: "Mesh Repeatability",
                        text: "Failed to start capture",
                        type: "error",
                        hide: true,
                        delay: 5000
                    });
                    self.isCapturing(false);
                }
            });
        };

        self.saveCurrentMesh = function() {
            self.isCapturing(true);
            console.log("[Mesh Repeatability] 'Save Current Mesh' triggered");
            $.ajax({
                url: API_BASEURL + "plugin/mesh_repeatability",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({ "command": "save_current_mesh" }),
                contentType: "application/json; charset=UTF-8",
                success: function(response) {
                    console.log("[Mesh Repeatability] Mesh save response:", response);
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
                },
                error: function(err) {
                    console.error("[Mesh Repeatability] Mesh save error:", err);
                    new PNotify({
                        title: "Mesh Repeatability",
                        text: "Failed to save mesh",
                        type: "error",
                        hide: true,
                        delay: 5000
                    });
                    self.isCapturing(false);
                }
            });
        };

        self.exportCsv = function() {
            console.log("[Mesh Repeatability] CSV export triggered");
            $.ajax({
                url: API_BASEURL + "plugin/mesh_repeatability",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({ "command": "export_csv" }),
                contentType: "application/json; charset=UTF-8",
                success: function(response) {
                    console.log("[Mesh Repeatability] CSV export success");
                    if (response.csv) {
                        var blob = new Blob([response.csv], { type: "text/csv;charset=utf-8;" });
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
                },
                error: function(err) {
                    console.error("[Mesh Repeatability] CSV export error:", err);
                    new PNotify({
                        title: "Mesh Repeatability",
                        text: "CSV export failed",
                        type: "error",
                        hide: true,
                        delay: 5000
                    });
                }
            });
        };

        self.selectRecord = function(record) {
            self.selectedRecord(record);
        };

        self.formatMatrix = function(matrix) {
            if (!matrix || matrix.length === 0) return "No data";
            return matrix.map(function(row) {
                return row.map(function(val) {
                    return Number(val).toFixed(3).padStart(8, ' ');
                }).join(" ");
            }).join("\n");
        };

        self.onBeforeBinding = function() {
            console.log("[Mesh Repeatability] Plugin loaded and initialized");
            self.fetchHistory();
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: MeshRepeatabilityViewModel,
        elements: ["#tab_plugin_mesh_repeatability"]
    });
});
