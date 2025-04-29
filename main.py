import logging
import os
from flask import Flask
from models import db

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "refund_audit_log_secret_key")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///auditlog.db"
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

print(">>> SQLAlchemy will use:", os.path.abspath("auditlog.db"))

db.init_app(app)

with app.app_context():
    db.create_all()

# Import after app setup to avoid circular imports
from app import *

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    app.run(host="0.0.0.0", port=5000, debug=True)
