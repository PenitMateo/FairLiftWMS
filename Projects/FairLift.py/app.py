from flask import Flask, request, jsonify, send_from_directory, session
from config import Config
from models import db, User, Parcel, Ticket, Driver
from flask_migrate import Migrate
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)
from flask_cors import CORS
from datetime import datetime, date

# --- Flask app setup ---
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config.from_object(Config)

# --- Ensure session & CORS settings ---
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


# -------------------- Serve Pages --------------------
@app.route('/')
def index():
    return send_from_directory('static', 'Login.html')


@app.route('/page/<path:filename>')
def page(filename):
    return send_from_directory('static', filename)


# -------------------- AUTH --------------------
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
        return jsonify({
            "message": "Logged in",
            "username": user.username,
            "role": user.role
        })
    return jsonify({"error": "Invalid credentials"}), 401


@app.route('/api/logout', methods=['POST'])
@login_required
def api_logout():
    logout_user()
    return jsonify({"message": "Logged out"})


# -------------------- PARCELS --------------------
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

    parcels = q.order_by(Parcel.arrival_date.desc()).all()
    out = [{
        "id": p.id,
        "tracking_number": p.tracking_number,
        "size": p.size,
        "weight": p.weight,
        "arrival_date": p.arrival_date.isoformat() if p.arrival_date else None,
        "destination": p.destination,
        "status": p.status,
        "location_rack": p.location_rack,
        "metadata": p.extra_data or {}
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
        arrival_date=(date.fromisoformat(data['arrival_date'])
                      if data.get('arrival_date') else None),
        destination=data.get('destination'),
        status=data.get('status', 'stored'),
        location_rack=data.get('location_rack'),
        extra_data=data.get('metadata')
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
        "arrival_date": p.arrival_date.isoformat() if p.arrival_date else None,
        "destination": p.destination,
        "status": p.status,
        "location_rack": p.location_rack,
        "metadata": p.extra_data or {}
    })


@app.route('/api/parcels/tracking/<tracking_number>', methods=['GET'])
@login_required
def get_parcel_by_tracking(tracking_number):
    """Get parcel details using its tracking number"""
    p = Parcel.query.filter_by(tracking_number=tracking_number).first()
    if not p:
        return jsonify({"error": "Parcel not found"}), 404

    # Use 'from' = warehouse, 'to' = destination for your Driver Dashboard
    from_location = "Las Piñas Warehouse"
    to_location = p.destination or "Unknown Destination"

    return jsonify({
        "id": p.id,
        "tracking_number": p.tracking_number,
        "from": from_location,
        "to": to_location,
        "status": p.status,
        "size": p.size,
        "weight": p.weight,
        "metadata": p.extra_data or {}
    })


@app.route('/api/parcels/<int:parcel_id>', methods=['DELETE'])
@login_required
def delete_parcel(parcel_id):
    p = Parcel.query.get_or_404(parcel_id)
    db.session.delete(p)
    db.session.commit()
    return jsonify({"message": "deleted"})


# -------------------- DRIVER AUTO-LOAD --------------------
@app.route('/api/driver/assigned', methods=['GET'])
@login_required
def driver_assigned_parcel():
    """Return the parcel assigned to the currently logged-in driver"""
    driver = Driver.query.filter_by(user_id=current_user.id).first()
    if not driver:
        return jsonify({"error": "No driver account linked"}), 404

    assigned = Parcel.query.filter_by(driver_id=driver.id, status="assigned").first()
    if not assigned:
        return jsonify({"error": "No assigned parcel"}), 404

    return jsonify({
        "id": assigned.id,
        "tracking_number": assigned.tracking_number,
        "from": "Las Piñas Warehouse",
        "to": assigned.destination,
        "status": assigned.status,
        "metadata": assigned.extra_data or {}
    })


# -------------------- Health Check --------------------
@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})


# -------------------- Unauthorized handler --------------------
@login_manager.unauthorized_handler
def unauthorized_callback():
    return jsonify({"error": "Unauthorized"}), 401


# -------------------- Main --------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
