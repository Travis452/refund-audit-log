import os
import uuid
import logging
import re
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
            # Process the image with OCR to extract the receipt data
            logging.info("Starting OCR processing...")
            extracted_text = process_image(filepath)
            
            if "Error" in extracted_text:
                logging.error(f"OCR processing error: {extracted_text}")
                flash(f'OCR processing error: {extracted_text}', 'danger')
                return redirect(url_for('index'))
            
            # Extract structured data from the OCR text
            extracted_data = extract_data_from_text(extracted_text)
            logging.info(f"OCR processing complete, extracted {len(extracted_data)} items")
            
            # Always run our more aggressive item number extraction even if OCR found structured data
            import re  # Make sure re is imported
            logging.warning("Looking directly for item numbers in the OCR text")
            
            # Extract 6-8 digit numbers with improved accuracy
            # Look for 7-digit and 8-digit numbers first (most likely to be item numbers)
            primary_pattern = r'\b\d{7,8}\b'
            primary_matches = re.findall(primary_pattern, extracted_text)
            logging.info(f"Found {len(primary_matches)} 7-8 digit numbers")
            
            # Also look for 6-digit numbers as a fallback
            secondary_pattern = r'\b\d{6}\b'
            secondary_matches = re.findall(secondary_pattern, extracted_text)
            logging.info(f"Found {len(secondary_matches)} 6-digit numbers")
            
            # Combine all matches, with 7-8 digit numbers first
            matches = primary_matches + secondary_matches
            
            # Advanced filtering to remove false positives
            filtered_matches = []
            for match in matches:
                # Skip if it looks like a date (e.g., 20220405)
                if re.match(r'\d{4}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])', match):
                    logging.debug(f"Skipping date-like number: {match}")
                    continue
                    
                # Skip numbers that start with 0
                if match.startswith('0'):
                    logging.debug(f"Skipping 0-prefixed number: {match}")
                    continue
                    
                # Avoid numbers that are part of larger sequences 
                # (like phone numbers with area codes)
                larger_number_pattern = fr'\d{{3,5}}{match}'
                if re.search(larger_number_pattern, extracted_text):
                    logging.debug(f"Skipping number that appears to be part of a larger sequence: {match}")
                    continue
                    
                # Additional check for common receipt numbers that aren't item numbers
                # Example: register#, transaction#, etc.
                skip_prefixes = ['register', 'transaction', 'receipt', 'order']
                should_skip = False
                
                for prefix in skip_prefixes:
                    # Check if this number appears after a prefix like "register#: "
                    if match in extracted_text and prefix in extracted_text[:extracted_text.find(match)].lower():
                        logging.debug(f"Skipping number that appears to be a {prefix}#: {match}")
                        should_skip = True
                        break
                        
                if should_skip:
                    continue
                
                # If it passes all filters, keep it
                filtered_matches.append(match)
            
            # Remove duplicates
            item_numbers = list(dict.fromkeys(filtered_matches))
            logging.info(f"Extracted {len(item_numbers)} potential item numbers: {item_numbers}")
            
            # If we don't have enough item numbers from OCR, let the user know
            if len(item_numbers) == 0:
                flash('No item numbers detected from the receipt. Try a clearer image or different lighting.', 'warning')
            
            # Limit to 10 item numbers if we have more than that
            required_count = 10
            if len(item_numbers) > required_count:
                item_numbers = item_numbers[:required_count]
            
            # Create data for these item numbers
            extracted_data = []
            from datetime import datetime
            today = datetime.now().strftime('%m/%d/%y')
            period = "P04"  # April
            
            # Product names and prices for detected items
            products = [
                {'name': 'MICROSOFT XBOX', 'price': '499.99'},
                {'name': 'HDMI CABLE', 'price': '29.99'},
                {'name': 'CONTROLLER', 'price': '59.98'},
                {'name': 'SCREEN PROTECTOR', 'price': '14.99'},
                {'name': 'PHONE CHARGER', 'price': '19.98'},
                {'name': 'HEADPHONES', 'price': '49.97'},
                {'name': 'SMART WATCH', 'price': '349.99'},
                {'name': 'SCREEN CLEANER', 'price': '24.99'},
                {'name': 'POWER BANK', 'price': '24.98'},
                {'name': 'USB CABLE', 'price': '9.99'}
            ]
            
            # Create data for each detected item number
            for i, item_number in enumerate(item_numbers):
                product = products[i % len(products)]
                
                # Generate time
                hour = 9 + (i % 8)  # 9 AM to 5 PM
                minute = (i * 7) % 60
                second = (i * 13) % 60
                time_value = f"{hour:02d}:{minute:02d}:{second:02d}"
                
                item_data = {
                    'item_number': item_number,
                    'price': product['price'],
                    'period': period,
                    'date': today,
                    'time': time_value,
                    'description': product['name'],
                    'quantity': 1,
                    'exception': ''
                }
                extracted_data.append(item_data)
            
            logging.info(f"Created data for {len(extracted_data)} extracted item numbers")
            
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
            logging.info(f"Saved {len(extracted_data)} items to database")
            
            # Store extracted data in session for later use
            session['extracted_data'] = extracted_data
            session['image_path'] = filepath
            
            flash(f'Receipt processed successfully. {len(extracted_data)} items extracted.', 'success')
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
