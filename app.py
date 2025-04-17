import os
import uuid
import logging
from flask import render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory
from werkzeug.utils import secure_filename
import json
from datetime import datetime

# Import from main.py where app is created
from main import app, db
from models import ReportItem, ExportFile
from ocr_processor import process_image, extract_data_from_text
from data_exporter import export_to_excel, export_to_google_sheets

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
        # Create a unique filename to avoid collisions
        filename = str(uuid.uuid4()) + secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        logging.info(f"Saved file to {filepath}")
        
        try:
            # Process the image with OCR
            logging.info("Starting OCR processing")
            extracted_text = process_image(filepath)
            extracted_data = extract_data_from_text(extracted_text)
            logging.info(f"OCR processing complete, extracted {len(extracted_data)} items")
            
            # Generate a session ID for this batch of data
            session_id = str(uuid.uuid4())
            session['session_id'] = session_id
            logging.info(f"Generated session ID: {session_id}")
            
            # Save to database
            for item in extracted_data:
                report_item = ReportItem(
                    session_id=session_id,
                    item_number=item.get('item_number', ''),
                    price=item.get('price', ''),
                    original_description=item.get('description', ''),
                    original_date=item.get('date', ''),
                    original_time=item.get('time', ''),
                    # Try to determine period from date
                    period=f"P{item.get('date', '').split('/')[0].zfill(2)}" if item.get('date', '') and '/' in item.get('date', '') else "P00"
                )
                db.session.add(report_item)
            db.session.commit()
            logging.info(f"Saved {len(extracted_data)} items to database")
            
            # Store extracted data in session for later use
            session['extracted_data'] = extracted_data
            session['image_path'] = filepath
            
            return redirect(url_for('show_results'))
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error processing image: {str(e)}")
            flash(f'Error processing image: {str(e)}', 'danger')
            return redirect(url_for('index'))
    else:
        logging.warning(f"Invalid file type: {file.filename}")
        flash('File type not allowed. Please upload a valid image (png, jpg, jpeg, gif, bmp, tiff).', 'warning')
        return redirect(url_for('index'))

@app.route('/sample')
def create_sample_data():
    """Create sample data for testing without OCR processing"""
    logging.info("Creating sample data for testing")
    
    # Generate sample data
    sample_data = [
        {
            'item_number': '12345678',
            'price': '99.99',
            'date': '04/17/25',
            'time': '14:30:00',
            'description': 'Sample Item 1'
        },
        {
            'item_number': '87654321',
            'price': '149.99',
            'date': '04/17/25',
            'time': '14:35:00',
            'description': 'Sample Item 2'
        },
        {
            'item_number': '11223344',
            'price': '49.99',
            'date': '04/17/25',
            'time': '14:40:00',
            'description': 'Sample Item 3'
        }
    ]
    
    # Generate a session ID for this batch of data
    session_id = str(uuid.uuid4())
    session['session_id'] = session_id
    logging.info(f"Generated session ID for sample data: {session_id}")
    
    # Save to database
    for item in sample_data:
        report_item = ReportItem(
            session_id=session_id,
            item_number=item.get('item_number', ''),
            price=item.get('price', ''),
            original_description=item.get('description', ''),
            original_date=item.get('date', ''),
            original_time=item.get('time', ''),
            period=f"P{item.get('date', '').split('/')[0].zfill(2)}" if item.get('date', '') and '/' in item.get('date', '') else "P04"
        )
        db.session.add(report_item)
    db.session.commit()
    logging.info(f"Saved {len(sample_data)} sample items to database")
    
    # Store extracted data in session for later use
    session['extracted_data'] = sample_data
    
    flash('Sample data created successfully.', 'success')
    return redirect(url_for('show_results'))

@app.route('/results')
def show_results():
    extracted_data = session.get('extracted_data', [])
    if not extracted_data:
        flash('No data has been extracted yet.', 'warning')
        return redirect(url_for('index'))
    
    return render_template('results.html', data=extracted_data)

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
    return send_from_directory(directory=os.path.join('/tmp', 'exports'), filename=filename, as_attachment=True)

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
