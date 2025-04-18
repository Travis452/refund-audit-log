import os
import uuid
import logging
import signal
from werkzeug.utils import secure_filename

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import the various OCR methods
from ocr_processor import process_image, extract_data_from_text, extract_item_numbers_direct, process_quick

# Custom timeout exception
class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("Processing timed out")

def process_receipt_image(file, app, temp_dir="/tmp"):
    """
    Comprehensive receipt processing using multiple strategies
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
        
        # Set timeout for processing (60 seconds)
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(60)
        
        try:
            # First try OpenAI Vision API (if available)
            try:
                from ai_processor import extract_item_numbers_with_ai
                logger.info("Attempting AI-powered OCR extraction...")
                
                ai_results = extract_item_numbers_with_ai(filepath)
                
                if ai_results and len(ai_results) > 0:
                    logger.info(f"AI successfully extracted {len(ai_results)} items")
                    
                    # Format items to standardized format
                    processed_data = []
                    current_month = int(os.popen('date +%m').read().strip())
                    period = f"P{current_month:02d}"
                    
                    for item in ai_results:
                        # Ensure we have the minimum required fields
                        processed_item = {
                            'item_number': item.get('item_number', ''),
                            'price': item.get('price', '0.00'),
                            'period': period,
                            'date': item.get('date', ''),
                            'time': item.get('time', ''),
                            'description': '',
                            'quantity': 1,
                            'exception': ''
                        }
                        processed_data.append(processed_item)
                    
                    signal.alarm(0)  # Cancel timeout
                    return True, processed_data
                    
            except ImportError:
                logger.warning("AI processor module not available, skipping AI extraction")
            except Exception as ai_error:
                logger.error(f"AI extraction error: {str(ai_error)}")
            
            # Next try direct item number extraction method
            logger.info("Attempting direct item number extraction...")
            direct_results = extract_item_numbers_direct(filepath)
            
            if direct_results and len(direct_results) > 0:
                logger.info(f"Direct extraction found {len(direct_results)} items")
                
                # Process and format the direct extraction results into our standard format
                processed_data = []
                current_month = int(os.popen('date +%m').read().strip())
                period = f"P{current_month:02d}"
                
                for item_number in direct_results:
                    item_data = {
                        'item_number': item_number,
                        'price': '0.00',
                        'period': period,
                        'date': '',
                        'time': '',
                        'description': '',
                        'quantity': 1,
                        'exception': ''
                    }
                    processed_data.append(item_data)
                
                signal.alarm(0)  # Cancel timeout
                return True, processed_data
            
            # Next try standard OCR
            logger.info("Attempting standard OCR processing...")
            extracted_text = process_image(filepath)
            
            if extracted_text and not (isinstance(extracted_text, str) and "Error" in extracted_text):
                # Extract structured data
                extracted_data = extract_data_from_text(extracted_text)
                
                if extracted_data and len(extracted_data) > 0:
                    logger.info(f"Standard OCR found {len(extracted_data)} items")
                    signal.alarm(0)  # Cancel timeout
                    return True, extracted_data
            
            # Last resort - quick OCR
            logger.info("Attempting quick OCR as last resort...")
            quick_text = process_quick(filepath)
            
            if quick_text and not quick_text.startswith("Error:"):
                # Try to extract data from quick text
                quick_data = extract_data_from_text(quick_text)
                
                if quick_data and len(quick_data) > 0:
                    logger.info(f"Quick OCR found {len(quick_data)} items")
                    signal.alarm(0)  # Cancel timeout  
                    return True, quick_data
            
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
        # Clean up the file regardless of success or failure
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as cleanup_error:
            logger.error(f"Error cleaning up temporary file: {str(cleanup_error)}")