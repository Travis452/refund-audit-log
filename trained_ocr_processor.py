"""
Trained OCR Processor Module

This module uses training data to improve OCR accuracy for specific item numbers.
It leverages the training examples to better locate and identify item numbers in new receipts.
"""

import os
import cv2
import logging
import json
import re
import pytesseract
from PIL import Image
import numpy as np
from datetime import datetime
from receipt_trainer import ReceiptTrainer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
TRAINING_DATA_FILE = 'trained_item_locations.json'
# Set up specialized OCR config for item numbers
DEFAULT_CONFIG = '--psm 11 --oem 3 -c tessedit_char_whitelist=0123456789'
ITEM_NUMBER_CONFIG = '--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789'

class TrainedOCRProcessor:
    """OCR processor that leverages training data for better item number recognition"""
    
    def __init__(self, training_data_path=TRAINING_DATA_FILE):
        """Initialize with optional path to training data"""
        self.training_data_path = training_data_path
        self.training_data = self._load_training_data()
        
    def _load_training_data(self):
        """Load existing training data if available"""
        if os.path.exists(self.training_data_path):
            try:
                with open(self.training_data_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading training data: {str(e)}")
                return {"examples": [], "patterns": [], "regions": []}
        else:
            # Create initial structure
            return {"examples": [], "patterns": [], "regions": []}
    
    def get_trained_regions(self):
        """Get regions of interest from training data"""
        regions = self.training_data.get("regions", [])
        if not regions:
            # If no trained regions, focus on the left side of the image for item numbers
            return [
                {"name": "top_left", "location": {"top": 0, "left": 0, "width": 0.33, "height": 0.25}},
                {"name": "upper_middle_left", "location": {"top": 0.25, "left": 0, "width": 0.33, "height": 0.25}},
                {"name": "lower_middle_left", "location": {"top": 0.5, "left": 0, "width": 0.33, "height": 0.25}},
                {"name": "bottom_left", "location": {"top": 0.75, "left": 0, "width": 0.33, "height": 0.25}},
                # For completeness, also include the full width sections but with lower priority
                {"name": "full_top", "location": {"top": 0, "left": 0, "width": 1.0, "height": 0.25}},
                {"name": "full_upper_middle", "location": {"top": 0.25, "left": 0, "width": 1.0, "height": 0.25}},
                {"name": "full_lower_middle", "location": {"top": 0.5, "left": 0, "width": 1.0, "height": 0.25}},
                {"name": "full_bottom", "location": {"top": 0.75, "left": 0, "width": 1.0, "height": 0.25}}
            ]
        return regions
    
    def get_trained_patterns(self):
        """Get patterns from training data"""
        return self.training_data.get("patterns", [])
    
    def process_image(self, image_path):
        """
        Process receipt image using trained data to extract item numbers
        
        Args:
            image_path: Path to receipt image
            
        Returns:
            List of extracted item numbers
        """
        if not os.path.exists(image_path):
            logger.error(f"Image file not found: {image_path}")
            return []
            
        try:
            # Read image
            img = cv2.imread(image_path, 0)  # Grayscale
            
            if img is None:
                logger.error("Failed to read image")
                return []
                
            # Get image dimensions
            height, width = img.shape
            
            # Get trained regions
            regions = self.get_trained_regions()
            
            # Extract text from each region
            potential_numbers = []
            
            for region in regions:
                region_name = region.get("name", "unknown")
                location = region.get("location", {})
                
                # Convert relative coordinates to absolute
                top = int(location.get("top", 0) * height)
                left = int(location.get("left", 0) * width)
                region_width = int(location.get("width", 1.0) * width)
                region_height = int(location.get("height", 1.0) * height)
                
                # Override to focus on left side of the receipt for item numbers
                if "left" not in location:
                    # If not explicitly defined, focus on the left third of the width
                    left = 0
                    region_width = int(width * 0.33)  # Just the left third of the receipt
                
                # Ensure coordinates are within image bounds
                top = max(0, min(top, height - 1))
                left = max(0, min(left, width - 1))
                region_width = max(1, min(region_width, width - left))
                region_height = max(1, min(region_height, height - top))
                
                # Extract region of interest
                roi = img[top:top+region_height, left:left+region_width]
                
                # Process this region with specialized config for item numbers
                text = pytesseract.image_to_string(roi, config=ITEM_NUMBER_CONFIG)
                
                # Extract potential item numbers based on trained patterns
                patterns = self.get_trained_patterns()
                item_numbers = self._extract_numbers_with_patterns(text, patterns)
                
                for number in item_numbers:
                    potential_numbers.append({
                        "item_number": number,
                        "region": region_name,
                        "confidence": 0.9  # Higher confidence for numbers matching trained patterns
                    })
                
                # Look for 7-digit numbers as potential item numbers (common format)
                seven_digit_numbers = re.findall(r'\b\d{7}\b', text)
                for number in seven_digit_numbers:
                    if number not in [x["item_number"] for x in potential_numbers]:
                        potential_numbers.append({
                            "item_number": number,
                            "region": region_name,
                            "confidence": 0.8  # Higher confidence for 7-digit numbers
                        })
                
                # Also look for any 6-12 digit numbers as potential item numbers (but with lower confidence)
                generic_numbers = re.findall(r'\b\d{6,12}\b', text)
                for number in generic_numbers:
                    if number not in [x["item_number"] for x in potential_numbers]:
                        potential_numbers.append({
                            "item_number": number,
                            "region": region_name,
                            "confidence": 0.5  # Lower confidence for generic matches
                        })
            
            # If we found numbers in trained regions, return them sorted by confidence
            if potential_numbers:
                # Sort by confidence (descending)
                sorted_numbers = sorted(potential_numbers, key=lambda x: x["confidence"], reverse=True)
                
                # Return unique numbers
                unique_numbers = []
                seen = set()
                for item in sorted_numbers:
                    number = item["item_number"]
                    if number not in seen:
                        seen.add(number)
                        unique_numbers.append(item)
                
                return unique_numbers
            
            # If we didn't find any numbers in trained regions, fall back to left side of image only
            logger.info("No item numbers found in trained regions, falling back to left side scan")
            
            # Extract just the left third of the image for item numbers
            left_region_width = int(width * 0.33)
            left_region = img[:, 0:left_region_width]
            
            # Process with specialized config for item numbers
            left_text = pytesseract.image_to_string(left_region, config=ITEM_NUMBER_CONFIG)
            
            # First look for 7-digit numbers (likely item numbers)
            seven_digit_numbers = re.findall(r'\b\d{7}\b', left_text)
            result_items = [{"item_number": num, "region": "left_side", "confidence": 0.7} for num in seven_digit_numbers]
            
            # Then include any other 6-12 digit numbers with lower confidence
            if not seven_digit_numbers:
                generic_numbers = re.findall(r'\b\d{6,12}\b', left_text)
                # Filter out numbers we already found
                generic_numbers = [num for num in generic_numbers if num not in seven_digit_numbers]
                result_items.extend([{"item_number": num, "region": "left_side", "confidence": 0.3} for num in generic_numbers])
            
            return result_items
            
        except Exception as e:
            logger.error(f"Error processing image with trained OCR: {str(e)}")
            return []
    
    def _extract_numbers_with_patterns(self, text, patterns):
        """
        Extract item numbers from text based on trained patterns
        
        Args:
            text: Extracted text from OCR
            patterns: List of pattern dictionaries
            
        Returns:
            List of potential item numbers
        """
        if not text or not patterns:
            return []
            
        potential_numbers = []
        
        # First, look specifically for 7-digit numbers (common item number format)
        seven_digit_matches = re.findall(r'\b\d{7}\b', text)
        potential_numbers.extend(seven_digit_matches)
        
        # Then look for other 6-12 digit numbers excluding the 7-digit ones we already found
        all_matches = re.findall(r'\b\d{6,12}\b', text)
        other_matches = [num for num in all_matches if num not in seven_digit_matches and len(num) != 7]
        potential_numbers.extend(other_matches)
        
        # Then apply each pattern
        for pattern in patterns:
            pattern_type = pattern.get("type", "")
            pattern_value = pattern.get("value", "")
            
            if not pattern_value:
                continue
                
            if pattern_type == "prefix":
                # Look for numbers that follow this prefix
                prefix_pattern = f"{re.escape(pattern_value)}\\s*([\\d]+)"
                prefix_matches = re.findall(prefix_pattern, text)
                for match in prefix_matches:
                    if 6 <= len(match) <= 12:  # Only consider numbers of valid length
                        potential_numbers.append(match)
                        
            elif pattern_type == "suffix":
                # Look for numbers that precede this suffix
                suffix_pattern = f"([\\d]+)\\s*{re.escape(pattern_value)}"
                suffix_matches = re.findall(suffix_pattern, text)
                for match in suffix_matches:
                    if 6 <= len(match) <= 12:
                        potential_numbers.append(match)
        
        # Return unique numbers
        return list(set(potential_numbers))


def process_with_training(image_path):
    """
    Process a receipt image using training data
    
    Args:
        image_path: Path to receipt image
        
    Returns:
        List of item data dictionaries
    """
    processor = TrainedOCRProcessor()
    results = processor.process_image(image_path)
    
    # Convert results to the expected format
    item_data = []
    for result in results:
        item_number = result.get("item_number", "")
        
        # Skip if no item number
        if not item_number:
            continue
            
        # Create item data entry
        data = {
            "item_number": item_number,
            "price": "0.00",  # Default price
            "date": datetime.now().strftime('%m/%d/%y'),
            "time": datetime.now().strftime('%H:%M:%S'),
            "description": f"Region: {result.get('region', 'unknown')}",
            "confidence": result.get("confidence", 0.0)
        }
        
        # Extract period from date
        month = data["date"].split('/')[0]
        if month.isdigit():
            data["period"] = f"P{month.zfill(2)}"
        else:
            data["period"] = "P00"
            
        item_data.append(data)
    
    return item_data