document.addEventListener("DOMContentLoaded", () => {
  /**
   * Use a single object to encapsulate the entire application.
   * This is the "Module Pattern". It helps organize code and avoid global variables.
   */
  const RobotTrackerApp = {
    // --- Properties ---
    config: {
      apiKey: null,
      map: {
        initialCoords: [50.084481430216634, 14.480014995760957],
        initialZoom: 5,
      },
    },
    state: {
      allRobotsData: {}, // Stores the latest data for all robots
      selectedRobotId: null, // The ID of the robot currently being viewed
      isFollowing: true, // Flag to determine if the map should follow the robot
    },
    dom: {}, // Will hold cached DOM elements
    map: null, // Will hold the Leaflet map instance
    socket: null, // Will hold the Socket.IO instance
    robotMarkers: {}, // Will hold the Leaflet marker instances for each robot
    missionLayer: null, // Will hold the Leaflet layer for robot missions

    init() {
      this.getConfig();
      this.cacheDom();
      this.initMap();
      this.bindEvents();
      this.initWebSocket();
      this.startTimers();
    },

    getConfig() {
      this.config.apiKey = document.body.dataset.apikey;
    },

    cacheDom() {
      this.dom.robotSelector = document.getElementById("robot-selector");
      this.dom.followButton = document.getElementById("follow-btn");
      this.dom.robotDetailsHeader = document.getElementById(
        "robot-details-header",
      );
      this.dom.robotStatusSections = document.getElementById(
        "robot-status-sections",
      );
      this.dom.lastSeenSpan = document.getElementById("last-seen");
      this.dom.missionProgress = document.getElementById("mission-progress");
      this.dom.sidebar = document.getElementById("sidebar");
      this.dom.sidebarToggle = document.getElementById("sidebar-toggle");
    },

    initMap() {
      this.map = L.map("map").setView(
        this.config.map.initialCoords,
        this.config.map.initialZoom,
      );

      const tileUrl = (style) =>
        `https://{s}.tile.thunderforest.com/${style}/{z}/{x}/{y}{r}.png?apikey=${this.config.apiKey}`;
      const tileAttribution =
        "&copy; Thunderforest, &copy; OpenStreetMap contributors";

      const outdoors = L.tileLayer(tileUrl("outdoors"), {
        attribution: tileAttribution,
        maxZoom: 22,
      });
      const landscape = L.tileLayer(tileUrl("landscape"), {
        attribution: tileAttribution,
        maxZoom: 22,
      });
      const mobileAtlas = L.tileLayer(tileUrl("mobile-atlas"), {
        attribution: tileAttribution,
        maxZoom: 22,
      });

      // Add one default base layer to the map
      outdoors.addTo(this.map);

      const baseLayers = {
        Outdoors: outdoors,
        Landscape: landscape,
        "Mobile Atlas": mobileAtlas,
      };

      L.control.layers(baseLayers).setPosition("topright").addTo(this.map);
      this.map.zoomControl.setPosition("topright");
      this.missionLayer = L.layerGroup().addTo(this.map);
    },

    bindEvents() {
      this.dom.sidebarToggle.addEventListener(
        "click",
        this.handleSidebarToggle.bind(this),
      );
      this.dom.robotSelector.addEventListener(
        "change",
        this.handleRobotSelection.bind(this),
      );
      this.dom.followButton.addEventListener(
        "click",
        this.handleFollowToggle.bind(this),
      );
    },

    initWebSocket() {
      this.socket = io(); // Assumes socket.io script is loaded in HTML

      this.socket.on("initial_robot_states", (data) => {
        this.state.allRobotsData = data;
        this.renderRobotSelector();
        this.renderMission();

        if (
          data.mission &&
          data.mission.waypoints &&
          data.mission.waypoints.length > 0
        ) {
          const bounds = data.mission.waypoints.map((wp) => [wp.lat, wp.lon]);
          this.map.fitBounds(bounds, { padding: [50, 50] });
        }

        if (this.dom.robotSelector.value) {
          this.dom.robotSelector.dispatchEvent(new Event("change"));
        }
      });

      this.socket.on("new_robot_online", (data) => {
        const robotId = data.robot_id;
        this.state.allRobotsData[robotId] = data;

        this.renderRobotSelector();

        if (!this.state.selectedRobotId) {
          this.dom.robotSelector.value = robotId;
          this.dom.robotSelector.dispatchEvent(new Event("change"));
        }

        Toastify({
          text: `✅ Robot ${robotId} is now online.`,
          duration: 30000,
          gravity: "bottom",
          position: "right",
          stopOnFocus: true,
          style: {
            background: "linear-gradient(to right, #00b09b, #96c93d)",
          },
        }).showToast();
      });

      this.socket.on("robot_update", (data) => {
        const robotId = data.robot_id;
        this.state.allRobotsData[robotId] = data;
        this.updateRobotMarker(robotId);

        if (robotId === this.state.selectedRobotId) {
          this.renderSelectedRobotDetails();
          this.renderMission();
          // The conflicting fitBounds() call was removed from here.
        }
      });

      this.socket.on("robot_offline", (data) => {
        const robotId = data.robot_id;
        console.log(`Robot ${robotId} has gone offline.`);

        if (this.state.allRobotsData[robotId]) {
          delete this.state.allRobotsData[robotId];
        }

        if (this.robotMarkers[robotId]) {
          this.map.removeLayer(this.robotMarkers[robotId]);
          delete this.robotMarkers[robotId];
        }

        if (robotId === this.state.selectedRobotId) {
          this.state.selectedRobotId = null;
          this.renderSelectedRobotDetails();
        }

        this.renderRobotSelector();
        Toastify({
          text: `❌ Robot ${robotId} has gone offline.`,
          duration: 30000,
          gravity: "bottom",
          position: "right",
          stopOnFocus: true,
          style: {
            background: "linear-gradient(to right, #ff5f6d, #ffc371)",
          },
        }).showToast();
      });
    },

    startTimers() {
      setInterval(this.updateLastSeen.bind(this), 1000);
    },

    // --- Event Handlers ---
    handleSidebarToggle() {
      const isOpen = this.dom.sidebar.classList.toggle("open");
      this.dom.sidebarToggle.innerHTML = isOpen ? "&times;" : "☰";
    },

    handleRobotSelection(e) {
      this.state.selectedRobotId = e.target.value;
      const robotData = this.state.allRobotsData[this.state.selectedRobotId];

      // First, render the details and the mission path itself
      this.renderSelectedRobotDetails();
      this.renderMission();

      // --- NEW: FIT BOUNDS ON SELECTION ---
      // Adjust the map view to show the entire mission for the newly selected robot.
      if (
        robotData &&
        robotData.mission &&
        robotData.mission.waypoints &&
        robotData.mission.waypoints.length > 0
      ) {
        const bounds = robotData.mission.waypoints.map((wp) => [
          wp.lat,
          wp.lon,
        ]);
        this.map.fitBounds(bounds, { padding: [50, 50] });
      }
    },

    handleFollowToggle() {
      this.state.isFollowing = !this.state.isFollowing;
      this.dom.followButton.textContent = this.state.isFollowing
        ? "Following Robot"
        : "Follow Robot";
      this.dom.followButton.classList.toggle(
        "following",
        this.state.isFollowing,
      );
    },

    // --- UI Rendering & Logic ---
    renderRobotSelector() {
      const currentSelection = this.dom.robotSelector.value;
      this.dom.robotSelector.innerHTML = "";

      const robotIds = Object.keys(this.state.allRobotsData);
      if (robotIds.length === 0) {
        this.dom.robotSelector.innerHTML =
          '<option value="">-- No Robots Online --</option>';
      } else {
        robotIds.forEach((id) => {
          const option = document.createElement("option");
          option.value = id;
          option.textContent = id;
          this.dom.robotSelector.appendChild(option);
        });
      }

      if (this.state.allRobotsData[currentSelection]) {
        this.dom.robotSelector.value = currentSelection;
      } else if (robotIds.length > 0) {
        this.dom.robotSelector.value = robotIds[0];
      }
    },

    updateRobotMarker(robotId) {
      const data = this.state.allRobotsData[robotId];
      if (!data) return;

      const leafletCoords = [data.location.lat, data.location.lon];

      if (this.robotMarkers[robotId]) {
        this.robotMarkers[robotId].setLatLng(leafletCoords);
      } else {
        this.robotMarkers[robotId] = L.marker(leafletCoords).bindPopup(
          `<b>${robotId}</b>`,
        );
      }
    },

    renderSelectedRobotDetails() {
      const robotId = this.state.selectedRobotId;
      const data = this.state.allRobotsData[robotId];

      Object.values(this.robotMarkers).forEach((marker) =>
        this.map.removeLayer(marker),
      );
      if (this.robotMarkers[robotId]) {
        this.map.addLayer(this.robotMarkers[robotId]);
      }

      if (!data) {
        this.dom.robotDetailsHeader.textContent = "Select a robot to view data";
        this.dom.robotStatusSections.style.display = "none";
        this.dom.followButton.style.display = "none";
        this.missionLayer.clearLayers();
        return;
      }

      this.dom.robotDetailsHeader.textContent = `Details for ${robotId}`;
      this.dom.robotStatusSections.style.display = "block";
      this.dom.followButton.style.display = "block";

      const mission = data?.mission;
      if (mission) {
        const progressHtml = `
            <div class="mt-2">
                ${mission.waypoints?.length || 0} waypoints total<br>
                Current target: ${
                  mission.current_waypoint_index >= 0
                    ? mission.current_waypoint_index + 1
                    : "None"
                }<br>
                Completed: ${
                  mission.waypoints?.filter(
                    (wp) => wp.classification === "completed",
                  ).length || 0
                }
            </div>`;
        this.dom.missionProgress.innerHTML = progressHtml;
      } else {
        this.dom.missionProgress.innerHTML = "No active mission";
      }

      this.updateLastSeen();

      // --- MODIFIED: SMART PANNING LOGIC ---
      // Pan map to the robot only if following is enabled AND it's off-screen.
      if (this.state.isFollowing && data.location) {
        const robotLatLng = L.latLng(data.location.lat, data.location.lon);
        const mapBounds = this.map.getBounds();

        // Only pan if the robot is not currently visible on the map.
        if (!mapBounds.contains(robotLatLng)) {
          this.map.panTo(robotLatLng, { animate: true });
        }
      }
    },

    renderMission() {
      this.missionLayer.clearLayers();
      const robotId = this.state.selectedRobotId;
      const mission = this.state.allRobotsData[robotId]?.mission;

      if (mission && mission.waypoints) {
        mission.waypoints.forEach((wp, index) => {
          const isCurrent = index === mission.current_waypoint_index;
          L.circleMarker([wp.lat, wp.lon], {
            radius: 6,
            color: this.getWaypointColor(wp.classification, isCurrent),
            fillColor: this.getWaypointColor(wp.classification, isCurrent),
            fillOpacity: 0.8,
          }).addTo(this.missionLayer);
        });

        const latlngs = mission.waypoints.map((wp) => [wp.lat, wp.lon]);
        L.polyline(latlngs, {
          color: "#4a5568",
          dashArray: "5,5",
        }).addTo(this.missionLayer);
      }
    },

    getWaypointColor(classification, isCurrent) {
      const colors = {
        completed: "#48bb78",
        current_goal: isCurrent ? "#4299e1" : "#d69e2e",
        unfinished: "#e53e3e",
        default: "#718096",
      };
      return colors[classification] || colors.default;
    },

    updateLastSeen() {
      const robotId = this.state.selectedRobotId;
      if (robotId && this.state.allRobotsData[robotId]) {
        const secondsAgo = Math.round(
          (Date.now() - this.state.allRobotsData[robotId].last_update * 1000) /
            1000,
        );
        this.dom.lastSeenSpan.textContent = `${secondsAgo}s ago`;
      }
    },
  };

  RobotTrackerApp.init();
});
