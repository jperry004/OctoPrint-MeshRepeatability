$(function() {
    function MeshRepeatabilityViewModel(parameters) {
        var self = this;

        self.history = ko.observableArray([]);
        self.selectedRecord = ko.observable(null);
        self.isCapturing = ko.observable(false);

        self.fetchHistory = function() {
            $.ajax({
                url: API_BASEURL + "plugin/mesh_repeatability",
                type: "GET",
                success: function(response) {
                    self.history(response.history);
                    if (self.history().length > 0 && !self.selectedRecord()) {
                        self.selectedRecord(self.history()[0]);
                    }
                }
            });
        };

        self.captureNow = function() {
            self.isCapturing(true);
            $.ajax({
                url: API_BASEURL + "plugin/mesh_repeatability",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({ "command": "capture_now" }),
                contentType: "application/json; charset=UTF-8",
                success: function() {
                    setTimeout(function() {  // M420 V is instant - 2s is more than enough
                        self.isCapturing(false);
                        self.fetchHistory();
                    }, 2000);
                }
            });
        };

        self.exportCsv = function() {
            $.ajax({
                url: API_BASEURL + "plugin/mesh_repeatability",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({ "command": "export_csv" }),
                contentType: "application/json; charset=utf-8;",
                success: function(response) {
                    if (response.csv) {
                        const blob = new Blob([response.csv], { type: "text/csv;charset=utf-8;" });
                        const link = document.createElement("a");
                        link.href = URL.createObjectURL(blob);
                        link.download = response.filename || "mesh_history.csv";
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                    }
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
            self.fetchHistory();
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: MeshRepeatabilityViewModel,
        elements: ["#tab_plugin_mesh_repeatability"]
    });
});
