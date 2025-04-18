"""
Receipt Number Location Trainer

This module allows training for specific item number locations in receipts.
The training data helps the OCR process focus on the right regions and patterns.
"""

import os
import json
import logging
import cv2
import numpy as np
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
TRAINING_DATA_FILE = 'trained_item_locations.json'

class ReceiptTrainer:
    """Train the system to recognize specific patterns and locations for item numbers"""
    
    def __init__(self, training_data_path=TRAINING_DATA_FILE):
        """Initialize the trainer with optional path to training data"""
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
                return {"examples": [], "patterns": [], "regions": [], "created_at": datetime.now().isoformat()}
        else:
            # Create initial structure
            return {"examples": [], "patterns": [], "regions": [], "created_at": datetime.now().isoformat()}
    
    def save_training_data(self):
        """Save training data to file"""
        try:
            with open(self.training_data_path, 'w') as f:
                json.dump(self.training_data, f, indent=2)
            logger.info(f"Training data saved to {self.training_data_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving training data: {str(e)}")
            return False
    
    def add_example(self, item_number, image_path, description=None):
        """
        Add an example of an item number with associated image
        
        Args:
            item_number: The correct item number to identify
            image_path: Path to the receipt image containing this number
            description: Optional description of the receipt
        """
        if not os.path.exists(image_path):
            logger.error(f"Image file not found: {image_path}")
            return False
        
        try:
            # Store example
            example = {
                "item_number": item_number,
                "image_path": image_path,
                "description": description or f"Example for {item_number}",
                "added_at": datetime.now().isoformat()
            }
            
            # Add to training data
            self.training_data["examples"].append(example)
            logger.info(f"Added example for item number: {item_number}")
            
            # Save updated training data
            return self.save_training_data()
            
        except Exception as e:
            logger.error(f"Error adding example: {str(e)}")
            return False
    
    def add_pattern(self, pattern_type, pattern_value):
        """
        Add a pattern to help identify item numbers
        
        Args:
            pattern_type: Type of pattern (prefix, suffix, format, etc.)
            pattern_value: The pattern value (regex or text)
        """
        try:
            pattern = {
                "type": pattern_type,
                "value": pattern_value,
                "added_at": datetime.now().isoformat()
            }
            
            self.training_data["patterns"].append(pattern)
            logger.info(f"Added pattern {pattern_type}: {pattern_value}")
            
            return self.save_training_data()
            
        except Exception as e:
            logger.error(f"Error adding pattern: {str(e)}")
            return False
    
    def add_region(self, region_name, region_location):
        """
        Add a region of interest for finding item numbers
        
        Args:
            region_name: Name of the region (top, middle, custom, etc.)
            region_location: Dict with relative coordinates (e.g. {"top": 0.1, "left": 0.2, "width": 0.6, "height": 0.2})
        """
        try:
            region = {
                "name": region_name,
                "location": region_location,
                "added_at": datetime.now().isoformat()
            }
            
            self.training_data["regions"].append(region)
            logger.info(f"Added region {region_name}")
            
            return self.save_training_data()
            
        except Exception as e:
            logger.error(f"Error adding region: {str(e)}")
            return False
    
    def get_training_summary(self):
        """Get a summary of the training data"""
        return {
            "example_count": len(self.training_data["examples"]),
            "pattern_count": len(self.training_data["patterns"]),
            "region_count": len(self.training_data["regions"]),
            "created_at": self.training_data.get("created_at", "Unknown"),
            "last_updated": self.training_data["examples"][-1]["added_at"] if self.training_data["examples"] else "Never"
        }
    
    def analyze_receipt_for_training(self, image_path, item_number):
        """
        Analyze a receipt to determine where the known item number is located
        This helps establish patterns for future receipt processing
        
        Args:
            image_path: Path to the receipt image
            item_number: The known item number to locate
        
        Returns:
            Dict with analysis results
        """
        if not os.path.exists(image_path):
            return {"success": False, "error": "Image file not found"}
            
        try:
            # Read the image
            img = cv2.imread(image_path, 0)  # Grayscale
            
            if img is None:
                return {"success": False, "error": "Could not read image"}
                
            # Get image dimensions
            height, width = img.shape
            
            # Try to find the item number in the image
            # For each region, we'll create a mask and check if item number is there
            regions = [
                {"name": "top", "coords": (0, 0, width, int(height * 0.25))},
                {"name": "upper_middle", "coords": (0, int(height * 0.25), width, int(height * 0.5))},
                {"name": "lower_middle", "coords": (0, int(height * 0.5), width, int(height * 0.75))},
                {"name": "bottom", "coords": (0, int(height * 0.75), width, height)}
            ]
            
            region_results = []
            
            import pytesseract
            for region in regions:
                x, y, w, h = region["coords"]
                roi = img[y:y+h, x:x+w]
                
                # Extract text from this region
                config = '--psm 11 --oem 3'
                text = pytesseract.image_to_string(roi, config=config)
                
                # Check if item number is in this region
                is_present = item_number in text.replace(" ", "").replace("\n", "")
                
                region_result = {
                    "region": region["name"],
                    "contains_item_number": is_present,
                    "relative_coords": {
                        "top": y / height,
                        "left": x / width,
                        "width": w / width,
                        "height": h / height
                    }
                }
                
                region_results.append(region_result)
                
                if is_present:
                    # Auto-add this region to training data
                    self.add_region(
                        f"auto_{region['name']}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        region_result["relative_coords"]
                    )
            
            # Look for patterns like prefixes or common formatting
            # Check characters before and after the item number
            digit_config = '--psm 11 --oem 3'
            all_text = pytesseract.image_to_string(img, config=digit_config)
            
            # Try to find the context around the item number
            patterns = []
            for line in all_text.split('\n'):
                if item_number in line.replace(" ", ""):
                    # Found the line containing the item number
                    clean_line = line.replace(" ", "")
                    idx = clean_line.find(item_number)
                    
                    # Extract characters before and after (if any)
                    chars_before = clean_line[:idx][-3:] if idx > 0 else ""
                    chars_after = clean_line[idx+len(item_number):][:3] if idx + len(item_number) < len(clean_line) else ""
                    
                    if chars_before:
                        pattern = {
                            "type": "prefix",
                            "value": chars_before,
                            "context": line
                        }
                        patterns.append(pattern)
                        
                        # Auto-add this pattern to training data
                        self.add_pattern("prefix", chars_before)
                        
                    if chars_after:
                        pattern = {
                            "type": "suffix",
                            "value": chars_after,
                            "context": line
                        }
                        patterns.append(pattern)
                        
                        # Auto-add this pattern to training data
                        self.add_pattern("suffix", chars_after)
            
            # Add this example to training data
            self.add_example(item_number, image_path, "Auto-analyzed example")
            
            return {
                "success": True,
                "item_number": item_number,
                "regions": region_results,
                "patterns": patterns,
                "dimensions": {"height": height, "width": width}
            }
                
        except Exception as e:
            logger.error(f"Error analyzing receipt: {str(e)}")
            return {"success": False, "error": str(e)}


def train_from_examples(examples):
    """
    Train the system with a list of examples
    
    Args:
        examples: List of dicts with {item_number, image_path, description}
    
    Returns:
        Summary of training results
    """
    trainer = ReceiptTrainer()
    results = []
    
    for example in examples:
        item_number = example.get("item_number")
        image_path = example.get("image_path")
        description = example.get("description")
        
        if not item_number or not image_path:
            results.append({
                "success": False,
                "error": "Missing item_number or image_path",
                "example": example
            })
            continue
            
        # Add the example
        success = trainer.add_example(item_number, image_path, description)
        
        if success:
            # Analyze the receipt to learn patterns and regions
            analysis = trainer.analyze_receipt_for_training(image_path, item_number)
            results.append({
                "success": True,
                "item_number": item_number,
                "analysis": analysis
            })
        else:
            results.append({
                "success": False,
                "item_number": item_number,
                "error": "Failed to add example"
            })
    
    return {
        "examples_processed": len(examples),
        "successful": sum(1 for r in results if r.get("success", False)),
        "training_summary": trainer.get_training_summary(),
        "results": results
    }


if __name__ == "__main__":
    # Example usage
    trainer = ReceiptTrainer()
    print("Training system initialized.")