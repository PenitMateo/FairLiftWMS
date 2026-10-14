from flask import Flask, request, jsonify, send_from_directory, session
from config import Config
from models import db, User, Parcel, Ticket, Driver, Event
from flask_migrate import Migrate
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)
from flask_cors import CORS
from datetime import datetime, date
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
import os

# --- Flask app setup ---
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config.from_object(Config)

app.config.update(
    SECRET_KEY="supersecretkey",
    SESSION_COOKIE_SAMESITE=None,
    SESSION_COOKIE_SECURE=False
)
CORS(app, supports_credentials=True)

db.init_app(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Folder to store uploaded delivery photos
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Serve Pages ---
@app.route('/')
def index():
    return send_from_directory('static', 'Login.html')

@app.route('/page/<path:filename>')
def page(filename):
    return send_from_directory('static', filename)

# --- AUTH API ---
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        login_user(user)
        session.permanent = True
        return jsonify({"message": "Logged in", "username": user.username, "role": user.role})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/api/logout', methods=['POST'])
@login_required
def api_logout():
    logout_user()
    return jsonify({"message": "Logged out"})

# --- PARCELS API ---
@app.route('/api/parcels', methods=['GET'])
@login_required
def list_parcels():
    q = Parcel.query
    dest = request.args.get('destination')
    status = request.args.get('status')
    size = request.args.get('size')

    if dest:
        q = q.filter(Parcel.destination.ilike(f"%{dest}%"))
    if status:
        q = q.filter_by(status=status)
    if size:
        q = q.filter_by(size=size)

    parcels = q.order_by(Parcel.shipping_date.desc()).all()
    out = [ {
        "id": p.id,
        "tracking_number": p.tracking_number,
        "size": p.size,
        "weight": p.weight,
        "shipping_date": p.shipping_date.isoformat() if p.shipping_date else None,
        "destination": p.destination,
        "status": p.status,
        "location_rack": p.location_rack,
        "metadata": dict(p.metadata) if isinstance(p.metadata, dict) else {}
    } for p in parcels]
    return jsonify(out)

@app.route('/api/parcels/<int:parcel_id>/verification', methods=['POST'])
@login_required
def verify_parcel(parcel_id):
    p = Parcel.query.get_or_404(parcel_id)

    receiver = request.form.get("receiver_name")
    delivered_time = request.form.get("delivered_time")
    remarks = request.form.get("remarks")
    photo = request.files.get("photo")

    if not receiver or not delivered_time:
        return jsonify({"error": "Missing required fields"}), 400
    if not photo:
        return jsonify({"error": "Photo proof required"}), 400

    filename = secure_filename(photo.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    photo.save(filepath)

    p.status = "delivered"

    meta = p.metadata or {}
    meta.update({
        "receiver_name": receiver,
        "delivered_time": delivered_time,
        "remarks": remarks,
        "photo": filename
    })
    p.metadata = meta

    db.session.commit()
    return jsonify({"message": "Delivery verified successfully"}), 200

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# --- Add other parcel CRUD, archive, restore APIs here ---
# --- Add users, events, health APIs as in your previous code ---

@login_manager.unauthorized_handler
def unauthorized_callback():
    return jsonify({"error": "Unauthorized"}), 401

# --- Start App ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
