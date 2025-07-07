import os
import time
from threading import Lock

import eventlet
from dotenv import load_dotenv
from flask import Flask
from flask import jsonify
from flask import render_template
from flask import request
from flask_socketio import SocketIO

INACTIVITY_TIMEOUT = 60  # 1 minute

# --- Initialization ---
load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "a_default_secret_key_for_dev")
socketio = SocketIO(app, async_mode="threading")

robots_data = {}
state_lock = Lock()
# ----------------------------------------------------


# --- Standard HTTP Routes ---
@app.route("/")
def index():
    api_key = os.getenv("THUNDERFOREST_API_KEY")
    return render_template("index.html", apikey=api_key)


@app.route("/api/update_data", methods=["POST"])
def update_data():
    """API endpoint for ANY robot to post its data."""
    data = request.get_json()
    # ** NEW: We now require a robot_id in the payload **
    if not data or "robot_id" not in data or "lat" not in data or "lon" not in data:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Invalid data, robot_id, lat, and lon are required",
                }
            ),
            400,
        )

    robot_id = data["robot_id"]
    is_new_robot = False

    with state_lock:
        if robot_id not in robots_data:
            is_new_robot = True

        robots_data[robot_id] = {
            "robot_id": robot_id,
            "location": {"lat": data["lat"], "lon": data["lon"]},
            "mission": data.get("mission", None),
            "last_update": time.time(),
        }

        # Get a copy of the updated data to send
        updated_robot_payload = robots_data[robot_id]

    # Broadcast the update for this specific robot
    socketio.emit("robot_update", updated_robot_payload)

    # If a new robot came online, send a special event so the UI can update the list
    if is_new_robot:
        socketio.emit("new_robot_online", updated_robot_payload)

    return (
        jsonify({"status": "success", "message": f"Data for {robot_id} updated"}),
        200,
    )


@socketio.on("connect")
def handle_connect():
    """When a new client connects, send them the state of ALL known robots."""
    print("Client connected")
    with state_lock:
        # Send the entire dictionary of robots to the newly connected client
        socketio.emit("initial_robot_states", robots_data, room=request.sid)


@socketio.on("disconnect")
def handle_disconnect():
    print("Client disconnected")


def cleanup_inactive_robots():
    while True:
        eventlet.sleep(2)  # Check every 10 seconds
        now = time.time()
        with state_lock:
            to_delete = [
                robot_id
                for robot_id, data in robots_data.items()
                if now - data["last_update"] > INACTIVITY_TIMEOUT
            ]
            for robot_id in to_delete:
                print(f"INFO: Removing inactive robot: {robot_id}")
                del robots_data[robot_id]
                socketio.emit("robot_offline", {"robot_id": robot_id})


if __name__ == "__main__":
    socketio.start_background_task(cleanup_inactive_robots)
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)
