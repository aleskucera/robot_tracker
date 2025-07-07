import json
import random
import time

import requests

# --- Configuration ---
API_URL = "http://127.0.0.1:5000/api/update_data"
ROBOT_ID = "Helhest"

# --- Simulation Parameters ---
# How often to send an update to the server (in seconds)
UPDATE_INTERVAL = 1
# How long it takes the robot to travel between any two waypoints (in seconds)
TRAVEL_TIME_BETWEEN_WAYPOINTS = 5
# How much random "wobble" to add to the GPS signal.
# 0.00001 is roughly 1.1 meters of noise.
NOISE_LEVEL = 0.00003

# --- The Robot's Mission Data ---
# This is the static list of all waypoints for the mission.
MISSION_WAYPOINTS = [
    {"lat": 50.021144963451064, "lon": 14.47251319885254},
    {"lat": 50.02116150744906, "lon": 14.47255611419678},
    {"lat": 50.02118563408718, "lon": 14.472588300704958},
    {"lat": 50.0212070033746, "lon": 14.472631216049196},
    {"lat": 50.021226994010085, "lon": 14.472690224647524},
    {"lat": 50.02124767395818, "lon": 14.472706317901613},
    {"lat": 50.02126835389739, "lon": 14.472754597663881},
    {"lat": 50.02127524720846, "lon": 14.47280287742615},
    {"lat": 50.021292480481854, "lon": 14.472845792770388},
    {"lat": 50.02130282044291, "lon": 14.472888708114626},
    {"lat": 50.02131660705421, "lon": 14.472915530204775},
    {"lat": 50.02133728696375, "lon": 14.472969174385073},
    {"lat": 50.021357966864336, "lon": 14.47300672531128},
    {"lat": 50.021364860162585, "lon": 14.47304427623749},
    {"lat": 50.021382093403844, "lon": 14.473071098327638},
    {"lat": 50.021388986698575, "lon": 14.473114013671877},
    {"lat": 50.02140621993119, "lon": 14.473156929016115},
    {"lat": 50.021413113222486, "lon": 14.473199844360353},
    {"lat": 50.02142069583128, "lon": 14.473248124122621},
]


def run_simulation():
    """Main loop to simulate the robot's movement and send updates."""
    num_waypoints = len(MISSION_WAYPOINTS)
    from_waypoint_idx = 0

    print(f"--- Starting smooth simulation for robot: {ROBOT_ID} ---")
    print(f"Targeting server at: {API_URL}")
    print(f"Sending updates every {UPDATE_INTERVAL} second(s). Press Ctrl+C to stop.")

    while True:
        # Determine the start and end points for this leg of the journey
        start_wp = MISSION_WAYPOINTS[from_waypoint_idx]
        to_waypoint_idx = (from_waypoint_idx + 1) % num_waypoints
        end_wp = MISSION_WAYPOINTS[to_waypoint_idx]

        print(
            f"\n--- Traveling from WP {from_waypoint_idx + 1} to WP {to_waypoint_idx + 1} ---"
        )

        # Inner loop for interpolation between the two points
        for step in range(TRAVEL_TIME_BETWEEN_WAYPOINTS):
            try:
                # --- INTERPOLATION ---
                # Calculate how far along the path we are (e.g., 0.2 means 20% of the way)
                progress = step / TRAVEL_TIME_BETWEEN_WAYPOINTS

                # Calculate the interpolated latitude and longitude
                interp_lat = (
                    start_wp["lat"] + (end_wp["lat"] - start_wp["lat"]) * progress
                )
                interp_lon = (
                    start_wp["lon"] + (end_wp["lon"] - start_wp["lon"]) * progress
                )

                # --- NOISE ---
                # Add a small random offset to simulate GPS inaccuracy
                noisy_lat = interp_lat + random.uniform(-NOISE_LEVEL, NOISE_LEVEL)
                noisy_lon = interp_lon + random.uniform(-NOISE_LEVEL, NOISE_LEVEL)

                # --- MISSION STATUS ---
                # Build the list of waypoints with updated classifications
                updated_waypoints = []
                for i, wp in enumerate(MISSION_WAYPOINTS):
                    classification = "unfinished"  # Default
                    if i < to_waypoint_idx:
                        classification = "completed"
                    elif i == to_waypoint_idx:
                        classification = "current_goal"

                    updated_wp = wp.copy()
                    updated_wp["classification"] = classification
                    updated_waypoints.append(updated_wp)

                # Assemble the full payload
                payload = {
                    "robot_id": ROBOT_ID,
                    "lat": noisy_lat,
                    "lon": noisy_lon,
                    "mission": {
                        "waypoints": updated_waypoints,
                        "current_waypoint_index": to_waypoint_idx,
                    },
                }

                print(
                    f"  Step {step+1}/{TRAVEL_TIME_BETWEEN_WAYPOINTS}: Pos({noisy_lat:.6f}, {noisy_lon:.6f})"
                )

                # Send the POST request
                response = requests.post(API_URL, json=payload)
                response.raise_for_status()

                # Wait before sending the next update
                time.sleep(UPDATE_INTERVAL)

            except requests.exceptions.RequestException as e:
                print(
                    f"❌ Error: Could not connect to server. Retrying in {UPDATE_INTERVAL}s..."
                )
                time.sleep(UPDATE_INTERVAL)
            except KeyboardInterrupt:
                print("\n--- Simulation stopped by user. ---")
                return  # Exit the function and the script

        # The robot has "arrived". Prepare for the next leg of the journey.
        from_waypoint_idx = to_waypoint_idx


if __name__ == "__main__":
    run_simulation()
