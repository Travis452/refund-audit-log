import os
import openpyxl
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import logging
import uuid
from datetime import datetime

def export_to_excel(data):
    """Export extracted data to Excel file."""
    try:
        # Create a new workbook and select the active worksheet
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Extracted Report Data"
        
        # Add headers
        headers = ['Item Number', 'Description', 'Price', 'Date', 'Time']
        for col_num, header in enumerate(headers, 1):
            ws.cell(row=1, column=col_num).value = header
        
        # Add data rows
        for row_num, item in enumerate(data, 2):
            ws.cell(row=row_num, column=1).value = item.get('item_number', '')
            ws.cell(row=row_num, column=2).value = item.get('description', '')
            ws.cell(row=row_num, column=3).value = item.get('price', '')
            ws.cell(row=row_num, column=4).value = item.get('date', '')
            ws.cell(row=row_num, column=5).value = item.get('time', '')
        
        # Make sure export directory exists
        export_dir = os.path.join('/tmp', 'exports')
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)
        
        # Save the workbook with a timestamp to avoid collisions
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"extracted_report_data_{timestamp}.xlsx"
        filepath = os.path.join(export_dir, filename)
        wb.save(filepath)
        
        logging.info(f"Data exported to Excel file: {filepath}")
        return filepath
    
    except Exception as e:
        logging.error(f"Error exporting to Excel: {str(e)}")
        raise e

def export_to_google_sheets(data):
    """Export extracted data to Google Sheets."""
    try:
        # Get Google Sheets credentials from environment or file
        credentials_json = os.environ.get('GOOGLE_CREDENTIALS')
        if not credentials_json:
            logging.warning("No Google credentials found in environment variables.")
            raise ValueError("Google Sheets credentials not found. Please check your configuration.")
        
        # Load credentials from JSON
        credentials_dict = json.loads(credentials_json)
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
        client = gspread.authorize(credentials)
        
        # Create a new spreadsheet
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        spreadsheet_title = f"OCR Report Data - {timestamp}"
        spreadsheet = client.create(spreadsheet_title)
        
        # Get the first sheet
        worksheet = spreadsheet.get_worksheet(0)
        
        # Add headers
        headers = ['Item Number', 'Description', 'Price', 'Date', 'Time']
        worksheet.append_row(headers)
        
        # Add data rows
        for item in data:
            row = [
                item.get('item_number', ''),
                item.get('description', ''),
                item.get('price', ''),
                item.get('date', ''),
                item.get('time', '')
            ]
            worksheet.append_row(row)
        
        # Make the spreadsheet publicly readable
        spreadsheet.share(None, perm_type='anyone', role='reader')
        
        logging.info(f"Data exported to Google Sheets: {spreadsheet.url}")
        return spreadsheet.url
    
    except Exception as e:
        logging.error(f"Error exporting to Google Sheets: {str(e)}")
        raise e
