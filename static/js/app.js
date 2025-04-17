document.addEventListener('DOMContentLoaded', function() {
    // Handle adding a new row
    const addRowBtn = document.getElementById('add-row-btn');
    if (addRowBtn) {
        addRowBtn.addEventListener('click', function() {
            const tbody = document.querySelector('#extracted-data-table tbody');
            const template = document.getElementById('row-template');
            const newRow = document.importNode(template.content, true);
            
            // Set a unique row ID
            const rowId = Date.now();
            newRow.querySelector('tr').dataset.rowId = rowId;
            
            // Add delete handler to the new row
            const deleteBtn = newRow.querySelector('.delete-row-btn');
            deleteBtn.addEventListener('click', function() {
                const row = this.closest('tr');
                row.remove();
            });
            
            tbody.appendChild(newRow);
        });
    }
    
    // Handle deleting rows
    document.querySelectorAll('.delete-row-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const row = this.closest('tr');
            row.remove();
        });
    });
    
    // Handle saving changes
    const saveChangesBtn = document.getElementById('save-changes-btn');
    if (saveChangesBtn) {
        saveChangesBtn.addEventListener('click', function() {
            const rows = document.querySelectorAll('#extracted-data-table tbody tr');
            const data = [];
            
            rows.forEach(row => {
                // Get period to convert to date format for backwards compatibility
                const periodElement = row.querySelector('.period');
                let period = "P00";
                let dateValue = "";
                
                if (periodElement) {
                    period = periodElement.value || "P00";
                    // Extract the month number from the period (e.g., "P04" -> "04")
                    const monthStr = period.substring(1);
                    // Create a date string in MM/DD/YY format
                    const currentYear = new Date().getFullYear().toString().substring(2);
                    dateValue = `${monthStr}/01/${currentYear}`;
                }
                
                const item = {
                    item_number: row.querySelector('.item-number').value,
                    description: "Item " + row.querySelector('.item-number').value, // Description is now derived from item number
                    price: row.querySelector('.price').value,
                    date: dateValue,
                    time: row.querySelector('.additional-info') ? row.querySelector('.additional-info').value : "",
                    exception: row.querySelector('.exception') ? row.querySelector('.exception').value : "",
                    quantity: row.querySelector('.quantity') ? row.querySelector('.quantity').value : 1,
                    period: period
                };
                data.push(item);
            });
            
            // Save data via AJAX
            fetch('/update-data', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showAlert('success', 'Data updated successfully!');
                } else {
                    showAlert('danger', 'Error: ' + data.message);
                }
            })
            .catch(error => {
                showAlert('danger', 'Error: ' + error.message);
            });
        });
    }
    
    // Handle export to Excel
    const exportExcelBtn = document.getElementById('export-excel-btn');
    if (exportExcelBtn) {
        exportExcelBtn.addEventListener('click', function() {
            showLoadingModal('Exporting to Excel...');
            
            const formData = new FormData();
            formData.append('export_type', 'excel');
            
            fetch('/export', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                hideLoadingModal();
                if (data.success) {
                    const alertBox = document.getElementById('export-alert');
                    const message = document.getElementById('export-message');
                    const link = document.getElementById('export-link');
                    
                    message.textContent = 'Excel file created successfully! ';
                    link.href = data.download_url;
                    link.textContent = 'Download Excel File';
                    alertBox.style.display = 'block';
                    
                    // Auto download
                    window.location.href = data.download_url;
                } else {
                    showAlert('danger', 'Export failed: ' + data.message);
                }
            })
            .catch(error => {
                hideLoadingModal();
                showAlert('danger', 'Export error: ' + error.message);
            });
        });
    }
    
    // Handle export to Google Sheets
    const exportGoogleBtn = document.getElementById('export-google-btn');
    if (exportGoogleBtn) {
        exportGoogleBtn.addEventListener('click', function() {
            showLoadingModal('Exporting to Google Sheets...');
            
            const formData = new FormData();
            formData.append('export_type', 'google');
            
            fetch('/export', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                hideLoadingModal();
                if (data.success) {
                    const alertBox = document.getElementById('export-alert');
                    const message = document.getElementById('export-message');
                    const link = document.getElementById('export-link');
                    
                    message.textContent = 'Data exported to Google Sheets! ';
                    link.href = data.spreadsheet_url;
                    link.textContent = 'Open Google Sheets';
                    alertBox.style.display = 'block';
                    
                    // Open in new tab
                    window.open(data.spreadsheet_url, '_blank');
                } else {
                    showAlert('danger', 'Export failed: ' + data.message);
                }
            })
            .catch(error => {
                hideLoadingModal();
                showAlert('danger', 'Export error: ' + error.message);
            });
        });
    }
    
    // Utility function to show an alert
    function showAlert(type, message) {
        // Create an alert element
        const alertElement = document.createElement('div');
        alertElement.className = `alert alert-${type} alert-dismissible fade show`;
        alertElement.setAttribute('role', 'alert');
        
        // Set the message
        alertElement.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        // Add to the page
        const container = document.querySelector('.container');
        container.insertBefore(alertElement, container.firstChild);
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alertElement);
            bsAlert.close();
        }, 5000);
    }
    
    // Show loading modal
    function showLoadingModal(message) {
        const loadingMessage = document.getElementById('loading-message');
        if (loadingMessage) {
            loadingMessage.textContent = message || 'Processing...';
        }
        
        const loadingModal = new bootstrap.Modal(document.getElementById('loadingModal'));
        loadingModal.show();
    }
    
    // Hide loading modal
    function hideLoadingModal() {
        const loadingModalElement = document.getElementById('loadingModal');
        const loadingModal = bootstrap.Modal.getInstance(loadingModalElement);
        if (loadingModal) {
            loadingModal.hide();
        }
    }
});
