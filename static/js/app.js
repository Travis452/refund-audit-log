document.addEventListener("DOMContentLoaded", function () {
  const exportExcelBtn = document.getElementById("export-excel-btn");
  if (exportExcelBtn) {
    exportExcelBtn.addEventListener("click", async function (e) {
      e.preventDefault();

      try {
        const response = await fetch("/export", {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
          },
          body: "export_type=excel",
        });

        const data = await response.json();
        if (data.success) {
          if (data.download_url) {
            window.location.href = data.download_url;
          } else if (data.spreadsheet_url) {
            window.open(data.spreadsheet_url, "_blank");
          }
        } else {
          alert(data.message || "Export failed.");
        }
      } catch (error) {
        console.error("Error during export:", error);
        alert("An error occurred while exporting. Check console for details.");
      }
    });
  }
});
