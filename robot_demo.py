import json
import random
import time

import requests

# --- Configuration ---
# API_URL = "http://45.91.169.180:5001/api/update_data"
API_URL = "http://localhost:5001/api/update_data"
ROBOT_ID = "helhest"  # Changed to match your example

# --- Simulation Parameters ---
UPDATE_INTERVAL = 1.5  # How often to send an update (seconds)
TRAVEL_TIME_BETWEEN_WAYPOINTS = 5
NOISE_LEVEL = 0.00003

# --- The Robot's Mission Data ---
# This is the "master copy" of the mission on the robot.
# Note: It does not contain 'classification'. The robot should not decide this.
MISSION_WAYPOINTS = [
    {"lat": 50.021144, "lon": 14.472513},
    {"lat": 50.021161, "lon": 14.472556},
    {"lat": 50.021185, "lon": 14.472588},
    {"lat": 50.021207, "lon": 14.472631},
    {"lat": 50.021226, "lon": 14.472690},
    {"lat": 50.021247, "lon": 14.472706},
    {"lat": 50.021268, "lon": 14.472754},
    {"lat": 50.021275, "lon": 14.472802},
    {"lat": 50.021292, "lon": 14.472845},
    {"lat": 50.021302, "lon": 14.472888},
    {"lat": 50.021316, "lon": 14.472915},
    {"lat": 50.021337, "lon": 14.472969},
    {"lat": 50.021357, "lon": 14.473006},
    {"lat": 50.021364, "lon": 14.473044},
    {"lat": 50.021382, "lon": 14.473071},
    {"lat": 50.021388, "lon": 14.473114},
    {"lat": 50.021406, "lon": 14.473156},
    {"lat": 50.021413, "lon": 14.473199},
    {"lat": 50.021420, "lon": 14.473248},
]


def run_simulation():
    """Main loop to simulate the robot's movement and send stateful updates."""
    num_waypoints = len(MISSION_WAYPOINTS)
    from_waypoint_idx = 0
    # STATE: Does the server have our mission? Start by assuming NO.
    server_has_mission = False

    print(f"--- Starting stateful simulation for robot: {ROBOT_ID} ---")
    print(f"Targeting server at: {API_URL}")

    while True:
        start_wp = MISSION_WAYPOINTS[from_waypoint_idx]
        to_waypoint_idx = (from_waypoint_idx + 1) % num_waypoints
        end_wp = MISSION_WAYPOINTS[to_waypoint_idx]

        print(
            f"\n--- Traveling from WP {from_waypoint_idx} to WP {to_waypoint_idx} ---"
        )

        for step in range(TRAVEL_TIME_BETWEEN_WAYPOINTS):
            progress = step / TRAVEL_TIME_BETWEEN_WAYPOINTS

            # --- CALCULATE POSITIONS ---
            ekf_lat = start_wp["lat"] + (end_wp["lat"] - start_wp["lat"]) * progress
            ekf_lon = start_wp["lon"] + (end_wp["lon"] - start_wp["lon"]) * progress

            gps_lat = ekf_lat + random.uniform(-NOISE_LEVEL, NOISE_LEVEL)
            gps_lon = ekf_lon + random.uniform(-NOISE_LEVEL, NOISE_LEVEL)

            # --- BUILD PAYLOAD ---
            payload = {
                "robot_id": ROBOT_ID,
                "position": {
                    "gps": {"lat": gps_lat, "lon": gps_lon},
                    "ekf": {"lat": ekf_lat, "lon": ekf_lon},
                },
                "mission": {
                    "current_waypoint_index": to_waypoint_idx,
                },
            }

            # If server needs the mission, add the full waypoints list to the payload
            if not server_has_mission:
                print("INFO: Server needs mission. Sending full waypoints list.")
                # Send a clean copy without any client-side classification
                payload["mission"]["waypoints"] = MISSION_WAYPOINTS
            else:
                print("INFO: Server has mission. Sending minimal update.")

            # --- SEND REQUEST AND HANDLE RESPONSE ---
            try:
                response = requests.post(API_URL, json=payload, timeout=5)

                if response.status_code == 200:
                    # SUCCESS: Server accepted the update and has the mission.
                    if not server_has_mission:
                        print("✅ SUCCESS (200): Server has acknowledged the mission.")
                        server_has_mission = True  # Set state to TRUE

                elif response.status_code == 202:
                    # MISSION REQUIRED: Server is asking for the waypoints.
                    print(
                        "⚠️ INFO (202): Server is requesting waypoints. Will send on next update."
                    )
                    server_has_mission = False  # Set state to FALSE

                else:
                    # Handle other potential errors
                    print(f"❌ ERROR ({response.status_code}): {response.text}")
                    # If we get an error, it's safest to assume the server might have lost our state
                    server_has_mission = False

            except requests.exceptions.RequestException as e:
                print(f"❌ NETWORK ERROR: Could not connect to server. {e}")
                # On network error, assume we need to re-sync with the server
                server_has_mission = False
            except KeyboardInterrupt:
                print("\n--- Simulation stopped by user. ---")
                return

            time.sleep(UPDATE_INTERVAL)

        from_waypoint_idx = to_waypoint_idx


if __name__ == "__main__":
    run_simulation()
