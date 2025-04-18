import os
import uuid
import logging
import re
from flask import render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory
# Import TimeoutError for exception handling
from socket import timeout as TimeoutError
from werkzeug.utils import secure_filename
import json
from datetime import datetime

# Import from main.py where app is created
from main import app, db
from models import ReportItem, ExportFile
from ocr_processor import process_image, extract_data_from_text, extract_item_numbers_direct
from data_exporter import export_to_excel, export_to_google_sheets
from receipt_trainer import ReceiptTrainer

# Configure upload folder
UPLOAD_FOLDER = '/tmp/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    # Get the 5 most recent exports to show in the UI
    recent_exports = ExportFile.query.order_by(ExportFile.created_at.desc()).limit(5).all()
    return render_template('index.html', recent_exports=recent_exports)

@app.route('/upload', methods=['POST'])
def upload_file():
    logging.info("Upload endpoint called")
    if 'file' not in request.files:
        logging.warning("No file part in the request")
        flash('No file part', 'danger')
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        logging.warning("Empty filename submitted")
        flash('No selected file', 'danger')
        return redirect(request.url)
    
    logging.info(f"File uploaded: {file.filename}")
    
    if file and allowed_file(file.filename):
        try:
            # Import our new comprehensive image processor
            from new_uploader import process_receipt_image
            
            # Generate a session ID for this batch of data
            session_id = str(uuid.uuid4())
            session['session_id'] = session_id
            
            # Process the image using our comprehensive processor
            success, result = process_receipt_image(
                file, 
                app, 
                temp_dir=app.config['UPLOAD_FOLDER']
            )
            
            if not success:
                # If processing failed, show error message
                logging.error(f"Receipt processing failed: {result}")
                flash(f"Receipt processing failed: {result}", 'danger')
                return redirect(url_for('index'))
            
            # If we got here, processing succeeded and result contains the extracted data
            extracted_data = result
            
            # Check if we actually got any data
            if not extracted_data or len(extracted_data) == 0:
                logging.warning("No items were extracted from the receipt")
                flash('No item numbers detected from the receipt. Try a clearer image or different lighting.', 'warning')
                return redirect(url_for('index'))
            
            # Save extracted items to database
            for item in extracted_data:
                report_item = ReportItem(
                    session_id=session_id,
                    item_number=item.get('item_number', ''),
                    price=item.get('price', ''),
                    period=item.get('period', 'P04'),  # Default to April if not specified
                    exception=item.get('exception', ''),
                    quantity=item.get('quantity', 1),
                    additional_info=item.get('time', ''),  # Use time as additional info
                    original_description=item.get('description', ''),
                    original_date=item.get('date', ''),
                    original_time=item.get('time', '')
                )
                db.session.add(report_item)
            
            # Commit to database
            db.session.commit()
            logging.info(f"Saved {len(extracted_data)} items to database with session ID: {session_id}")
            
            # Store extracted data in session for later use
            session['extracted_data'] = extracted_data
            
            # Success message
            flash(f'Receipt processed successfully. {len(extracted_data)} items extracted.', 'success')
            return redirect(url_for('show_results'))
            
        except Exception as e:
            # Handle unexpected errors
            db.session.rollback()
            logging.error(f"Error processing image: {str(e)}")
            
            # Check for known timeout errors
            if "timeout" in str(e).lower():
                flash("Image processing timed out. Please try again with a clearer image.", "warning")
            else:
                flash(f'Error processing image: {str(e)}', 'danger')
                
            return redirect(url_for('index'))
    else:
        logging.warning(f"Invalid file type: {file.filename}")
        flash('File type not allowed. Please upload a valid image (png, jpg, jpeg, gif, bmp, tiff).', 'warning')
        return redirect(url_for('index'))

# Sample data route removed to focus exclusively on OCR-based extraction

# Manual entry has been removed to focus exclusively on OCR-based extraction

