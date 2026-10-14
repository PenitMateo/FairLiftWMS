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
from werkzeug.security import generate_password_hash  # ✅ Added this import

# --- Flask app setup ---
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config.from_object(Config)

app.config.update(
    SECRET_KEY="supersecretkey",  # Change before production
    SESSION_COOKIE_SAMESITE=None,
    SESSION_COOKIE_SECURE=False
)
CORS(app, supports_credentials=True)

db.init_app(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Serve pages ---
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
    out = [{
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


@app.route('/api/parcels', methods=['POST'])
@login_required
def create_parcel():
    data = request.json
    if not data or not data.get('tracking_number'):
        return jsonify({"error": "tracking_number required"}), 400

    if Parcel.query.filter_by(tracking_number=data['tracking_number']).first():
        return jsonify({"error": "tracking_number already exists"}), 400

    p = Parcel(
        tracking_number=data['tracking_number'],
        size=data.get('size'),
        weight=data.get('weight'),
        shipping_date=(date.fromisoformat(data['shipping_date'])
                      if data.get('shipping_date') else None),
        destination=data.get('destination'),
        status=data.get('status', 'stored'),
        location_rack=data.get('location_rack'),
        metadata=data.get('metadata')
    )
    db.session.add(p)
    db.session.commit()
    return jsonify({"message": "created", "id": p.id}), 201


@app.route('/api/parcels/<int:parcel_id>', methods=['GET'])
@login_required
def get_parcel(parcel_id):
    p = Parcel.query.get_or_404(parcel_id)
    return jsonify({
        "id": p.id,
        "tracking_number": p.tracking_number,
        "size": p.size,
        "weight": p.weight,
        "shipping_date": p.shipping_date.isoformat() if p.shipping_date else None,
        "destination": p.destination,
        "status": p.status,
        "location_rack": p.location_rack,
        "metadata": p.metadata if isinstance(p.metadata, dict) else {}
    })


@app.route('/api/parcels/<int:parcel_id>', methods=['PUT', 'PATCH'])
@login_required
def update_parcel(parcel_id):
    """Update existing parcel details"""
    p = Parcel.query.get_or_404(parcel_id)
    data = request.get_json() or {}

    # Update only the fields provided
    if 'tracking_number' in data:
        existing = Parcel.query.filter_by(tracking_number=data['tracking_number']).first()
        if existing and existing.id != p.id:
            return jsonify({"error": "Tracking number already exists"}), 400
        p.tracking_number = data['tracking_number']

    if 'size' in data:
        p.size = data['size']
    if 'weight' in data:
        try:
            p.weight = float(data['weight'])
        except (TypeError, ValueError):
            return jsonify({"error": "Weight must be numeric"}), 400
    if 'shipping_date' in data:
        try:
            p.shipping_date = date.fromisoformat(data['shipping_date'])
        except ValueError:
            return jsonify({"error": "Invalid date format (use YYYY-MM-DD)"}), 400
    if 'destination' in data:
        p.destination = data['destination']
    if 'status' in data:
        p.status = data['status']
    if 'location_rack' in data:
        p.location_rack = data['location_rack']
    if 'metadata' in data and isinstance(data['metadata'], dict):
        p.metadata = data['metadata']

    db.session.commit()
    return jsonify({"message": "Parcel updated successfully", "id": p.id})


@app.route('/api/parcels/tracking/<tracking_number>', methods=['GET'])
@login_required
def get_parcel_by_tracking(tracking_number):
    p = Parcel.query.filter_by(tracking_number=tracking_number).first()
    if not p:
        return jsonify({"error": "Parcel not found"}), 404
    return jsonify({
        "id": p.id,
        "tracking_number": p.tracking_number,
        "size": p.size,
        "weight": p.weight,
        "shipping_date": p.shipping_date.isoformat() if p.shipping_date else None,
        "destination": p.destination,
        "status": p.status,
        "location_rack": p.location_rack,
        "metadata": p.metadata if isinstance(p.metadata, dict) else {}
    })


@app.route('/api/parcels/<int:parcel_id>', methods=['DELETE'])
@login_required
def delete_parcel(parcel_id):
    p = Parcel.query.get_or_404(parcel_id)
    db.session.delete(p)
    db.session.commit()
    return jsonify({"message": "deleted"})


# --- ARCHIVE / RESTORE API ---
@app.route('/api/parcels/<int:parcel_id>/archive', methods=['POST'])
@login_required
def archive_parcel(parcel_id):
    p = Parcel.query.get_or_404(parcel_id)
    if p.status == 'archived': return jsonify({"error":"Parcel already archived"}), 400
    p.status = 'archived'
    db.session.commit()
    return jsonify({"message": f"Parcel {p.tracking_number} archived successfully."})

@app.route('/api/parcels/<int:parcel_id>/restore', methods=['POST'])
@login_required
def restore_parcel(parcel_id):
    p = Parcel.query.get_or_404(parcel_id)
    if p.status != 'archived': return jsonify({"error":"Parcel is not archived"}), 400
    p.status = 'stored'
    db.session.commit()
    return jsonify({"message": f"Parcel {p.tracking_number} restored successfully."})

@app.route('/api/parcels/archived', methods=['GET'])
@login_required
def list_archived_parcels():
    parcels = Parcel.query.filter_by(status='archived').order_by(Parcel.shipping_date.desc()).all()
    out = [{
        "id": p.id,
        "tracking_number": p.tracking_number,
        "size": p.size,
        "weight": p.weight,
        "shipping_date": p.shipping_date.isoformat() if p.shipping_date else None,
        "destination": p.destination,
        "status": p.status,
        "location_rack": p.location_rack
    } for p in parcels]
    return jsonify(out)


# --- USER MANAGEMENT API ---
@app.route('/api/users', methods=['GET'])
@login_required
def list_users():
    users = User.query.all()
    return jsonify([{"id": u.id, "username": u.username, "role": u.role, "position": u.position} for u in users])

@app.route('/api/users', methods=['POST'])
@login_required
def create_user():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'admin')
    position = data.get('position', 'Administrator')
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username exists"}), 400
    user = User(username=username, role=role, position=position)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": f"User '{username}' added successfully"}), 201

@app.route('/api/users/<int:user_id>', methods=['PATCH'])
@login_required
def patch_user(user_id):
    data = request.json or {}
    user = User.query.get_or_404(user_id)

    if 'password' in data:
        user.password_hash = generate_password_hash(data['password'])
    if 'role' in data:
        user.role = data['role']
    if 'username' in data:
        user.username = data['username']
    if 'position' in data:
        user.position = data['position']
    db.session.commit()
    return jsonify(message="User updated successfully"), 200

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": f"User '{user.username}' deleted successfully"}), 200

# --- EVENTS API ---
@app.route('/api/events', methods=['GET'])
@login_required
def list_events():
    events = Event.query.filter_by(created_by=current_user.id).all()
    return jsonify([e.to_dict() for e in events])

@app.route('/api/events', methods=['POST'])
@login_required
def create_event():
    data = request.get_json() or {}
    title = data.get("title")
    start = data.get("start")
    end = data.get("end")
    description = data.get("description")

    if not title or not start:
        return jsonify({"error": "Title and start are required"}), 400

    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end) if end else start_dt
    except Exception:
        return jsonify({"error": "Invalid date format"}), 400

    e = Event(
        title=title,
        start=start_dt,
        end=end_dt,
        description=description,
        created_by=current_user.id
    )
    db.session.add(e)
    db.session.commit()
    return jsonify(e.to_dict()), 201

@app.route('/api/events/<int:event_id>', methods=['PUT'])
@login_required
def update_event(event_id):
    e = Event.query.get_or_404(event_id)
    if e.created_by != current_user.id:
        return jsonify({"error": "Not authorized"}), 403

    data = request.get_json() or {}
    if 'title' in data:
        e.title = data['title']
    if 'description' in data:
        e.description = data['description']
    if 'start' in data:
        e.start = datetime.fromisoformat(data['start'])
    if 'end' in data and data['end']:
        e.end = datetime.fromisoformat(data['end'])

    db.session.commit()
    return jsonify({"message": "Event updated", "id": e.id})

@app.route('/api/events/<int:event_id>', methods=['DELETE'])
@login_required
def delete_event(event_id):
    e = Event.query.get_or_404(event_id)
    if e.created_by != current_user.id:
        return jsonify({"error": "Not authorized"}), 403

    db.session.delete(e)
    db.session.commit()
    return jsonify({"message": "Event deleted"})

# --- Health route ---
@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})

@login_manager.unauthorized_handler
def unauthorized_callback():
    return jsonify({"error": "Unauthorized"}), 401

# --- Start app ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
