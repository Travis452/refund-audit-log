from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class ReportItem(db.Model):
    __tablename__ = 'report_items'

    id = db.Column(db.Integer, primary_key=True)
    item_number = db.Column(db.String(50), nullable=False)
    department = db.Column(db.String(20))
    price = db.Column(db.String(20))
    period = db.Column(db.String(5))
    exception = db.Column(db.String(100))
    quantity = db.Column(db.Integer, default=1)
    additional_info = db.Column(db.String(200))
    original_description = db.Column(db.String(200))
    original_date = db.Column(db.String(20))
    original_time = db.Column(db.String(20))
    session_id = db.Column(db.String(50), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<ReportItem {self.item_number}>'

    def to_dict(self):
        return {col.name: getattr(self, col.name) for col in self.__table__.columns}

class ExportFile(db.Model):
    __tablename__ = 'export_files'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(50), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    export_type = db.Column(db.String(20), nullable=False)
    file_path = db.Column(db.String(500))
    sheet_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    item_count = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<ExportFile {self.filename}>'

    def to_dict(self):
        return {col.name: getattr(self, col.name) for col in self.__table__.columns}