@app.route('/results')
def show_results():
    extracted_data = session.get('extracted_data', [])
    if not extracted_data:
        flash('No data has been extracted yet.', 'warning')
        return redirect(url_for('index'))
    
    # Pass current datetime for template to use
    from datetime import datetime
    now = datetime.now()
    
    return render_template('results.html', data=extracted_data, now=now)

@app.route('/update-data', methods=['POST'])
def update_data():
    try:
        updated_data = request.json
        session['extracted_data'] = updated_data
        
        # Get session ID
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({"success": False, "message": "Session ID not found. Please upload an image first."})
        
        # Delete previous items for this session
        ReportItem.query.filter_by(session_id=session_id).delete()
        
        # Add updated items to database
        for item in updated_data:
            report_item = ReportItem(
                session_id=session_id,
                item_number=item.get('item_number', ''),
                price=item.get('price', ''),
                period=item.get('period', 'P00'),
                exception=item.get('exception', ''),
                quantity=item.get('quantity', 1),
                additional_info=item.get('time', ''),  # Store additional info from the time field
                # Store original values for reference
                original_description=item.get('description', ''),
                original_date=item.get('date', ''),
                original_time=item.get('time', '')
            )
            db.session.add(report_item)
        
        db.session.commit()
        return jsonify({"success": True, "message": "Data updated successfully"})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error updating data: {str(e)}")
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/export', methods=['POST'])
def export_data():
    export_type = request.form.get('export_type', 'excel')
    data = session.get('extracted_data', [])
    session_id = session.get('session_id')
    
    if not data:
        flash('No data to export.', 'warning')
        return redirect(url_for('show_results'))
    
    if not session_id:
        flash('Session ID not found. Please upload an image first.', 'warning')
        return redirect(url_for('index'))
    
    try:
        # Create export record
        export_file = ExportFile(
            session_id=session_id,
            export_type=export_type,
            item_count=len(data),
            filename=f"refund_audit_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        
        if export_type == 'excel':
            download_path = export_to_excel(data)
            export_file.file_path = download_path
            export_file.filename = os.path.basename(download_path)
            db.session.add(export_file)
            db.session.commit()
            
            flash('Data exported to Excel successfully.', 'success')
            # Return file download link
            return jsonify({"success": True, "download_url": url_for('download_file', filename=os.path.basename(download_path))})
            
        elif export_type == 'google':
            try:
                spreadsheet_url = export_to_google_sheets(data)
                export_file.sheet_url = spreadsheet_url
                db.session.add(export_file)
                db.session.commit()
                
                flash('Data exported to Google Sheets successfully.', 'success')
                return jsonify({"success": True, "spreadsheet_url": spreadsheet_url})
            except ValueError as google_error:
                if "credentials not found" in str(google_error).lower():
                    # Google credentials are missing - inform the user and offer Excel as alternative
                    logging.warning("Google Sheets export failed due to missing credentials, falling back to Excel")
                    flash('Google Sheets export requires credentials. Exporting to Excel instead.', 'warning')
                    
                    # Fall back to Excel export
                    download_path = export_to_excel(data)
                    export_file.export_type = 'excel'  # Update the export type
                    export_file.file_path = download_path
                    export_file.filename = os.path.basename(download_path)
                    db.session.add(export_file)
                    db.session.commit()
                    
                    return jsonify({
                        "success": True, 
                        "download_url": url_for('download_file', filename=os.path.basename(download_path)),
                        "fallback": True,
                        "fallback_message": "Exported to Excel instead of Google Sheets due to missing credentials."
                    })
                else:
                    # Other Google Sheets error
                    raise
            
        else:
            flash('Invalid export type.', 'danger')
            return jsonify({"success": False, "message": "Invalid export type"})
            
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error during export: {str(e)}")
        flash(f'Error exporting data: {str(e)}', 'danger')
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/download/<filename>')
def download_file(filename):
    # Check the version of Flask to determine the correct parameters
    try:
        # For newer versions of Flask
        return send_from_directory(os.path.join('/tmp', 'exports'), filename, as_attachment=True)
    except TypeError:
        # For older versions that expect 'directory' parameter
        return send_from_directory(directory=os.path.join('/tmp', 'exports'), filename=filename, as_attachment=True)

@app.route('/train', methods=['GET', 'POST'])
def train():
    # Setup static folder for upload images if it doesn't exist
    uploads_folder = os.path.join('static', 'uploads')
    if not os.path.exists(uploads_folder):
        os.makedirs(uploads_folder)
        
    # Initialize trainer
    trainer = ReceiptTrainer()
    training_summary = trainer.get_training_summary()
    
    # Load existing examples for display
    if os.path.exists(trainer.training_data_path):
        training_examples = []
        for example in trainer.training_data.get('examples', []):
            image_path = example.get('image_path', '')
            image_filename = os.path.basename(image_path) if image_path else ''
            image_exists = os.path.exists(image_path) if image_path else False
            
            training_examples.append({
                'item_number': example.get('item_number', ''),
                'description': example.get('description', ''),
                'added_at': example.get('added_at', ''),
                'image_path': image_path,
                'image_filename': image_filename,
                'image_exists': image_exists
            })
    else:
        training_examples = []
    
    # Handle POST request (training submission)
    if request.method == 'POST':
        if 'receipt_image' not in request.files:
            flash('No file part in the request', 'danger')
            return redirect(url_for('train'))
            
        file = request.files['receipt_image']
        item_number = request.form.get('item_number', '')
        description = request.form.get('description', '')
        analyze_regions = 'analyze_regions' in request.form
        
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(url_for('train'))
            
        if not item_number:
            flash('Item number is required', 'danger')
            return redirect(url_for('train'))
            
        if file and allowed_file(file.filename):
            try:
                # Save uploaded file
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                filename = f"{timestamp}_{filename}"
                file_path = os.path.join(uploads_folder, filename)
                file.save(file_path)
                
                # Add to training data
                if analyze_regions:
                    # Full analysis with region detection
                    analysis_result = trainer.analyze_receipt_for_training(file_path, item_number)
                    training_result = analysis_result
                    flash('Training data added successfully with region analysis', 'success')
                else:
                    # Simple example addition
                    success = trainer.add_example(item_number, file_path, description)
                    training_result = {
                        'success': success,
                        'item_number': item_number,
                        'regions': [],
                        'patterns': []
                    }
                    flash('Training data added successfully', 'success')
                
                # Update training summary
                training_summary = trainer.get_training_summary()
                
                # Force refresh of training examples
                training_examples = []
                for example in trainer.training_data.get('examples', []):
                    image_path = example.get('image_path', '')
                    image_filename = os.path.basename(image_path) if image_path else ''
                    image_exists = os.path.exists(image_path) if image_path else False
                    
                    training_examples.append({
                        'item_number': example.get('item_number', ''),
                        'description': example.get('description', ''),
                        'added_at': example.get('added_at', ''),
                        'image_path': image_path,
                        'image_filename': image_filename,
                        'image_exists': image_exists
                    })
                
                # Return with results
                return render_template('train.html', 
                                     training_result=training_result,
                                     training_summary=training_summary,
                                     training_examples=training_examples,
                                     receipt_image_path=file_path,
                                     receipt_image_filename=filename)
                                     
            except Exception as e:
                logging.error(f"Error in training: {str(e)}")
                flash(f'Error processing training data: {str(e)}', 'danger')
                return redirect(url_for('train'))
        else:
            flash('Invalid file type', 'danger')
            return redirect(url_for('train'))
    
    # GET request - show training form
    return render_template('train.html', 
                         training_summary=training_summary,
                         training_examples=training_examples)

@app.route('/history')
def export_history():
    # Get all exports ordered by most recent first
    exports = ExportFile.query.order_by(ExportFile.created_at.desc()).all()
    return render_template('history.html', exports=exports)

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
