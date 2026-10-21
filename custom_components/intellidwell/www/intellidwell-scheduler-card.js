/**
 * IntelliDwell Sprinkler Scheduler Card for Home Assistant
 * Allows viewing, adding, editing, and deleting sprinkler watering schedules directly from Lovelace.
 */

const DAYS_OF_WEEK = [
  { short: "Mon", full: "Monday", letter: "M" },
  { short: "Tue", full: "Tuesday", letter: "T" },
  { short: "Wed", full: "Wednesday", letter: "W" },
  { short: "Thu", full: "Thursday", letter: "T" },
  { short: "Fri", full: "Friday", letter: "F" },
  { short: "Sat", full: "Saturday", letter: "S" },
  { short: "Sun", full: "Sunday", letter: "S" },
];

class IntelliDwellSchedulerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._selectedZoneFilter = "all"; // 'all' or zone_index (1-10)
    this._modalState = null; // null or { mode: 'add'|'edit', zoneIndex, scheduleId, days, onTime, offTime, durationMins }
    this._timerModalState = null; // null or { zoneIndex, zoneName, durationMins }
    this._activeRemaining = 0;
    this._countdownTimer = null;
  }

  connectedCallback() {
    if (!this._countdownTimer) {
      this._countdownTimer = setInterval(() => {
        const liveEl = this.shadowRoot ? this.shadowRoot.getElementById("liveCountdown") : null;
        if (liveEl && this._activeRemaining > 0) {
          this._activeRemaining -= 1;
          liveEl.textContent = `${this._formatRemaining(this._activeRemaining)} remaining`;
        }
      }, 1000);
    }
  }

  disconnectedCallback() {
    if (this._countdownTimer) {
      clearInterval(this._countdownTimer);
      this._countdownTimer = null;
    }
  }

  _formatRemaining(seconds) {
    if (!seconds || seconds <= 0) return "0s";
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    if (m === 0) return `${s}s`;
    return `${m}m ${s < 10 ? '0' : ''}${s}s`;
  }

  setConfig(config) {
    this._config = Object.assign(
      {
        title: "Sprinkler Schedules",
        show_zone_filter: true,
      },
      config
    );
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 6;
  }

  _getScheduleEntities() {
    if (!this._hass) return [];
    const entities = [];
    for (const [entityId, stateObj] of Object.entries(this._hass.states)) {
      if (
        entityId.startsWith("switch.intellidwell_") &&
        !entityId.endsWith("_schedule") &&
        stateObj.attributes &&
        stateObj.attributes.zone_index !== undefined
      ) {
        entities.push(stateObj);
      }
    }
    entities.sort((a, b) => {
      const idxA = a.attributes.zone_index || 0;
      const idxB = b.attributes.zone_index || 0;
      return idxA - idxB;
    });
    return entities;
  }

  _calculateDurationMinutes(onTime, offTime) {
    if (!onTime || !offTime) return 0;
    const [h1, m1] = onTime.split(":").map(Number);
    const [h2, m2] = offTime.split(":").map(Number);
    let mins = h2 * 60 + m2 - (h1 * 60 + m1);
    if (mins < 0) mins += 24 * 60;
    return mins;
  }

  _calculateOffTime(onTime, durationMins) {
    if (!onTime) return "";
    const [h, m] = onTime.split(":").map(Number);
    const total = (h * 60 + m + Number(durationMins)) % (24 * 60);
    const endH = String(Math.floor(total / 60)).padStart(2, "0");
    const endM = String(total % 60).padStart(2, "0");
    return `${endH}:${endM}`;
  }

  _render() {
    if (!this._hass) return;
    const entities = this._getScheduleEntities();

    // Check if any zone is actively watering or has a timer
    let activeZone = null;
    for (const ent of entities) {
      const remaining = Number(ent.attributes.timer_remaining_seconds || 0);
      const isSwitchOn = ent.state === "on";
      if (remaining > 0 || isSwitchOn) {
        activeZone = {
          index: ent.attributes.zone_index || 1,
          name: ent.attributes.zone_name || `Zone ${ent.attributes.zone_index || 1}`,
          remaining: remaining,
        };
        break;
      }
    }
    this._activeRemaining = activeZone ? activeZone.remaining : 0;

    // Preserve open modal state during updates
    const modalHtml = this._renderModal(entities);
    const timerModalHtml = this._renderTimerModal();

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          --accent-color: var(--primary-color, #3b82f6);
          --accent-success: var(--success-color, #10b981);
          --accent-danger: var(--error-color, #ef4444);
          --card-bg: var(--ha-card-background, var(--card-background-color, #1e293b));
          --border-color: var(--divider-color, rgba(255, 255, 255, 0.1));
          --text-primary: var(--primary-text-color, #f8fafc);
          --text-secondary: var(--secondary-text-color, #94a3b8);
        }

        ha-card {
          padding: 16px;
          border-radius: var(--ha-card-border-radius, 16px);
          background: var(--card-bg);
          box-sizing: border-box;
          font-family: inherit;
        }

        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 16px;
          padding-bottom: 12px;
          border-bottom: 1px solid var(--border-color);
        }

        .header-title {
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 1.25rem;
          font-weight: 700;
          color: var(--text-primary);
        }

        .header-icon {
          color: var(--accent-color);
        }

        .btn-add {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          background: var(--accent-color);
          color: #ffffff;
          border: none;
          border-radius: 9999px;
          padding: 8px 14px;
          font-size: 0.875rem;
          font-weight: 600;
          cursor: pointer;
          transition: filter 0.15s ease, transform 0.1s ease;
        }
        .btn-add:hover {
          filter: brightness(1.1);
        }
        .btn-add:active {
          transform: scale(0.97);
        }

        /* Filter Pills */
        .filter-container {
          display: flex;
          gap: 8px;
          overflow-x: auto;
          padding-bottom: 12px;
          margin-bottom: 14px;
          scrollbar-width: thin;
        }
        .filter-container::-webkit-scrollbar {
          height: 4px;
        }
        .filter-container::-webkit-scrollbar-thumb {
          background: var(--border-color);
          border-radius: 4px;
        }

        .filter-pill {
          background: rgba(255, 255, 255, 0.05);
          color: var(--text-secondary);
          border: 1px solid var(--border-color);
          border-radius: 9999px;
          padding: 6px 12px;
          font-size: 0.8rem;
          font-weight: 500;
          white-space: nowrap;
          cursor: pointer;
          transition: all 0.15s ease;
        }
        .filter-pill.active {
          background: var(--accent-color);
          color: #ffffff;
          border-color: var(--accent-color);
        }

        /* Zone Section */
        .zone-group {
          background: rgba(0, 0, 0, 0.12);
          border: 1px solid var(--border-color);
          border-radius: 12px;
          padding: 14px;
          margin-bottom: 14px;
        }

        .zone-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 10px;
        }

        .zone-name-wrap {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .zone-badge {
          background: rgba(255, 255, 255, 0.1);
          color: var(--text-secondary);
          border-radius: 6px;
          padding: 2px 6px;
          font-size: 0.75rem;
          font-weight: 600;
        }

        .zone-title {
          font-size: 1rem;
          font-weight: 600;
          color: var(--text-primary);
        }

        .zone-switch-wrap {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        /* Active Watering Banner */
        .active-watering-banner {
          display: flex;
          align-items: center;
          justify-content: space-between;
          background: linear-gradient(135deg, rgba(59, 130, 246, 0.18), rgba(16, 185, 129, 0.18));
          border: 1px solid rgba(59, 130, 246, 0.45);
          border-radius: 12px;
          padding: 12px 14px;
          margin-bottom: 14px;
        }
        .watering-badge {
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .pulsing-drop {
          font-size: 1.35rem;
          display: inline-block;
          animation: pulse-drop 1.5s infinite ease-in-out;
        }
        @keyframes pulse-drop {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.25); }
        }
        .watering-text {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .watering-title {
          font-size: 0.95rem;
          font-weight: 700;
          color: var(--text-primary);
        }
        .watering-countdown {
          font-size: 0.8rem;
          font-weight: 600;
          color: var(--accent-success);
        }
        .btn-stop-watering {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          background: var(--accent-danger);
          color: #ffffff;
          border: none;
          border-radius: 8px;
          padding: 6px 12px;
          font-size: 0.8rem;
          font-weight: 600;
          cursor: pointer;
          transition: filter 0.15s ease;
        }
        .btn-stop-watering:hover {
          filter: brightness(1.15);
        }

        /* Quick Zone Timer Button */
        .btn-zone-timer {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          background: rgba(255, 255, 255, 0.08);
          color: var(--text-secondary);
          border: 1px solid var(--border-color);
          border-radius: 6px;
          padding: 4px 8px;
          font-size: 0.75rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
        }
        .btn-zone-timer:hover {
          background: rgba(255, 255, 255, 0.14);
          color: var(--text-primary);
        }
        .btn-zone-timer.active {
          background: rgba(239, 68, 68, 0.2);
          color: var(--accent-danger);
          border-color: var(--accent-danger);
          animation: pulse-border 1.5s infinite;
        }
        @keyframes pulse-border {
          0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
          70% { box-shadow: 0 0 0 6px rgba(239, 68, 68, 0); }
          100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
        }

        /* Schedule Rule Item */
        .schedules-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .schedule-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid var(--border-color);
          border-radius: 10px;
          padding: 10px 12px;
          gap: 12px;
          transition: border-color 0.15s ease;
        }
        .schedule-row.disabled {
          opacity: 0.55;
        }

        .rule-info {
          display: flex;
          flex-direction: column;
          gap: 4px;
          flex: 1;
        }

        .time-badge {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          font-size: 0.95rem;
          font-weight: 700;
          color: var(--text-primary);
        }

        .duration-chip {
          font-size: 0.75rem;
          font-weight: 500;
          color: var(--text-secondary);
          background: rgba(255, 255, 255, 0.08);
          padding: 2px 6px;
          border-radius: 4px;
        }

        /* Days Badges */
        .days-badges {
          display: flex;
          gap: 4px;
        }

        .day-dot {
          width: 20px;
          height: 20px;
          border-radius: 4px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 0.65rem;
          font-weight: 700;
          background: rgba(255, 255, 255, 0.05);
          color: var(--text-secondary);
        }
        .day-dot.active {
          background: var(--accent-color);
          color: #ffffff;
        }

        .rule-actions {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .icon-btn {
          background: none;
          border: none;
          padding: 6px;
          cursor: pointer;
          color: var(--text-secondary);
          border-radius: 6px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.15s ease;
        }
        .icon-btn:hover {
          color: var(--text-primary);
          background: rgba(255, 255, 255, 0.1);
        }
        .icon-btn.delete:hover {
          color: var(--accent-danger);
          background: rgba(239, 68, 68, 0.1);
        }

        .toggle-rule {
          width: 38px;
          height: 22px;
          position: relative;
          display: inline-block;
        }
        .toggle-rule input {
          opacity: 0;
          width: 0;
          height: 0;
        }
        .toggle-slider {
          position: absolute;
          cursor: pointer;
          top: 0; left: 0; right: 0; bottom: 0;
          background-color: rgba(255, 255, 255, 0.15);
          transition: .2s;
          border-radius: 22px;
        }
        .toggle-slider:before {
          position: absolute;
          content: "";
          height: 16px;
          width: 16px;
          left: 3px;
          bottom: 3px;
          background-color: white;
          transition: .2s;
          border-radius: 50%;
        }
        input:checked + .toggle-slider {
          background-color: var(--accent-success);
        }
        input:checked + .toggle-slider:before {
          transform: translateX(16px);
        }

        .empty-zone {
          padding: 12px;
          text-align: center;
          color: var(--text-secondary);
          font-size: 0.85rem;
          border: 1px dashed var(--border-color);
          border-radius: 8px;
          cursor: pointer;
        }
        .empty-zone:hover {
          background: rgba(255, 255, 255, 0.02);
          color: var(--text-primary);
        }

        /* Modal Overlay */
        .modal-overlay {
          position: fixed;
          top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(0, 0, 0, 0.65);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 9999;
          backdrop-filter: blur(4px);
          padding: 16px;
        }

        .modal-dialog {
          background: var(--card-bg);
          border: 1px solid var(--border-color);
          border-radius: 16px;
          width: 100%;
          max-width: 440px;
          padding: 22px;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
          box-sizing: border-box;
        }

        .modal-title {
          font-size: 1.15rem;
          font-weight: 700;
          color: var(--text-primary);
          margin-bottom: 18px;
        }

        .form-group {
          margin-bottom: 16px;
        }

        .form-label {
          display: block;
          font-size: 0.85rem;
          font-weight: 600;
          color: var(--text-secondary);
          margin-bottom: 6px;
        }

        .form-select, .form-input {
          width: 100%;
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid var(--border-color);
          border-radius: 8px;
          color: var(--text-primary);
          padding: 10px;
          font-size: 0.95rem;
          box-sizing: border-box;
          outline: none;
        }
        .form-select:focus, .form-input:focus {
          border-color: var(--accent-color);
        }

        /* Days Selector in Modal */
        .days-selector {
          display: flex;
          justify-content: space-between;
          gap: 4px;
          margin-bottom: 8px;
        }
        .day-toggle-btn {
          flex: 1;
          padding: 8px 0;
          background: rgba(255, 255, 255, 0.06);
          color: var(--text-secondary);
          border: 1px solid var(--border-color);
          border-radius: 6px;
          font-size: 0.75rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
        }
        .day-toggle-btn.selected {
          background: var(--accent-color);
          color: #ffffff;
          border-color: var(--accent-color);
        }

        .quick-days-row {
          display: flex;
          gap: 6px;
        }
        .quick-day-btn {
          background: none;
          border: 1px solid var(--border-color);
          border-radius: 4px;
          padding: 4px 8px;
          font-size: 0.7rem;
          color: var(--text-secondary);
          cursor: pointer;
        }
        .quick-day-btn:hover {
          background: rgba(255, 255, 255, 0.05);
          color: var(--text-primary);
        }

        /* Duration Chips */
        .duration-chips {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-top: 6px;
        }
        .duration-chip-btn {
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid var(--border-color);
          border-radius: 6px;
          padding: 4px 10px;
          font-size: 0.75rem;
          color: var(--text-secondary);
          cursor: pointer;
        }
        .duration-chip-btn.active {
          background: var(--accent-color);
          color: #ffffff;
          border-color: var(--accent-color);
        }

        .end-time-preview {
          font-size: 0.85rem;
          color: var(--accent-success);
          margin-top: 6px;
          font-weight: 500;
        }

        .modal-actions {
          display: flex;
          justify-content: flex-end;
          gap: 10px;
          margin-top: 24px;
        }

        .btn-cancel {
          background: transparent;
          border: 1px solid var(--border-color);
          color: var(--text-primary);
          padding: 9px 16px;
          border-radius: 8px;
          font-size: 0.875rem;
          cursor: pointer;
        }

        .btn-save {
          background: var(--accent-color);
          border: none;
          color: #ffffff;
          padding: 9px 18px;
          border-radius: 8px;
          font-size: 0.875rem;
          font-weight: 600;
          cursor: pointer;
        }
        .btn-save:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
      </style>

      <ha-card>
        <div class="header">
          <div class="header-title">
            <ha-icon class="header-icon" icon="mdi:sprinkler-variant"></ha-icon>
            <span>${this._config.title}</span>
          </div>
          <button class="btn-add" id="btnHeaderAdd">
            <ha-icon icon="mdi:plus"></ha-icon>
            Add Schedule
          </button>
        </div>

        ${
          activeZone
            ? `
            <div class="active-watering-banner">
              <div class="watering-badge">
                <span class="pulsing-drop">💧</span>
                <div class="watering-text">
                  <span class="watering-title">${activeZone.name} is Watering</span>
                  <span class="watering-countdown" id="liveCountdown">${
                    activeZone.remaining > 0
                      ? `${this._formatRemaining(activeZone.remaining)} remaining`
                      : "Running manually"
                  }</span>
                </div>
              </div>
              <button class="btn-stop-watering" id="btnActiveStop" data-zone="${activeZone.index}">
                <ha-icon icon="mdi:stop-circle-outline"></ha-icon> Stop
              </button>
            </div>
            `
            : ""
        }

        ${this._config.show_zone_filter ? this._renderFilters(entities) : ""}

        <div class="zones-container">
          ${this._renderZoneGroups(entities)}
        </div>

        ${modalHtml}
        ${timerModalHtml}
      </ha-card>
    `;

    this._bindEvents(entities);
  }

  _renderFilters(entities) {
    let pills = `
      <div class="filter-pill ${this._selectedZoneFilter === "all" ? "active" : ""}" data-filter="all">
        All Zones
      </div>
    `;

    for (const ent of entities) {
      const zIdx = ent.attributes.zone_index || 1;
      const zName = ent.attributes.zone_name || `Zone ${zIdx}`;
      const schedCount = (ent.attributes.schedules || []).length;
      const isActive = String(this._selectedZoneFilter) === String(zIdx);

      pills += `
        <div class="filter-pill ${isActive ? "active" : ""}" data-filter="${zIdx}">
          ${zName} (${schedCount})
        </div>
      `;
    }

    return `<div class="filter-container">${pills}</div>`;
  }

  _renderZoneGroups(entities) {
    const visibleEntities =
      this._selectedZoneFilter === "all"
        ? entities
        : entities.filter(
            (e) => String(e.attributes.zone_index) === String(this._selectedZoneFilter)
          );

    if (visibleEntities.length === 0) {
      return `<div style="text-align:center; padding: 20px; color: var(--text-secondary);">No sprinkler zones found.</div>`;
    }

    return visibleEntities
      .map((ent) => {
        const zIdx = ent.attributes.zone_index || 1;
        const zName = ent.attributes.zone_name || `Zone ${zIdx}`;
        const schedules = ent.attributes.schedules || [];
        const isMasterOn = ent.attributes.schedule_enabled !== false;
        const remaining = Number(ent.attributes.timer_remaining_seconds || 0);
        const isWatering = ent.state === "on" || remaining > 0;

        return `
          <div class="zone-group">
            <div class="zone-header">
              <div class="zone-name-wrap">
                <span class="zone-badge">#${zIdx}</span>
                <span class="zone-title">${zName}</span>
              </div>
              <div class="zone-switch-wrap">
                <button type="button" class="btn-zone-timer ${isWatering ? "active" : ""}" 
                  data-zone="${zIdx}" 
                  data-zone-name="${zName}"
                  data-watering="${isWatering ? "true" : "false"}"
                  title="${isWatering ? "Stop watering" : "Start quick watering timer"}">
                  <ha-icon icon="${isWatering ? "mdi:stop-circle" : "mdi:timer-play-outline"}"></ha-icon>
                  <span>${isWatering ? (remaining > 0 ? `${Math.ceil(remaining / 60)}m left` : "Stop") : "Timer"}</span>
                </button>
                <label class="toggle-rule" title="Toggle entire schedule for ${zName}">
                  <input type="checkbox" class="zone-master-toggle" data-zone="${zIdx}" ${
          isMasterOn ? "checked" : ""
        }>
                  <span class="toggle-slider"></span>
                </label>
              </div>
            </div>

            <div class="schedules-list">
              ${
                schedules.length === 0
                  ? `<div class="empty-zone" data-add-zone="${zIdx}">+ Add a scheduled run for ${zName}</div>`
                  : schedules
                      .map((sched) => {
                        const duration = this._calculateDurationMinutes(
                          sched.onTime,
                          sched.offTime
                        );
                        return `
                          <div class="schedule-row ${sched.enabled === false ? "disabled" : ""}">
                            <div class="rule-info">
                              <div class="time-badge">
                                <span>${sched.onTime} – ${sched.offTime}</span>
                                <span class="duration-chip">${duration} min</span>
                              </div>
                              <div class="days-badges">
                                ${DAYS_OF_WEEK.map((d) => {
                                  const active = (sched.days || []).includes(d.short);
                                  return `<div class="day-dot ${active ? "active" : ""}" title="${d.full}">${d.letter}</div>`;
                                }).join("")}
                              </div>
                            </div>

                            <div class="rule-actions">
                              <label class="toggle-rule" title="Enable/Disable rule">
                                <input type="checkbox" class="schedule-item-toggle"
                                  data-zone="${zIdx}"
                                  data-sched-id="${sched.id}"
                                  ${sched.enabled !== false ? "checked" : ""}>
                                <span class="toggle-slider"></span>
                              </label>

                              <button class="icon-btn edit-btn" title="Edit schedule"
                                data-zone="${zIdx}"
                                data-sched-id="${sched.id}"
                                data-on="${sched.onTime}"
                                data-off="${sched.offTime}"
                                data-days='${JSON.stringify(sched.days || [])}'>
                                <ha-icon icon="mdi:pencil-outline"></ha-icon>
                              </button>

                              <button class="icon-btn delete delete-btn" title="Delete schedule"
                                data-zone="${zIdx}"
                                data-sched-id="${sched.id}">
                                <ha-icon icon="mdi:trash-can-outline"></ha-icon>
                              </button>
                            </div>
                          </div>
                        `;
                      })
                      .join("")
              }
            </div>
          </div>
        `;
      })
      .join("");
  }

  _renderModal(entities) {
    if (!this._modalState) return "";

    const { mode, zoneIndex, scheduleId, days, onTime, offTime, durationMins } =
      this._modalState;
    const isEdit = mode === "edit";
    const title = isEdit ? "Edit Schedule" : "Add Watering Schedule";
    const calculatedOff = this._calculateOffTime(onTime, durationMins);

    return `
      <div class="modal-overlay" id="modalOverlay">
        <div class="modal-dialog">
          <div class="modal-title">${title}</div>

          <div class="form-group">
            <label class="form-label">Zone</label>
            <select class="form-select" id="modalZoneSelect" ${isEdit ? "disabled" : ""}>
              ${entities
                .map((e) => {
                  const z = e.attributes.zone_index || 1;
                  const name = e.attributes.zone_name || `Zone ${z}`;
                  return `<option value="${z}" ${String(z) === String(zoneIndex) ? "selected" : ""}>${z}: ${name}</option>`;
                })
                .join("")}
            </select>
          </div>

          <div class="form-group">
            <label class="form-label">Active Days</label>
            <div class="days-selector">
              ${DAYS_OF_WEEK.map((d) => {
                const sel = days.includes(d.short);
                return `<button type="button" class="day-toggle-btn ${sel ? "selected" : ""}" data-day="${d.short}">${d.short}</button>`;
              }).join("")}
            </div>
            <div class="quick-days-row">
              <button type="button" class="quick-day-btn" id="btnDaysEveryday">Every Day</button>
              <button type="button" class="quick-day-btn" id="btnDaysWeekdays">Weekdays</button>
              <button type="button" class="quick-day-btn" id="btnDaysWeekends">Weekends</button>
              <button type="button" class="quick-day-btn" id="btnDaysClear">Clear</button>
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">Start Time</label>
            <input type="time" class="form-input" id="modalStartTime" value="${onTime || "06:00"}">
          </div>

          <div class="form-group">
            <label class="form-label">Duration (Minutes)</label>
            <input type="number" min="1" max="240" class="form-input" id="modalDuration" value="${durationMins || 20}">
            <div class="duration-chips">
              ${[5, 10, 15, 20, 30, 45, 60]
                .map((m) => {
                  const isAct = Number(durationMins) === m;
                  return `<button type="button" class="duration-chip-btn ${isAct ? "active" : ""}" data-mins="${m}">${m} min</button>`;
                })
                .join("")}
            </div>
            <div class="end-time-preview" id="endTimePreview">
              Watering ends at: ${calculatedOff || "06:20"}
            </div>
          </div>

          <div class="modal-actions">
            <button type="button" class="btn-cancel" id="btnModalCancel">Cancel</button>
            <button type="button" class="btn-save" id="btnModalSave">${isEdit ? "Save Changes" : "Add Schedule"}</button>
          </div>
        </div>
      </div>
    `;
  }

  _renderTimerModal() {
    if (!this._timerModalState) return "";
    const { zoneIndex, zoneName, durationMins } = this._timerModalState;
    const presets = [5, 10, 15, 20, 30, 45, 60];

    return `
      <div class="modal-overlay" id="timerModalOverlay">
        <div class="modal-dialog">
          <div class="modal-title">⏱ Quick Timer: ${zoneName}</div>

          <div class="form-group">
            <label class="form-label">Watering Duration (Minutes)</label>
            <div class="duration-chips" style="margin-bottom: 12px;">
              ${presets
                .map(
                  (m) => `
                <button type="button" class="duration-chip-btn ${
                  Number(durationMins) === m ? "active" : ""
                }" data-quick-mins="${m}">${m} min</button>
              `
                )
                .join("")}
            </div>
            <input type="number" min="1" max="180" class="form-input" id="timerDurationInput" value="${
              durationMins || 15
            }">
          </div>

          <div class="modal-actions">
            <button type="button" class="btn-cancel" id="btnTimerCancel">Cancel</button>
            <button type="button" class="btn-save" id="btnTimerStart">💧 Start Watering</button>
          </div>
        </div>
      </div>
    `;
  }

  _bindEvents(entities) {
    const root = this.shadowRoot;

    // Stop active watering banner button
    const btnActiveStop = root.getElementById("btnActiveStop");
    if (btnActiveStop) {
      btnActiveStop.addEventListener("click", () => {
        const zone = Number(btnActiveStop.getAttribute("data-zone") || 1);
        this._hass.callService("intellidwell", "cancel_timer", { zone: zone });
      });
    }

    // Quick zone timer buttons
    root.querySelectorAll(".btn-zone-timer").forEach((btn) => {
      btn.addEventListener("click", () => {
        const zone = Number(btn.getAttribute("data-zone"));
        const zoneName = btn.getAttribute("data-zone-name");
        const isWatering = btn.getAttribute("data-watering") === "true";

        if (isWatering) {
          this._hass.callService("intellidwell", "cancel_timer", { zone: zone });
        } else {
          this._timerModalState = {
            zoneIndex: zone,
            zoneName: zoneName,
            durationMins: 15,
          };
          this._render();
        }
      });
    });

    // Filter pills
    root.querySelectorAll(".filter-pill").forEach((pill) => {
      pill.addEventListener("click", () => {
        this._selectedZoneFilter = pill.getAttribute("data-filter");
        this._render();
      });
    });

    // Add button in header
    const btnAdd = root.getElementById("btnHeaderAdd");
    if (btnAdd) {
      btnAdd.addEventListener("click", () => {
        const defaultZone =
          this._selectedZoneFilter !== "all"
            ? Number(this._selectedZoneFilter)
            : entities.length > 0
            ? entities[0].attributes.zone_index || 1
            : 1;

        this._modalState = {
          mode: "add",
          zoneIndex: defaultZone,
          scheduleId: null,
          days: ["Mon", "Wed", "Fri"],
          onTime: "06:00",
          offTime: "06:20",
          durationMins: 20,
        };
        this._render();
      });
    }

    // Empty zone add shortcuts
    root.querySelectorAll(".empty-zone").forEach((btn) => {
      btn.addEventListener("click", () => {
        const z = Number(btn.getAttribute("data-add-zone"));
        this._modalState = {
          mode: "add",
          zoneIndex: z,
          scheduleId: null,
          days: ["Mon", "Wed", "Fri"],
          onTime: "06:00",
          offTime: "06:20",
          durationMins: 20,
        };
        this._render();
      });
    });

    // Zone Master Schedule Switch
    root.querySelectorAll(".zone-master-toggle").forEach((toggle) => {
      toggle.addEventListener("change", (e) => {
        const zone = Number(toggle.getAttribute("data-zone"));
        this._hass.callService("intellidwell", "toggle_zone_schedule", {
          zone: zone,
          enabled: toggle.checked,
        });
      });
    });

    // Toggle individual schedule item
    root.querySelectorAll(".schedule-item-toggle").forEach((toggle) => {
      toggle.addEventListener("change", (e) => {
        const zone = Number(toggle.getAttribute("data-zone"));
        const schedId = toggle.getAttribute("data-sched-id");
        this._hass.callService("intellidwell", "toggle_schedule_item", {
          zone: zone,
          schedule_id: schedId,
          enabled: toggle.checked,
        });
      });
    });

    // Edit schedule button
    root.querySelectorAll(".edit-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const zone = Number(btn.getAttribute("data-zone"));
        const schedId = btn.getAttribute("data-sched-id");
        const onTime = btn.getAttribute("data-on");
        const offTime = btn.getAttribute("data-off");
        let days = [];
        try {
          days = JSON.parse(btn.getAttribute("data-days") || "[]");
        } catch (_) {}

        const duration = this._calculateDurationMinutes(onTime, offTime);

        this._modalState = {
          mode: "edit",
          zoneIndex: zone,
          scheduleId: schedId,
          days: days,
          onTime: onTime,
          offTime: offTime,
          durationMins: duration || 20,
        };
        this._render();
      });
    });

    // Delete schedule button
    root.querySelectorAll(".delete-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const zone = Number(btn.getAttribute("data-zone"));
        const schedId = btn.getAttribute("data-sched-id");
        if (confirm(`Delete this scheduled run for Zone ${zone}?`)) {
          this._hass.callService("intellidwell", "delete_schedule", {
            zone: zone,
            schedule_id: schedId,
          });
        }
      });
    });

    // Modal bindings
    if (this._modalState) {
      const overlay = root.getElementById("modalOverlay");
      const btnCancel = root.getElementById("btnModalCancel");
      const btnSave = root.getElementById("btnModalSave");
      const zoneSelect = root.getElementById("modalZoneSelect");
      const startTimeInput = root.getElementById("modalStartTime");
      const durationInput = root.getElementById("modalDuration");
      const preview = root.getElementById("endTimePreview");

      const updatePreview = () => {
        const on = startTimeInput ? startTimeInput.value : "06:00";
        const dur = durationInput ? Number(durationInput.value) : 20;
        const off = this._calculateOffTime(on, dur);
        if (preview) {
          preview.textContent = `Watering ends at: ${off}`;
        }
      };

      if (btnCancel) {
        btnCancel.addEventListener("click", () => {
          this._modalState = null;
          this._render();
        });
      }

      if (overlay) {
        overlay.addEventListener("click", (e) => {
          if (e.target === overlay) {
            this._modalState = null;
            this._render();
          }
        });
      }

      // Day buttons
      root.querySelectorAll(".day-toggle-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const day = btn.getAttribute("data-day");
          const idx = this._modalState.days.indexOf(day);
          if (idx >= 0) {
            this._modalState.days.splice(idx, 1);
            btn.classList.remove("selected");
          } else {
            this._modalState.days.push(day);
            btn.classList.add("selected");
          }
        });
      });

      // Quick day buttons
      const btnAll = root.getElementById("btnDaysEveryday");
      if (btnAll) {
        btnAll.addEventListener("click", () => {
          this._modalState.days = DAYS_OF_WEEK.map((d) => d.short);
          root.querySelectorAll(".day-toggle-btn").forEach((b) => b.classList.add("selected"));
        });
      }
      const btnWeekdays = root.getElementById("btnDaysWeekdays");
      if (btnWeekdays) {
        btnWeekdays.addEventListener("click", () => {
          this._modalState.days = ["Mon", "Tue", "Wed", "Thu", "Fri"];
          root.querySelectorAll(".day-toggle-btn").forEach((b) => {
            const d = b.getAttribute("data-day");
            if (["Mon", "Tue", "Wed", "Thu", "Fri"].includes(d)) {
              b.classList.add("selected");
            } else {
              b.classList.remove("selected");
            }
          });
        });
      }
      const btnWeekends = root.getElementById("btnDaysWeekends");
      if (btnWeekends) {
        btnWeekends.addEventListener("click", () => {
          this._modalState.days = ["Sat", "Sun"];
          root.querySelectorAll(".day-toggle-btn").forEach((b) => {
            const d = b.getAttribute("data-day");
            if (["Sat", "Sun"].includes(d)) {
              b.classList.add("selected");
            } else {
              b.classList.remove("selected");
            }
          });
        });
      }
      const btnClear = root.getElementById("btnDaysClear");
      if (btnClear) {
        btnClear.addEventListener("click", () => {
          this._modalState.days = [];
          root.querySelectorAll(".day-toggle-btn").forEach((b) => b.classList.remove("selected"));
        });
      }

      // Duration chips
      root.querySelectorAll(".duration-chip-btn").forEach((chip) => {
        chip.addEventListener("click", () => {
          const mins = Number(chip.getAttribute("data-mins"));
          if (durationInput) durationInput.value = mins;
          root.querySelectorAll(".duration-chip-btn").forEach((c) => c.classList.remove("active"));
          chip.classList.add("active");
          updatePreview();
        });
      });

      if (startTimeInput) startTimeInput.addEventListener("input", updatePreview);
      if (durationInput) durationInput.addEventListener("input", updatePreview);

      // Save button
      if (btnSave) {
        btnSave.addEventListener("click", () => {
          const zone = zoneSelect ? Number(zoneSelect.value) : this._modalState.zoneIndex;
          const days = this._modalState.days;
          const onTime = startTimeInput ? startTimeInput.value : "06:00";
          const dur = durationInput ? Number(durationInput.value) : 20;

          if (days.length === 0) {
            alert("Please select at least one day of the week.");
            return;
          }
          if (!onTime) {
            alert("Please select a valid start time.");
            return;
          }
          if (dur <= 0) {
            alert("Duration must be at least 1 minute.");
            return;
          }

          const offTime = this._calculateOffTime(onTime, dur);

          if (this._modalState.mode === "edit") {
            this._hass.callService("intellidwell", "edit_schedule", {
              zone: zone,
              schedule_id: this._modalState.scheduleId,
              days: days,
              on_time: onTime,
              off_time: offTime,
            });
          } else {
            this._hass.callService("intellidwell", "add_schedule", {
              zone: zone,
              days: days,
              on_time: onTime,
              off_time: offTime,
            });
          }

          this._modalState = null;
          this._render();
        });
      }
    }

    // Timer modal bindings
    if (this._timerModalState) {
      const timerOverlay = root.getElementById("timerModalOverlay");
      const btnTimerCancel = root.getElementById("btnTimerCancel");
      const btnTimerStart = root.getElementById("btnTimerStart");
      const timerInput = root.getElementById("timerDurationInput");

      if (btnTimerCancel) {
        btnTimerCancel.addEventListener("click", () => {
          this._timerModalState = null;
          this._render();
        });
      }

      if (timerOverlay) {
        timerOverlay.addEventListener("click", (e) => {
          if (e.target === timerOverlay) {
            this._timerModalState = null;
            this._render();
          }
        });
      }

      root.querySelectorAll(".duration-chip-btn[data-quick-mins]").forEach((chip) => {
        chip.addEventListener("click", () => {
          const mins = Number(chip.getAttribute("data-quick-mins"));
          if (timerInput) timerInput.value = mins;
          this._timerModalState.durationMins = mins;
          root.querySelectorAll(".duration-chip-btn[data-quick-mins]").forEach((c) => c.classList.remove("active"));
          chip.classList.add("active");
        });
      });

      if (btnTimerStart) {
        btnTimerStart.addEventListener("click", () => {
          const zone = this._timerModalState.zoneIndex;
          const mins = timerInput ? Number(timerInput.value) : 15;
          if (mins <= 0) {
            alert("Duration must be at least 1 minute.");
            return;
          }
          this._hass.callService("intellidwell", "start_timer", {
            zone: zone,
            duration_mins: mins,
          });
          this._timerModalState = null;
          this._render();
        });
      }
    }
  }

  static async getConfigElement() {
    return document.createElement("intellidwell-scheduler-card-editor");
  }

  static getStubConfig(hass, unusedEntities, allEntities) {
    return {
      type: "custom:intellidwell-scheduler-card",
      title: "Sprinkler Schedules",
      show_zone_filter: true,
    };
  }
}

class IntelliDwellSchedulerCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = Object.assign(
      {
        title: "Sprinkler Schedules",
        show_zone_filter: true,
      },
      config
    );
    this.render();
  }

  set hass(hass) {
    this._hass = hass;
  }

  render() {
    this.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 14px; padding: 12px 0; font-family: inherit;">
        <div>
          <label style="display: block; font-weight: 600; font-size: 0.9rem; margin-bottom: 6px; color: var(--primary-text-color, #fff);">Card Title</label>
          <input type="text" id="editTitle" value="${this._config.title || "Sprinkler Schedules"}" 
            style="width: 100%; padding: 10px; border-radius: 8px; border: 1px solid var(--divider-color, rgba(255,255,255,0.2)); background: rgba(255,255,255,0.05); color: var(--primary-text-color, #fff); box-sizing: border-box; outline: none; font-size: 0.95rem;">
        </div>
        <div style="display: flex; align-items: center; gap: 10px;">
          <input type="checkbox" id="editFilter" ${this._config.show_zone_filter !== false ? "checked" : ""} style="width: 18px; height: 18px; cursor: pointer;">
          <label for="editFilter" style="font-weight: 500; font-size: 0.9rem; cursor: pointer; color: var(--primary-text-color, #fff);">Show Zone Filter Navigation Bar</label>
        </div>
      </div>
    `;

    const titleInput = this.querySelector("#editTitle");
    const filterInput = this.querySelector("#editFilter");

    const fireChange = () => {
      const newConfig = {
        ...this._config,
        title: titleInput ? titleInput.value : "Sprinkler Schedules",
        show_zone_filter: filterInput ? filterInput.checked : true,
      };
      this.dispatchEvent(
        new CustomEvent("config-changed", { detail: { config: newConfig } })
      );
    };

    if (titleInput) titleInput.addEventListener("input", fireChange);
    if (filterInput) filterInput.addEventListener("change", fireChange);
  }
}

customElements.define("intellidwell-scheduler-card-editor", IntelliDwellSchedulerCardEditor);
customElements.define("intellidwell-scheduler-card", IntelliDwellSchedulerCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "intellidwell-scheduler-card",
  name: "IntelliDwell Sprinkler Scheduler Card",
  description: "Interactive card to view, add, edit, and toggle sprinkler schedules for each zone.",
  preview: true,
  documentationURL: "http://192.168.1.125/scheduler",
});
console.info(
  "%c INTELLIDWELL-SCHEDULER-CARD %c v1.0.3 Loaded ",
  "color: white; background: #3b82f6; font-weight: 700;",
  "color: #3b82f6; background: #1e293b; font-weight: 700;"
);
