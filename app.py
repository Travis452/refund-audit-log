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

@app.route('/sample')
def create_sample_data():
    """Create sample data for testing without OCR processing"""
    logging.info("Creating sample data for testing")
    
    # Generate sample data to match the Refund Audit format in IMG_6560.png
    # but also include the items similar to those in the user's receipt with CORRECT item numbers
    sample_data = [
        # Items from the user's receipt format with correct item numbers
        {
            'item_number': '9900099',
            'price': '499.99',
            'period': 'P04',
            'quantity': 1,
            'exception': '',
            'date': '04/17/25',
            'time': '13:49:41',
            'description': 'MICROSOFT XBOX'
        },
        {
            'item_number': '1806281',
            'price': '29.99',
            'period': 'P04',
            'quantity': 1,
            'exception': '',
            'date': '04/17/25',
            'time': '13:50:22',
            'description': 'HDMI CABLE'
        },
        {
            'item_number': '1839592',
            'price': '59.98',
            'period': 'P04',
            'quantity': 1,
            'exception': '',
            'date': '04/17/25',
            'time': '13:53:10',
            'description': 'CONTROLLER'
        },
        {
            'item_number': '7276736',
            'price': '14.99',
            'period': 'P04',
            'quantity': 1,
            'exception': '',
            'date': '04/17/25',
            'time': '13:54:46',
            'description': 'SCREEN PROTECTOR'
        },
        {
            'item_number': '7188016',
            'price': '19.98',
            'period': 'P04',
            'quantity': 1,
            'exception': '',
            'date': '04/17/25',
            'time': '13:55:53',
            'description': 'PHONE CHARGER'
        },
        {
            'item_number': '8157432',
            'price': '49.97',
            'period': 'P04',
            'quantity': 1,
            'exception': '',
            'date': '04/17/25',
            'time': '13:56:77',
            'description': 'HEADPHONES'
        },
        {
            'item_number': '3346994',
            'price': '349.99',
            'period': 'P04',
            'quantity': 1,
            'exception': '',
            'date': '04/17/25',
            'time': '13:57:31',
            'description': 'SMART WATCH'
        },
        {
            'item_number': '2255392',
            'price': '24.99',
            'period': 'P04',
            'quantity': 1,
            'exception': '',
            'date': '04/17/25',
            'time': '13:57:38',
            'description': 'SCREEN CLEANER'
        },
        {
            'item_number': '1176647',
            'price': '24.98',
            'period': 'P04',
            'quantity': 1,
            'exception': '',
            'date': '04/17/25',
            'time': '13:57:83',
            'description': 'POWER BANK'
        },
        {
            'item_number': '2633324',
            'price': '9.99',
            'period': 'P04',
            'quantity': 1,
            'exception': '',
            'date': '04/17/25',
            'time': '13:58:44',
            'description': 'USB CABLE'
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
            period=item.get('period', 'P04'),
            exception=item.get('exception', ''),
            quantity=item.get('quantity', 1),
            additional_info=item.get('additional_info', ''),
            original_description=item.get('description', ''),
            original_date=item.get('date', ''),
            original_time=item.get('time', '')
        )
        db.session.add(report_item)
    db.session.commit()
    logging.info(f"Saved {len(sample_data)} sample items to database")
    
    # Store extracted data in session for later use
    session['extracted_data'] = sample_data
    
    flash('Sample data created successfully.', 'success')
    return redirect(url_for('show_results'))

@app.route('/manual-entry', methods=['POST'])
def manual_entry():
    """Process manually entered item numbers"""
    try:
        logging.info("Manual item entry endpoint called")
        
        # Get item numbers from form - one per line
        item_numbers_text = request.form.get('item_numbers', '')
        if not item_numbers_text.strip():
            flash('Please enter at least one item number.', 'warning')
            return redirect(url_for('index'))
            
        # Split by lines and clean up
        item_numbers = [line.strip() for line in item_numbers_text.split('\n') if line.strip()]
        logging.info(f"Received {len(item_numbers)} manually entered item numbers")
        
        # Basic validation
        valid_item_numbers = []
        for number in item_numbers:
            # Check if it's a valid item number format (6-9 digits)
            if re.match(r'^\d{6,9}$', number):
                valid_item_numbers.append(number)
            else:
                logging.warning(f"Invalid item number format: {number}")
        
        if not valid_item_numbers:
            flash('No valid item numbers found. Item numbers should be 6-9 digits.', 'warning')
            return redirect(url_for('index'))
            
        logging.info(f"Found {len(valid_item_numbers)} valid item numbers")
        
        # Create data entries for these item numbers
        extracted_data = []
        from datetime import datetime
        today = datetime.now().strftime('%m/%d/%y')
        current_month = datetime.now().strftime('%m')
        period = f"P{current_month}"
        
        # Create an entry for each item number
        for item_number in valid_item_numbers:
            item_data = {
                'item_number': item_number,
                'price': '0.00',  # Default price, user can edit
                'period': period,
                'date': today,
                'time': datetime.now().strftime('%H:%M:%S'),
                'description': f"Item {item_number}",
                'quantity': 1,
                'exception': ''
            }
            extracted_data.append(item_data)
        
        # Generate a session ID
        session_id = str(uuid.uuid4())
        session['session_id'] = session_id
        logging.info(f"Generated session ID for manual entry: {session_id}")
        
        # Save to database
        for item in extracted_data:
            report_item = ReportItem(
                session_id=session_id,
                item_number=item.get('item_number', ''),
                price=item.get('price', ''),
                period=item.get('period', 'P00'),
                exception=item.get('exception', ''),
                quantity=item.get('quantity', 1),
                additional_info=item.get('additional_info', ''),
                original_description=item.get('description', ''),
                original_date=item.get('date', ''),
                original_time=item.get('time', '')
            )
            db.session.add(report_item)
        db.session.commit()
        
        # Store in session for results page
        session['extracted_data'] = extracted_data
        
        flash(f'Successfully processed {len(extracted_data)} item numbers.', 'success')
        return redirect(url_for('show_results'))
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error processing manual item numbers: {str(e)}")
        flash(f'Error processing item numbers: {str(e)}', 'danger')
        return redirect(url_for('index'))

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
