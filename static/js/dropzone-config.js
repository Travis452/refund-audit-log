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
