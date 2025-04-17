import cv2
import pytesseract
import re
import logging
import os
import numpy as np
from datetime import datetime

def preprocess_image(image_path):
    """Preprocess the image for better OCR results."""
    # Read the image
    img = cv2.imread(image_path)
    
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Apply thresholding
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
    
    # Apply dilation and erosion to remove noise
    kernel = np.ones((1, 1), np.uint8)
    img_dilation = cv2.dilate(thresh, kernel, iterations=1)
    img_erosion = cv2.erode(img_dilation, kernel, iterations=1)
    
    # Invert back
    processed = cv2.bitwise_not(img_erosion)
    
    return processed

def process_image(image_path):
    """Process the image with OCR to extract text."""
    try:
        # Check if the image file exists
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")
            
        # Preprocess the image
        processed_img = preprocess_image(image_path)
        
        # Apply OCR
        extracted_text = pytesseract.image_to_string(processed_img)
        
        # Log the extracted text for debugging
        logging.debug(f"Extracted text from image: {extracted_text[:200]}...")
        
        return extracted_text
        
    except Exception as e:
        logging.error(f"Error in process_image: {str(e)}")
        raise e

def extract_data_from_text(text):
    """Extract structured data from OCR text."""
    items = []
    
    # Split text into lines
    lines = text.strip().split('\n')
    
    # Regular expressions for data extraction
    item_number_pattern = r'Item/Dept\s*:\s*(\d+)'
    description_pattern = r'Description\s*:\s*([A-Za-z0-9\s]+)'
    price_pattern = r'(\d+\.\d{2})'  # Matches prices like 499.99
    date_pattern = r'Date\s*:\s*(\d{2}/\d{2}/\d{2})'
    time_pattern = r'POS Time\s*:\s*(\d{2}:\d{2}:\d{2})'
    
    # For each line that seems to contain item data
    for i, line in enumerate(lines):
        # Check for lines that could contain item data
        if "Member#:" in line or "Operator ID:" in line:
            try:
                # Extract item details from the current line and surrounding lines
                item_data = {}
                
                # Look for item number and description
                item_match = re.search(r'(\d{6,8})', line)
                if item_match:
                    item_data['item_number'] = item_match.group(1)
                else:
                    # Try to find item number in surrounding lines
                    for offset in [-2, -1, 1, 2]:
                        if i + offset >= 0 and i + offset < len(lines):
                            item_match = re.search(r'(\d{6,8})', lines[i + offset])
                            if item_match:
                                item_data['item_number'] = item_match.group(1)
                                break
                
                # Look for price
                price_match = re.search(price_pattern, line)
                if price_match:
                    item_data['price'] = price_match.group(1)
                else:
                    # Try to find price in surrounding lines
                    for offset in [-2, -1, 1, 2]:
                        if i + offset >= 0 and i + offset < len(lines):
                            price_match = re.search(price_pattern, lines[i + offset])
                            if price_match:
                                item_data['price'] = price_match.group(1)
                                break
                
                # Look for date
                date_match = re.search(r'Date\s*:\s*(\d{2}/\d{2}/\d{2})', line)
                if not date_match:
                    date_match = re.search(r'(\d{2}/\d{2}/\d{2})', line)
                if date_match:
                    item_data['date'] = date_match.group(1)
                else:
                    # Try to find date in surrounding lines
                    for offset in [-2, -1, 1, 2]:
                        if i + offset >= 0 and i + offset < len(lines):
                            date_match = re.search(r'Date\s*:\s*(\d{2}/\d{2}/\d{2})', lines[i + offset])
                            if not date_match:
                                date_match = re.search(r'(\d{2}/\d{2}/\d{2})', lines[i + offset])
                            if date_match:
                                item_data['date'] = date_match.group(1)
                                break
                
                # Look for time
                time_match = re.search(r'POS Time\s*:\s*(\d{2}:\d{2}:\d{2})', line)
                if not time_match:
                    time_match = re.search(r'(\d{2}:\d{2}:\d{2})', line)
                if time_match:
                    item_data['time'] = time_match.group(1)
                else:
                    # Try to find time in surrounding lines
                    for offset in [-2, -1, 1, 2]:
                        if i + offset >= 0 and i + offset < len(lines):
                            time_match = re.search(r'POS Time\s*:\s*(\d{2}:\d{2}:\d{2})', lines[i + offset])
                            if not time_match:
                                time_match = re.search(r'(\d{2}:\d{2}:\d{2})', lines[i + offset])
                            if time_match:
                                item_data['time'] = time_match.group(1)
                                break
                
                # Only add if we have at least an item number and price
                if 'item_number' in item_data and 'price' in item_data:
                    # Add missing fields with empty values
                    for field in ['item_number', 'price', 'date', 'time']:
                        if field not in item_data:
                            item_data[field] = ''
                    
                    # Try to extract a description if available
                    desc_match = None
                    for offset in [-2, -1, 0, 1, 2]:
                        if i + offset >= 0 and i + offset < len(lines):
                            desc_line = lines[i + offset]
                            if "Description" in desc_line:
                                desc_parts = desc_line.split("Description")
                                if len(desc_parts) > 1:
                                    desc_match = desc_parts[1].strip()
                                    break
                    
                    if desc_match:
                        item_data['description'] = desc_match
                    else:
                        item_data['description'] = f"Item {item_data['item_number']}"
                    
                    items.append(item_data)
            except Exception as e:
                logging.error(f"Error extracting data from line {i}: {str(e)}")
                continue
    
    # If no items were found, try a different approach
    if not items:
        # Look for patterns like: ItemNumber Price Date Time
        pattern = r'(\d{6,8}).*?(\d+\.\d{2}).*?(\d{2}/\d{2}/\d{2}).*?(\d{2}:\d{2}:\d{2})'
        matches = re.findall(pattern, text)
        
        for match in matches:
            items.append({
                'item_number': match[0],
                'price': match[1],
                'date': match[2],
                'time': match[3],
                'description': f"Item {match[0]}"
            })
    
    logging.debug(f"Extracted {len(items)} items from text")
    return items
