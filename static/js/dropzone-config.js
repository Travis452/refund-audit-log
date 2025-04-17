// Dropzone configuration
Dropzone.autoDiscover = false;

document.addEventListener('DOMContentLoaded', function() {
    // Initialize Dropzone
    const myDropzone = new Dropzone("#upload-dropzone", {
        url: "/upload",
        autoProcessQueue: false,
        maxFilesize: 10, // MB
        acceptedFiles: "image/*",
        maxFiles: 1,
        addRemoveLinks: true,
        dictRemoveFile: "Remove",
        dictDefaultMessage: "Drop files here to upload",
        init: function() {
            // Cache the upload button
            const submitButton = document.getElementById("submit-upload");
            const myDropzone = this;
            
            // When the button is clicked, process the queue
            submitButton.addEventListener("click", function() {
                if (myDropzone.getQueuedFiles().length > 0) {
                    // Show loading indicator
                    submitButton.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Processing...';
                    submitButton.disabled = true;
                    
                    // Add a loading overlay to the page
                    const loadingOverlay = document.createElement('div');
                    loadingOverlay.className = 'loading-overlay';
                    loadingOverlay.innerHTML = `
                        <div class="loading-content">
                            <div class="spinner-border text-light mb-3" role="status">
                                <span class="visually-hidden">Loading...</span>
                            </div>
                            <h5 class="text-light">Processing Image...</h5>
                            <p class="text-light-emphasis">Please wait while we extract data from your image</p>
                        </div>
                    `;
                    document.body.appendChild(loadingOverlay);
                    
                    // Process the queue
                    myDropzone.processQueue();
                } else {
                    // If no files are in the queue, show an alert
                    showAlert("warning", "Please select a file to upload first.");
                }
            });
            
            // Show a success message when upload is complete
            this.on("success", function(file, response) {
                window.location.href = "/results";
            });
            
            // Show error message on upload error
            this.on("error", function(file, errorMessage, xhr) {
                // Remove loading overlay
                const overlay = document.querySelector('.loading-overlay');
                if (overlay) {
                    overlay.remove();
                }
                
                // Reset button
                const submitButton = document.getElementById("submit-upload");
                submitButton.innerHTML = '<i class="fas fa-upload me-2"></i>Process Image';
                submitButton.disabled = false;
                
                if (typeof errorMessage === "string") {
                    showAlert("danger", "Error: " + errorMessage);
                } else {
                    showAlert("danger", "An error occurred during upload. Please try again.");
                }
            });
        }
    });
    
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
        
        // Add to the page before the dropzone
        const dropzoneElement = document.getElementById('upload-dropzone');
        dropzoneElement.parentNode.insertBefore(alertElement, dropzoneElement);
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alertElement);
            bsAlert.close();
        }, 5000);
    }
});
