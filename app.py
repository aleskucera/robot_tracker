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

INACTIVITY_TIMEOUT = 300  # 5 minutes

# --- Initialization ---
load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "a_default_secret_key_for_dev")
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
    """API endpoint for robots to post data with GPS (mandatory) and EKF (optional) positions."""
    data = request.get_json()

    # --- REFINED VALIDATION ---
    # Check for robot_id and a valid, mandatory 'gps' object.
    if (
        not data
        or "robot_id" not in data
        or not isinstance(data.get("position"), dict)
        or "lat" not in data["position"]["gps"]
        or "lon" not in data["position"]["gps"]
        or "lat" not in data["position"]["ekf"]
        or "lon" not in data["position"]["ekf"]
    ):
        print(f"ERROR: Invalid data received: {data}")
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Invalid data. 'robot_id' and correct 'position' with 'gps' and 'ekf' are required.",
                }
            ),
            400,
        )

    robot_id = data["robot_id"]
    is_new_robot_on_map = False

    with state_lock:
        is_new_robot_on_map = robot_id not in robots_data
        mission_payload = data.get("mission") or {}
        has_waypoints_in_payload = "waypoints" in mission_payload and isinstance(
            mission_payload.get("waypoints"), list
        )

        # 1. Handle mission registration or overwrite.
        if has_waypoints_in_payload:
            if is_new_robot_on_map:
                print(f"INFO: Registering new mission for robot: {robot_id}")
                robots_data[robot_id] = {
                    "robot_id": robot_id,
                    "mission": {},
                }  # Initialize structure
            else:
                print(f"INFO: Overwriting mission for existing robot: {robot_id}")

            robots_data[robot_id]["mission"]["waypoints"] = mission_payload["waypoints"]
            robots_data[robot_id]["mission"].pop("current_waypoint_index", None)

        # 2. Check if the mission is known.
        mission_is_known = robot_id in robots_data and "waypoints" in robots_data[
            robot_id
        ].get("mission", {})
        if not mission_is_known:
            return (
                jsonify(
                    {
                        "status": "waypoints_required",
                        "message": f"Mission waypoints for robot {robot_id} are missing.",
                    }
                ),
                202,
            )

        # 3. Perform the regular update.
        # Overwrite the entire position object with the new data from the payload.
        robots_data[robot_id]["position"] = data.get("position", {})
        robots_data[robot_id]["last_update"] = time.time()

        # Handle waypoint classification based on index
        current_waypoint_index = mission_payload.get("current_waypoint_index")
        if current_waypoint_index is not None:
            stored_waypoints = robots_data[robot_id]["mission"]["waypoints"]
            for i, wp in enumerate(stored_waypoints):
                if i < current_waypoint_index:
                    wp["classification"] = "completed"
                elif i == current_waypoint_index:
                    wp["classification"] = "current_goal"
                else:
                    wp["classification"] = "unfinished"
            robots_data[robot_id]["mission"][
                "current_waypoint_index"
            ] = current_waypoint_index

        updated_robot_payload = robots_data[robot_id].copy()

    # Broadcast updates
    socketio.emit("robot_update", updated_robot_payload)
    if is_new_robot_on_map:
        socketio.emit("new_robot_online", updated_robot_payload)

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
    while True:
        eventlet.sleep(10)
        now = time.time()
        with state_lock:
            to_delete = [
                robot_id
                for robot_id, data in robots_data.items()
                if now - data.get("last_update", 0) > INACTIVITY_TIMEOUT
            ]
            for robot_id in to_delete:
                print(f"INFO: Removing inactive robot: {robot_id}")
                del robots_data[robot_id]
                socketio.emit("robot_offline", {"robot_id": robot_id})


if __name__ == "__main__":
    eventlet.spawn(cleanup_inactive_robots)
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)
