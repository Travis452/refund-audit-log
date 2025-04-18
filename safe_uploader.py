"""
Safe uploader module that avoids pytesseract completely but uses AI.
This version focuses on extracting real data using OpenAI Vision API
and only falls back to direct processing as a last resort.
"""

import os
import uuid
import logging
import signal
from werkzeug.utils import secure_filename
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import our AI processor and direct processor as fallback
from ai_processor import extract_item_numbers_with_ai
from direct_processor import direct_process

# Custom timeout exception
class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("Processing timed out")

def process_receipt_image_safe(file, app, temp_dir="/tmp"):
    """
    Safe receipt processing that doesn't use pytesseract.
    Returns: tuple of (success_status, data or error_message)
    """
    if not file or file.filename == '':
        return False, "No file selected"
    
    # Generate a unique filename
    filename = f"{uuid.uuid4()}_{secure_filename(file.filename)}"
    filepath = os.path.join(temp_dir, filename)
    
    try:
        # Save the file
        file.save(filepath)
        
        # Check if file saved properly
        if not os.path.exists(filepath):
            return False, "File failed to save"
        
        file_size = os.path.getsize(filepath)
        if file_size == 0:
            return False, "Saved file is empty (0 bytes)"
            
        logger.info(f"Processing receipt image: {filename}, size: {file_size} bytes")
        
        # Set timeout for processing (30 seconds)
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(30)
        
        try:
            # Try AI processing first (OpenAI Vision API)
            try:
                logger.info("Attempting to process with OpenAI Vision API")
                ai_results = extract_item_numbers_with_ai(filepath)
                
                if ai_results and len(ai_results) > 0:
                    logger.info(f"AI processing succeeded with {len(ai_results)} items")
                    
                    # Format AI results to standard format
                    processed_data = []
                    current_month = datetime.now().month
                    period = f"P{current_month:02d}"
                    
                    for item in ai_results:
                        item_data = {
                            'item_number': item.get('item_number', ''),
                            'price': item.get('price', '0.00'),
                            'period': period,
                            'date': item.get('date', ''),
                            'time': item.get('time', ''),
                            'description': item.get('description', 'AI Extracted'),
                            'quantity': 1,
                            'exception': ''
                        }
                        processed_data.append(item_data)
                    
                    signal.alarm(0)  # Cancel timeout
                    return True, processed_data
            except Exception as ai_error:
                logger.error(f"AI processing failed: {str(ai_error)}")
                # Continue to fallback methods
            
            # Fallback to direct processing if AI failed
            logger.info("AI processing failed, falling back to direct processing")
            safe_results = direct_process(filepath)
            
            if safe_results and len(safe_results) > 0:
                logger.info(f"Direct processing succeeded with {len(safe_results)} items")
                
                # Format direct results to standard format
                processed_data = []
                current_month = datetime.now().month
                period = f"P{current_month:02d}"
                
                for item in safe_results:
                    item_data = {
                        'item_number': item.get('item_number', ''),
                        'price': item.get('price', '0.00'),
                        'period': period,
                        'date': item.get('date', ''),
                        'time': item.get('time', ''),
                        'description': 'Emergency fallback - No OCR/AI data available',
                        'quantity': 1,
                        'exception': 'Failed to extract with primary methods'
                    }
                    processed_data.append(item_data)
                
                signal.alarm(0)  # Cancel timeout
                return True, processed_data
            
            # If we got here, no extraction method worked
            signal.alarm(0)  # Cancel timeout
            return False, "No item numbers could be extracted from the image"
            
        except TimeoutException:
            logger.error("Processing timed out")
            return False, "Processing timed out. Please try a clearer image or smaller file"
        finally:
            # Ensure alarm is canceled even if an error occurs
            signal.alarm(0)  
    
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        return False, f"Error processing file: {str(e)}"
    finally:
        # Keep the file for debugging - don't delete it
        try:
            if os.path.exists(filepath):
                logger.info(f"Preserving uploaded file for debugging: {filepath}")
                # Don't remove the file so we can inspect it
        except Exception as cleanup_error:
            logger.error(f"Error accessing temporary file: {str(cleanup_error)}")