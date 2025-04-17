from datetime import datetime
import json
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class ReportItem(db.Model):
    __tablename__ = 'report_items'
    
    id = db.Column(db.Integer, primary_key=True)
    item_number = db.Column(db.String(50), nullable=False)
    price = db.Column(db.String(20))
    period = db.Column(db.String(5))  # P01, P02, etc.
    exception = db.Column(db.String(100))
    quantity = db.Column(db.Integer, default=1)
    additional_info = db.Column(db.String(200))
    
    # Original OCR data for reference
    original_description = db.Column(db.String(200))
    original_date = db.Column(db.String(20))
    original_time = db.Column(db.String(20))
    
    # Batch/session info
    session_id = db.Column(db.String(50), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<ReportItem {self.item_number}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'item_number': self.item_number,
            'price': self.price,
            'period': self.period,
            'exception': self.exception,
            'quantity': self.quantity,
            'additional_info': self.additional_info,
            'original_description': self.original_description,
            'original_date': self.original_date,
            'original_time': self.original_time,
            'session_id': self.session_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class ExportFile(db.Model):
    __tablename__ = 'export_files'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(50), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    export_type = db.Column(db.String(20), nullable=False)  # 'excel' or 'google'
    file_path = db.Column(db.String(500))  # Local file path for Excel files
    sheet_url = db.Column(db.String(500))  # URL for Google Sheets
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    item_count = db.Column(db.Integer, default=0)
    
    def __repr__(self):
        return f'<ExportFile {self.filename}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'filename': self.filename,
            'export_type': self.export_type,
            'file_path': self.file_path,
            'sheet_url': self.sheet_url,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'item_count': self.item_count
        }