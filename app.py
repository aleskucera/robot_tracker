import os
import time
from threading import Lock

from dotenv import load_dotenv
from flask import Flask
from flask import jsonify
from flask import render_template
from flask import request
from flask_socketio import SocketIO  # This will manage the background task

# No longer need eventlet

INACTIVITY_TIMEOUT = 20  # 2 minutes

# --- Initialization ---
load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "a_default_secret_key_for_dev")
# This is the key: we are committing to the 'threading' model
socketio = SocketIO(app, async_mode="threading")

robots_data = {}
state_lock = Lock()
# ----------------------------------------------------


@app.route("/")
def index():
    api_key = os.getenv("THUNDERFOREST_API_KEY")
    return render_template("index.html", apikey=api_key)


@app.route("/api/update_data", methods=["POST"])
def update_data():
    """API endpoint for robots to post data. Handles initial registration and updates seamlessly."""
    data = request.get_json()

    # --- 1. Basic Validation ---
    if (
        not data
        or "robot_id" not in data
        or not isinstance(data.get("position"), dict)
        or "gps" not in data["position"]
        or "ekf" not in data["position"]
    ):
        print(f"ERROR: Invalid data received: {data}")
        return (
            jsonify({"status": "error", "message": "Invalid data structure."}),
            400,
        )

    robot_id = data["robot_id"]

    with state_lock:
        is_new_robot = robot_id not in robots_data

        # --- 2. Get or Create Robot State (Upsert Pattern) ---
        if is_new_robot:
            print(f"INFO: New robot online, creating state for: {robot_id}")
            # Initialize a full, default structure for the new robot
            robots_data[robot_id] = {
                "robot_id": robot_id,
                "mission": {},
                "position": {},
                "last_update": 0,
            }

        # --- 3. Update State from Payload ---
        # If the payload has a mission, overwrite the stored one.
        # This handles both initial registration and mission changes.
        if "mission" in data and isinstance(data.get("mission"), dict):
            if "waypoints" in data["mission"]:
                print(f"INFO: Updating mission/waypoints for robot: {robot_id}")
                robots_data[robot_id]["mission"] = data["mission"]

        # Gatekeeper: After updating, check if we have waypoints. If not, reject.
        if not robots_data[robot_id].get("mission", {}).get("waypoints"):
            return (
                jsonify(
                    {
                        "status": "waypoints_required",
                        "message": f"Mission waypoints for robot {robot_id} are missing.",
                    }
                ),
                202,
            )

        # Update position and timestamp
        robots_data[robot_id]["position"] = data["position"]
        robots_data[robot_id]["last_update"] = time.time()

        # Update waypoint classifications based on the *incoming* index
        current_waypoint_index = data.get("mission", {}).get("current_waypoint_index")
        if current_waypoint_index is not None:
            stored_waypoints = robots_data[robot_id]["mission"]["waypoints"]
            for i, wp in enumerate(stored_waypoints):
                if i < current_waypoint_index:
                    wp["classification"] = "completed"
                elif i == current_waypoint_index:
                    wp["classification"] = "current_goal"
                else:
                    wp["classification"] = "unfinished"
            # Ensure the stored index is also updated
            robots_data[robot_id]["mission"][
                "current_waypoint_index"
            ] = current_waypoint_index

        # Prepare a clean copy of the data to be sent
        updated_robot_payload = robots_data[robot_id].copy()

    # --- 4. Broadcast Updates ---
    # IMPORTANT: Emit 'new_robot_online' *only* for the new robot,
    # but emit 'robot_update' for all updates to keep all clients in sync.
    if is_new_robot:
        socketio.emit("new_robot_online", updated_robot_payload)

    # Always send a robot_update so that UI elements that depend on it
    # (like 'last seen') are refreshed for all connected clients.
    socketio.emit("robot_update", updated_robot_payload)

    return (
        jsonify({"status": "success", "message": f"Data for {robot_id} updated"}),
        200,
    )


@socketio.on("connect")
def handle_connect():
    print("Client connected")
    with state_lock:
        socketio.emit("initial_robot_states", robots_data, room=request.sid)


@socketio.on("disconnect")
def handle_disconnect():
    print("Client disconnected")


def cleanup_inactive_robots():
    """Background task to remove inactive robots."""
    print("--> Cleanup task started")
    while True:
        # Use a standard library sleep, as we are in a normal thread
        time.sleep(5)
        print("--- Cleanup task is running a check ---")

        now = time.time()
        with state_lock:
            # Add another print to show the state of the dictionary
            print(f"Current robots_data: {robots_data}")

            to_delete = [
                robot_id
                for robot_id, data in robots_data.items()
                if now - data.get("last_update", 0) > INACTIVITY_TIMEOUT
            ]
            for robot_id, data in robots_data.items():
                print(
                    f"Checking {robot_id}. Time since last update: {now - data.get('last_update', 0)}"
                )

            for robot_id in to_delete:
                print(f"INFO: Removing inactive robot: {robot_id}")
                del robots_data[robot_id]
                socketio.emit("robot_offline", {"robot_id": robot_id})


if __name__ == "__main__":
    # Use the official Flask-SocketIO method for background tasks.
    # This respects the async_mode you chose.
    socketio.start_background_task(target=cleanup_inactive_robots)
    socketio.run(app, debug=True, host="0.0.0.0", port=5001)
