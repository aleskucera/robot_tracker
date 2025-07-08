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
    // MODIFIED: robotMarkers now holds an object with separate gps and ekf markers for each robot
    robotMarkers: {},
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
      this.socket = io();

      this.socket.on("initial_robot_states", (data) => {
        // Add timestamps to initial data
        Object.values(data).forEach((robotData) => {
          robotData.last_update = Date.now() / 1000;
        });

        this.state.allRobotsData = data;
        this.renderRobotSelector();
        this.renderMission();

        if (this.dom.robotSelector.value) {
          this.dom.robotSelector.dispatchEvent(new Event("change"));
        }
      });

      this.socket.on("new_robot_online", (data) => {
        const robotId = data.robot_id;
        data.last_update = Date.now() / 1000;
        this.state.allRobotsData[robotId] = data;

        this.renderRobotSelector();

        if (!this.state.selectedRobotId) {
          this.dom.robotSelector.value = robotId;
          this.dom.robotSelector.dispatchEvent(new Event("change"));
        }

        Toastify({
          text: `✅ Robot ${robotId} is now online.`,
          duration: 3000,
          gravity: "bottom",
          position: "right",
          stopOnFocus: true,
          style: { background: "linear-gradient(to right, #00b09b, #96c93d)" },
        }).showToast();
      });

      this.socket.on("robot_update", (data) => {
        const robotId = data.robot_id;
        // NEW: Add a timestamp to the data for the "last seen" feature
        data.last_update = Date.now() / 1000;
        this.state.allRobotsData[robotId] = data;

        this.updateRobotMarker(robotId);

        if (robotId === this.state.selectedRobotId) {
          this.renderSelectedRobotDetails();
          this.renderMission();
        }
      });

      this.socket.on("robot_offline", (data) => {
        const robotId = data.robot_id;
        console.log(`Robot ${robotId} has gone offline.`);

        if (this.state.allRobotsData[robotId]) {
          delete this.state.allRobotsData[robotId];
        }

        // MODIFIED: Remove both EKF and GPS markers if they exist
        if (this.robotMarkers[robotId]) {
          if (this.robotMarkers[robotId].ekf) {
            this.map.removeLayer(this.robotMarkers[robotId].ekf);
          }
          if (this.robotMarkers[robotId].gps) {
            this.map.removeLayer(this.robotMarkers[robotId].gps);
          }
          delete this.robotMarkers[robotId];
        }

        if (robotId === this.state.selectedRobotId) {
          this.state.selectedRobotId = null;
          this.renderSelectedRobotDetails();
        }

        this.renderRobotSelector();
        Toastify({
          text: `❌ Robot ${robotId} has gone offline.`,
          duration: 3000,
          gravity: "bottom",
          position: "right",
          stopOnFocus: true,
          style: { background: "linear-gradient(to right, #ff5f6d, #ffc371)" },
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

      this.renderSelectedRobotDetails();
      this.renderMission();

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

    createPinSVG(color, fillOpacity = 1) {
      // Changed parameter name for clarity
      const svgPath =
        "M16 .5c-8.282 0-15 6.718-15 15 0 8.283 15 29.5 15 29.5s15-21.217 15-29.5c0-8.282-6.718-15-15-15z";

      // Use the "fill-opacity" attribute instead of "opacity"
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 45.5" class="vector-pin-svg">
      <path d="${svgPath}" fill="${color}" stroke="#fff" stroke-width="1.5" fill-opacity="${fillOpacity}" />
    </svg>`;

      return svg;
    },

    // Update the robot marker only for the selected robot
    updateRobotMarker(robotId) {
      if (robotId !== this.state.selectedRobotId) {
        return;
      }
      const data = this.state.allRobotsData[robotId];
      if (!data || !data.position || !data.position.gps || !data.position.ekf) {
        return;
      }

      const ekfCoords = [data.position.ekf.lat, data.position.ekf.lon];
      const gpsCoords = [data.position.gps.lat, data.position.gps.lon];

      const ekfIcon = L.divIcon({
        html: this.createPinSVG("#28a745", 0.7),
        className: "vector-pin-marker",
        iconSize: [28, 40],
        iconAnchor: [14, 40],
      });

      const gpsIcon = L.divIcon({
        html: this.createPinSVG("#007bff", 0.7),
        className: "vector-pin-marker",
        iconSize: [28, 40],
        iconAnchor: [14, 40],
      });

      // Since we're recreating markers each time, initialize the structure
      if (!this.robotMarkers[robotId]) {
        this.robotMarkers[robotId] = { gps: null, ekf: null };
      }
      const markers = this.robotMarkers[robotId];

      // Create or update EKF marker
      if (markers.ekf) {
        markers.ekf.setLatLng(ekfCoords);
      } else {
        markers.ekf = L.marker(ekfCoords, { icon: ekfIcon })
          .bindPopup(`<b>${robotId} (EKF)</b>`)
          .addTo(this.map);
      }

      if (markers.gps) {
        markers.gps.setLatLng(gpsCoords);
      } else {
        markers.gps = L.marker(gpsCoords, { icon: gpsIcon, zIndexOffset: -100 })
          .bindPopup(`<b>${robotId} (GPS)</b>`)
          .addTo(this.map);
      }
    },

    // Render details and recreate markers for the selected robot
    renderSelectedRobotDetails() {
      const robotId = this.state.selectedRobotId;
      const data = this.state.allRobotsData[robotId];

      // Remove all existing markers from the map
      for (const id in this.robotMarkers) {
        if (this.robotMarkers[id].ekf) {
          this.map.removeLayer(this.robotMarkers[id].ekf);
        }
        if (this.robotMarkers[id].gps) {
          this.map.removeLayer(this.robotMarkers[id].gps);
        }
      }
      // Fully delete markers by clearing the object
      this.robotMarkers = {};

      if (data) {
        // Recreate markers for the selected robot
        this.updateRobotMarker(robotId);
        this.dom.robotDetailsHeader.textContent = `Details for ${robotId}`;
        this.dom.robotStatusSections.style.display = "block";
        this.dom.followButton.style.display = "block";
        // Additional details rendering can be added here as needed
      } else {
        this.dom.robotDetailsHeader.textContent = "Select a robot to view data";
        this.dom.robotStatusSections.style.display = "none";
        this.dom.followButton.style.display = "none";
        this.missionLayer.clearLayers();
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
      const robotData = this.state.allRobotsData[robotId];
      if (robotId && robotData && robotData.last_update) {
        const secondsAgo = Math.round(
          (Date.now() - robotData.last_update * 1000) / 1000,
        );
        this.dom.lastSeenSpan.textContent = `${secondsAgo}s ago`;
      } else if (robotId) {
        this.dom.lastSeenSpan.textContent = `...`;
      }
    },
  };

  RobotTrackerApp.init();
});
