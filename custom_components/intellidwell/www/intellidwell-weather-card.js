/**
 * IntelliDwell Smart Weather Card for Home Assistant
 * Interactive dashboard interface for Heat Wave, Cooling Mist, Cool Wave,
 * Freeze Skip, Wind Drift Guard, Soil Moisture veto, and Rain Delay rules.
 */

const WX_DEFAULT_OPTS = {
  weather_push_enabled: true,
  rain_sensor: "",
  rain_48h_sensor: "",
  temp_sensor: "",
  weather_entity: "",
  forecast_rain_sensor: "",
  forecast_rain_48h_sensor: "",
  soil_moisture_sensor: "",
  wind_sensor: "",
  source_name: "",
  auto_rain_delay: true,
  rain_threshold: 0.25,
  collected_48h_threshold: 0.5,
  anticipated_24h_threshold: 0.15,
  anticipated_48h_threshold: 0.3,
  delay_days: 2,
  heavy_rain_threshold: 0.5,
  heavy_delay_days: 3,
  forecast_pop_threshold: 60,
  stop_active_watering: true,
  heat_wave_enabled: true,
  heat_wave_temp_threshold: 90,
  heat_wave_days: 2,
  heat_wave_boost_pct: 20,
  heat_wave_syringe_enabled: false,
  heat_wave_syringe_temp_threshold: 95,
  heat_wave_syringe_minutes: 3,
  heat_wave_syringe_time: "14:00",
  cool_wave_enabled: true,
  cool_wave_temp_threshold: 60,
  cool_wave_reduce_pct: 20,
  freeze_skip_enabled: true,
  freeze_temp_threshold: 34,
  wind_skip_enabled: true,
  wind_skip_threshold: 20,
  wind_protect_drip_exempt: true,
  soil_moisture_max_pct: 45,
};

const WX_PRESETS = {
  default: {
    label: "Recommended",
    values: {
      rain_threshold: 0.25,
      collected_48h_threshold: 0.5,
      anticipated_24h_threshold: 0.15,
      anticipated_48h_threshold: 0.3,
      forecast_pop_threshold: 60,
      heavy_rain_threshold: 0.5,
      delay_days: 2,
      heavy_delay_days: 3,
      heat_wave_enabled: true,
      heat_wave_temp_threshold: 90,
      heat_wave_days: 2,
      heat_wave_boost_pct: 20,
      heat_wave_syringe_enabled: false,
      heat_wave_syringe_temp_threshold: 95,
      heat_wave_syringe_minutes: 3,
      heat_wave_syringe_time: "14:00",
      cool_wave_enabled: true,
      cool_wave_temp_threshold: 60,
      cool_wave_reduce_pct: 20,
      freeze_skip_enabled: true,
      freeze_temp_threshold: 34,
      wind_skip_enabled: true,
      wind_skip_threshold: 20,
      wind_protect_drip_exempt: true,
      soil_moisture_max_pct: 45,
    },
  },
  arid: {
    label: "Hot & Dry",
    values: {
      rain_threshold: 0.15,
      collected_48h_threshold: 0.35,
      anticipated_24h_threshold: 0.15,
      anticipated_48h_threshold: 0.3,
      forecast_pop_threshold: 65,
      heavy_rain_threshold: 0.4,
      delay_days: 1,
      heavy_delay_days: 2,
      heat_wave_enabled: true,
      heat_wave_temp_threshold: 92,
      heat_wave_days: 2,
      heat_wave_boost_pct: 25,
      heat_wave_syringe_enabled: true,
      heat_wave_syringe_temp_threshold: 98,
      heat_wave_syringe_minutes: 2,
      heat_wave_syringe_time: "14:30",
      cool_wave_enabled: true,
      cool_wave_temp_threshold: 58,
      cool_wave_reduce_pct: 20,
      freeze_skip_enabled: true,
      freeze_temp_threshold: 33,
      wind_skip_enabled: true,
      wind_skip_threshold: 20,
      wind_protect_drip_exempt: true,
      soil_moisture_max_pct: 45,
    },
  },
  humid: {
    label: "Humid",
    values: {
      rain_threshold: 0.25,
      collected_48h_threshold: 0.5,
      anticipated_24h_threshold: 0.15,
      anticipated_48h_threshold: 0.3,
      forecast_pop_threshold: 55,
      heavy_rain_threshold: 0.5,
      delay_days: 2,
      heavy_delay_days: 3,
      heat_wave_enabled: true,
      heat_wave_temp_threshold: 90,
      heat_wave_days: 3,
      heat_wave_boost_pct: 15,
      heat_wave_syringe_enabled: false,
      heat_wave_syringe_temp_threshold: 96,
      heat_wave_syringe_minutes: 2,
      heat_wave_syringe_time: "14:00",
      cool_wave_enabled: true,
      cool_wave_temp_threshold: 64,
      cool_wave_reduce_pct: 25,
      freeze_skip_enabled: true,
      freeze_temp_threshold: 35,
      wind_skip_enabled: true,
      wind_skip_threshold: 16,
      wind_protect_drip_exempt: true,
      soil_moisture_max_pct: 40,
    },
  },
  saver: {
    label: "Water Saver",
    values: {
      rain_threshold: 0.15,
      collected_48h_threshold: 0.3,
      anticipated_24h_threshold: 0.1,
      anticipated_48h_threshold: 0.2,
      forecast_pop_threshold: 50,
      heavy_rain_threshold: 0.35,
      delay_days: 2,
      heavy_delay_days: 4,
      heat_wave_enabled: true,
      heat_wave_temp_threshold: 94,
      heat_wave_days: 3,
      heat_wave_boost_pct: 10,
      heat_wave_syringe_enabled: false,
      heat_wave_syringe_temp_threshold: 98,
      heat_wave_syringe_minutes: 2,
      heat_wave_syringe_time: "14:00",
      cool_wave_enabled: true,
      cool_wave_temp_threshold: 65,
      cool_wave_reduce_pct: 30,
      freeze_skip_enabled: true,
      freeze_temp_threshold: 36,
      wind_skip_enabled: true,
      wind_skip_threshold: 15,
      wind_protect_drip_exempt: true,
      soil_moisture_max_pct: 40,
    },
  },
};

function wxEscapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

class IntelliDwellWeatherCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = { title: "Smart Weather Control" };
    this._hass = null;
    this._draftOpts = null;
    this._dirty = false;
    this._lastEntityId = null;
    this._openSections = new Set(["sources", "heat"]);
    this._statusToast = "";
    this._statusError = "";
    this._busy = false;
    this._renderedOnce = false;
  }

  setConfig(config) {
    this._config = Object.assign({ title: "Smart Weather Control" }, config || {});
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const modEnt = this._getWeatherModifierEntity();
    const entId = modEnt ? modEnt.entity_id : null;
    if (entId && entId !== this._lastEntityId) {
      this._lastEntityId = entId;
      this._dirty = false;
    }
    if (!this._dirty && modEnt) {
      this._draftOpts = Object.assign(
        {},
        WX_DEFAULT_OPTS,
        (modEnt.attributes && modEnt.attributes.weather_options) || {}
      );
    } else if (!this._draftOpts) {
      this._draftOpts = Object.assign({}, WX_DEFAULT_OPTS);
    }
    const activeEl = this.shadowRoot && this.shadowRoot.activeElement;
    const isEditingControl =
      activeEl && (activeEl.tagName === "INPUT" || activeEl.tagName === "SELECT");
    if (this._renderedOnce && (this._dirty || isEditingControl)) {
      this._updateLiveTelemetryDom();
      return;
    }
    this._render();
  }

  getCardSize() {
    return 8;
  }

  _isWeatherModifierEntity(entityId, stateObj) {
    if (!entityId.startsWith("sensor.")) return false;
    const attrs = (stateObj && stateObj.attributes) || {};
    const regEntry =
      this._hass && this._hass.entities ? this._hass.entities[entityId] : null;
    if (regEntry && regEntry.platform) {
      return (
        regEntry.platform === "intellidwell" &&
        (attrs.weather_options !== undefined || attrs.scale_pct !== undefined)
      );
    }
    return (
      (entityId.includes("intellidwell") && entityId.includes("weather_modifier")) ||
      (attrs.weather_options !== undefined && attrs.scale_pct !== undefined)
    );
  }

  _getWeatherModifierEntity() {
    if (!this._hass || !this._hass.states) return null;
    if (this._config.entity && this._hass.states[this._config.entity]) {
      return this._hass.states[this._config.entity];
    }
    for (const [entityId, stateObj] of Object.entries(this._hass.states)) {
      if (this._isWeatherModifierEntity(entityId, stateObj)) {
        return stateObj;
      }
    }
    return null;
  }

  _getEntityOptions(domainFilter) {
    if (!this._hass || !this._hass.states) return [];
    const out = [];
    for (const [entityId, st] of Object.entries(this._hass.states)) {
      if (!entityId.startsWith(domainFilter + ".")) continue;
      if (entityId.includes("intellidwell") && entityId.includes("weather_modifier")) continue;
      const fn = (st.attributes && st.attributes.friendly_name) || entityId;
      out.push({ id: entityId, name: `${fn} (${entityId})` });
    }
    out.sort((a, b) => a.name.localeCompare(b.name));
    return out;
  }

  _selectHtml(id, key, domain, currentVal) {
    const list = this._getEntityOptions(domain);
    const hasCustom = currentVal && !list.some((item) => item.id === currentVal);
    let optionsHtml = `<option value="">-- Not Set --</option>`;
    if (hasCustom) {
      optionsHtml += `<option value="${wxEscapeHtml(currentVal)}" selected>${wxEscapeHtml(currentVal)}</option>`;
    }
    for (const item of list) {
      const sel = item.id === currentVal ? " selected" : "";
      optionsHtml += `<option value="${wxEscapeHtml(item.id)}"${sel}>${wxEscapeHtml(item.name)}</option>`;
    }
    return `<select class="ctrl-select" id="${id}" data-key="${key}">${optionsHtml}</select>`;
  }

  _sliderHtml(id, key, label, value, min, max, step, unit, fmtFn) {
    const numVal = Number.isFinite(Number(value)) ? Number(value) : min;
    const disp = fmtFn ? fmtFn(numVal) : `${numVal}${unit || ""}`;
    return `
      <div class="slider-row">
        <div class="slider-head">
          <span class="slider-lbl">${wxEscapeHtml(label)}</span>
          <span class="slider-val" id="${id}-val">${wxEscapeHtml(disp)}</span>
        </div>
        <input type="range" class="ctrl-range" id="${id}" data-key="${key}"
          data-unit="${wxEscapeHtml(unit || "")}"
          min="${min}" max="${max}" step="${step}" value="${numVal}">
      </div>
    `;
  }

  _toggleHtml(id, key, title, desc, checked) {
    return `
      <label class="toggle-row" for="${id}">
        <div class="toggle-copy">
          <div class="toggle-title">${wxEscapeHtml(title)}</div>
          ${desc ? `<div class="toggle-desc">${wxEscapeHtml(desc)}</div>` : ""}
        </div>
        <input type="checkbox" class="ctrl-chk" id="${id}" data-key="${key}" ${checked ? "checked" : ""}>
      </label>
    `;
  }

  _computeSimulator() {
    const o = this._draftOpts || WX_DEFAULT_OPTS;
    const coolMin = o.cool_wave_enabled
      ? Math.round((20 * Math.max(50, 100 - Number(o.cool_wave_reduce_pct || 20))) / 100)
      : 20;
    const heatMin = o.heat_wave_enabled
      ? Math.round((20 * Math.min(160, 100 + Number(o.heat_wave_boost_pct || 20))) / 100)
      : 20;
    return {
      coolMin,
      heatMin,
      windMode: o.wind_skip_enabled
        ? o.wind_protect_drip_exempt
          ? "Drip Safe"
          : "Skip All"
        : "Off",
      mistText: o.heat_wave_syringe_enabled
        ? `${o.heat_wave_syringe_minutes}m @ ${o.heat_wave_syringe_time}`
        : "Off",
    };
  }

  _updateSimulatorDom() {
    if (!this.shadowRoot) return;
    const sim = this._computeSimulator();
    const set = (id, text) => {
      const el = this.shadowRoot.getElementById(id);
      if (el) el.textContent = text;
    };
    set("sim-cool", `${sim.coolMin}m`);
    set("sim-heat", `${sim.heatMin}m`);
    set("sim-wind", sim.windMode);
    set("sim-mist", sim.mistText);
  }

  _updateLiveTelemetryDom() {
    if (!this.shadowRoot || !this._hass) return;
    const modEnt = this._getWeatherModifierEntity();
    const attrs = (modEnt && modEnt.attributes) || {};
    const ev = attrs.weather_evaluation || {};
    const fmtVal = (v, suffix = "") =>
      v !== undefined && v !== null && v !== "" ? `${v}${suffix}` : "—";
    const set = (id, text) => {
      const el = this.shadowRoot.getElementById(id);
      if (el) el.textContent = text;
    };
    const rainDelayDays = Number(attrs.rain_delay_days || 0);
    set("wx-status-pill", rainDelayDays > 0 ? `Rain Delay ${rainDelayDays}d` : (modEnt ? modEnt.state : "Not Connected"));
    set("wx-met-temp", `${fmtVal(ev.temp_f ?? attrs.temp, "°F")} / ${fmtVal(ev.tonight_low_f, "°F")}`);
    set("wx-met-rain", `${fmtVal(ev.rain_today_in ?? attrs.rain_today_in, '"')} / ${fmtVal(ev.collected_48h_in, '"')}`);
    set("wx-met-fcst", `${fmtVal(ev.anticipated_24h_in, '"')} / ${fmtVal(ev.anticipated_48h_in, '"')} (${fmtVal(ev.pop_pct, "%")})`);
    set("wx-met-wind", `${fmtVal(ev.wind_mph ?? attrs.wind_speed_mph, " mph")} · ${fmtVal(ev.soil_moisture_pct ?? attrs.soil_moisture_pct, "%")}`);
  }

  async _callSvc(service, data) {
    if (!this._hass || this._busy) return;
    this._busy = true;
    this._statusError = "";
    this._render();
    try {
      await this._hass.callService("intellidwell", service, data);
    } catch (err) {
      this._statusError = (err && err.message) || String(err);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _saveRules(applyNow) {
    const modEnt = this._getWeatherModifierEntity();
    const entryId =
      modEnt && modEnt.attributes ? modEnt.attributes.config_entry_id : undefined;
    const payload = {
      options: Object.assign({}, this._draftOpts),
      apply_now: Boolean(applyNow),
    };
    if (entryId) payload.config_entry_id = entryId;
    await this._callSvc("update_weather_settings", payload);
    if (!this._statusError) {
      this._dirty = false;
      this._statusToast = applyNow
        ? "Saved rules and pushed modifier to controller."
        : "Saved Smart Weather rules.";
      this._render();
      setTimeout(() => {
        this._statusToast = "";
        this._render();
      }, 3500);
    }
  }

  _render() {
    if (!this._hass || !this.shadowRoot) return;
    const modEnt = this._getWeatherModifierEntity();
    const attrs = (modEnt && modEnt.attributes) || {};
    const ev = attrs.weather_evaluation || {};
    const recMod = ev.recommended_modifier || {};
    const o = this._draftOpts || WX_DEFAULT_OPTS;
    const entryId = attrs.config_entry_id || undefined;
    const sim = this._computeSimulator();

    const stateStr = modEnt ? modEnt.state : "Not Connected";
    const isFreeze = Boolean(attrs.freeze_skip || attrs.inhibit);
    const isWind = Boolean(attrs.wind_skip);
    const isHeat = Boolean(attrs.heat_wave_active || Number(attrs.scale_pct || 100) > 100);
    const isCool = Boolean(attrs.cool_wave_active || Number(attrs.scale_pct || 100) < 100);
    const rainDelayDays = Number(attrs.rain_delay_days || 0);

    let badgeColor = "#10b981";
    if (isFreeze) badgeColor = "#38bdf8";
    else if (isWind || rainDelayDays > 0) badgeColor = "#f59e0b";
    else if (isHeat) badgeColor = "#ef4444";
    else if (isCool) badgeColor = "#06b6d4";

    const fmtVal = (v, suffix = "") =>
      v !== undefined && v !== null && v !== "" ? `${v}${suffix}` : "—";

    const rain24 = fmtVal(ev.rain_today_in ?? attrs.rain_today_in, '"');
    const rain48 = fmtVal(ev.collected_48h_in, '"');
    const ant24 = fmtVal(ev.anticipated_24h_in, '"');
    const ant48 = fmtVal(ev.anticipated_48h_in, '"');
    const pop = fmtVal(ev.pop_pct, "%");
    const tempF = fmtVal(ev.temp_f ?? attrs.temp, "°F");
    const lowF = fmtVal(ev.tonight_low_f, "°F");
    const windMph = fmtVal(ev.wind_mph ?? attrs.wind_speed_mph, " mph");
    const soilPct = fmtVal(ev.soil_moisture_pct ?? attrs.soil_moisture_pct, "%");
    const syrReady = Boolean((recMod.syringe && recMod.syringe.enabled) || o.heat_wave_syringe_enabled);
    const recSummary = recMod.reason || "Standard Watering (100%)";
    const activeSummary = attrs.active
      ? `${attrs.reason || stateStr} (${attrs.scale_pct || 100}%)`
      : "No active override on controller";

    const section = (key, icon, title, accent, bodyHtml) => {
      const open = this._openSections.has(key);
      return `
        <div class="acc ${open ? "open" : ""}" style="--sec-accent: ${accent};">
          <button type="button" class="acc-head" data-sec="${key}">
            <span>${icon} ${wxEscapeHtml(title)}</span>
            <span class="chev">${open ? "▾" : "▸"}</span>
          </button>
          <div class="acc-body">${bodyHtml}</div>
        </div>
      `;
    };

    const mistTimes = ["12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30", "16:00"];
    const mistTimeOpts = mistTimes
      .map((t) => {
        const [h, m] = t.split(":").map(Number);
        const h12 = h > 12 ? h - 12 : h;
        const lbl = `${h12}:${String(m).padStart(2, "0")} PM`;
        const sel = o.heat_wave_syringe_time === t ? " selected" : "";
        return `<option value="${t}"${sel}>${lbl}</option>`;
      })
      .join("");

    const dayOpts = (selected) =>
      [1, 2, 3, 4, 5]
        .map((d) => `<option value="${d}"${Number(selected) === d ? " selected" : ""}>${d} Days</option>`)
        .join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          --accent: var(--primary-color, #3b82f6);
          --card-bg: var(--ha-card-background, var(--card-background-color, #1e293b));
          --surface-2: rgba(15, 23, 42, 0.45);
          --border: var(--divider-color, rgba(255, 255, 255, 0.12));
          --txt-1: var(--primary-text-color, #f8fafc);
          --txt-2: var(--secondary-text-color, #94a3b8);
        }
        ha-card {
          padding: 16px;
          border-radius: var(--ha-card-border-radius, 16px);
          background: var(--card-bg);
          color: var(--txt-1);
          font-family: inherit;
          box-sizing: border-box;
        }
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          padding-bottom: 12px;
          margin-bottom: 12px;
          border-bottom: 1px solid var(--border);
          flex-wrap: wrap;
        }
        .title-wrap {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 1.15rem;
          font-weight: 700;
        }
        .status-pill {
          padding: 5px 11px;
          border-radius: 999px;
          font-size: 0.78rem;
          font-weight: 700;
          border: 1px solid currentColor;
          background: rgba(255,255,255,0.05);
        }
        .banner {
          background: var(--surface-2);
          border: 1px solid var(--border);
          border-radius: 12px;
          padding: 12px;
          margin-bottom: 12px;
        }
        .metrics-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(115px, 1fr));
          gap: 8px;
          margin-top: 10px;
        }
        .metric-box {
          background: rgba(255,255,255,0.04);
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 8px 10px;
        }
        .metric-lbl { font-size: 0.7rem; color: var(--txt-2); }
        .metric-val { font-size: 0.88rem; font-weight: 700; margin-top: 2px; }
        .btn-row {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-top: 10px;
        }
        button.btn {
          border-radius: 10px;
          border: 1px solid var(--border);
          background: rgba(255,255,255,0.06);
          color: var(--txt-1);
          padding: 8px 12px;
          font-size: 0.8rem;
          font-weight: 600;
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          gap: 5px;
          font-family: inherit;
        }
        button.btn:hover { filter: brightness(1.15); }
        button.btn:disabled { opacity: 0.55; cursor: not-allowed; }
        button.btn-primary {
          background: var(--accent);
          border-color: transparent;
          color: #ffffff;
        }
        button.btn-mist {
          border-color: rgba(56, 189, 248, 0.5);
          color: #38bdf8;
        }
        .preset-row {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-bottom: 10px;
        }
        .chip {
          border: 1px solid var(--border);
          background: var(--surface-2);
          color: var(--txt-1);
          border-radius: 999px;
          padding: 5px 11px;
          font-size: 0.76rem;
          font-weight: 600;
          cursor: pointer;
          font-family: inherit;
        }
        .chip:hover { border-color: var(--accent); }
        .sim-bar {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 6px;
          padding: 10px;
          background: var(--surface-2);
          border: 1px solid var(--border);
          border-radius: 12px;
          margin-bottom: 12px;
          text-align: center;
        }
        .sim-val { font-size: 0.92rem; font-weight: 800; }
        .sim-lbl { font-size: 0.68rem; color: var(--txt-2); }
        .acc {
          border: 1px solid var(--border);
          border-left: 3px solid var(--sec-accent, var(--accent));
          border-radius: 12px;
          margin-bottom: 10px;
          background: var(--surface-2);
          overflow: hidden;
        }
        .acc-head {
          width: 100%;
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 11px 12px;
          background: transparent;
          border: none;
          color: var(--txt-1);
          font-size: 0.88rem;
          font-weight: 700;
          cursor: pointer;
          font-family: inherit;
          text-align: left;
        }
        .acc-body { display: none; padding: 0 12px 12px; border-top: 1px solid var(--border); }
        .acc.open .acc-body { display: block; padding-top: 10px; }
        .toggle-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 12px;
          padding: 7px 0;
          cursor: pointer;
        }
        .toggle-title { font-size: 0.84rem; font-weight: 600; }
        .toggle-desc { font-size: 0.73rem; color: var(--txt-2); margin-top: 2px; line-height: 1.35; }
        .ctrl-chk { width: 18px; height: 18px; accent-color: var(--accent); cursor: pointer; flex-shrink: 0; }
        .slider-row { margin: 8px 0; }
        .slider-head { display: flex; justify-content: space-between; font-size: 0.8rem; margin-bottom: 3px; }
        .slider-lbl { color: var(--txt-2); }
        .slider-val { font-weight: 700; color: #38bdf8; }
        .ctrl-range { width: 100%; accent-color: var(--accent); cursor: pointer; }
        .field-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 8px;
          margin: 6px 0;
        }
        .field-lbl { display: block; font-size: 0.74rem; color: var(--txt-2); margin-bottom: 3px; }
        .ctrl-select, .ctrl-input {
          width: 100%;
          padding: 7px 9px;
          border-radius: 8px;
          border: 1px solid var(--border);
          background: rgba(15, 23, 42, 0.7);
          color: var(--txt-1);
          font-size: 0.8rem;
          font-family: inherit;
          box-sizing: border-box;
        }
        .alert {
          padding: 9px 12px;
          border-radius: 10px;
          font-size: 0.8rem;
          font-weight: 600;
          margin-bottom: 10px;
        }
        .alert-warn { background: rgba(239, 68, 68, 0.14); border: 1px solid rgba(239, 68, 68, 0.45); color: #fca5a5; }
        .alert-ok { background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.45); color: #6ee7b7; }
        .alert-draft { background: rgba(245, 158, 11, 0.14); border: 1px solid rgba(245, 158, 11, 0.4); color: #fcd34d; }
        .footer {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-top: 12px;
        }
        .footer button { flex: 1; justify-content: center; min-width: 130px; padding: 10px 14px; }
      </style>

      <ha-card>
        <div class="header">
          <div class="title-wrap">
            <span>🌦️</span>
            <span>${wxEscapeHtml(this._config.title || "Smart Weather Control")}</span>
          </div>
          <span class="status-pill" id="wx-status-pill" style="color: ${badgeColor};">
            ${rainDelayDays > 0 ? `Rain Delay ${rainDelayDays}d` : wxEscapeHtml(stateStr)}
          </span>
        </div>

        ${!modEnt ? `<div class="alert alert-warn">No IntelliDwell Weather Modifier sensor found. Ensure the IntelliDwell integration (v1.4.0+) is loaded.</div>` : ""}
        ${ev.hard_freeze_warning ? `<div class="alert alert-warn">❄️ Hard Freeze Forecast (&le; 28°F in 7-day outlook): Consider winterizing / blowing out irrigation lines.</div>` : ""}
        ${this._statusError ? `<div class="alert alert-warn">${wxEscapeHtml(this._statusError)}</div>` : ""}
        ${this._statusToast ? `<div class="alert alert-ok">${wxEscapeHtml(this._statusToast)}</div>` : ""}
        ${this._dirty ? `<div class="alert alert-draft">Unsaved rule adjustments — tap <strong>Save Rules</strong> below to persist &amp; apply.</div>` : ""}

        <div class="banner">
          <div style="font-size:0.84rem;font-weight:700;">Recommended: <span style="color:${badgeColor};">${wxEscapeHtml(recSummary)}</span></div>
          <div style="font-size:0.76rem;color:var(--txt-2);margin-top:2px;">ESP32 Status: ${wxEscapeHtml(activeSummary)} · Source: ${wxEscapeHtml(ev.source || o.source_name || "Home Assistant")}</div>
          <div class="metrics-grid">
            <div class="metric-box"><div class="metric-lbl">Temp / Low</div><div class="metric-val" id="wx-met-temp">${tempF} / ${lowF}</div></div>
            <div class="metric-box"><div class="metric-lbl">Collected 24h / 48h</div><div class="metric-val" id="wx-met-rain">${rain24} / ${rain48}</div></div>
            <div class="metric-box"><div class="metric-lbl">Forecast 24h / 48h</div><div class="metric-val" id="wx-met-fcst">${ant24} / ${ant48} (${pop})</div></div>
            <div class="metric-box"><div class="metric-lbl">Wind / Soil</div><div class="metric-val" id="wx-met-wind">${windMph} · ${soilPct}</div></div>
          </div>
          <div class="btn-row">
            <button type="button" class="btn btn-primary" id="btn-push-mod" ${this._busy || !modEnt ? "disabled" : ""}>⚡ Push Recommended</button>
            <button type="button" class="btn" id="btn-clear-mod" ${this._busy || !modEnt ? "disabled" : ""}>↺ Clear Override</button>
            ${syrReady ? `<button type="button" class="btn btn-mist" id="btn-run-mist" ${this._busy || !modEnt ? "disabled" : ""}>💦 Run ${Number(o.heat_wave_syringe_minutes || 3)}m Cooling Mist</button>` : ""}
          </div>
        </div>

        <div class="preset-row">
          ${Object.entries(WX_PRESETS)
            .map(([pKey, p]) => `<button type="button" class="chip" data-preset="${pKey}">${wxEscapeHtml(p.label)}</button>`)
            .join("")}
        </div>

        <div class="sim-bar">
          <div><div class="sim-val" id="sim-cool" style="color:#38bdf8;">${sim.coolMin}m</div><div class="sim-lbl">Cool Wave</div></div>
          <div><div class="sim-val">20m</div><div class="sim-lbl">Normal Base</div></div>
          <div><div class="sim-val" id="sim-heat" style="color:#f87171;">${sim.heatMin}m</div><div class="sim-lbl">Heat Wave</div></div>
          <div><div class="sim-val" id="sim-wind" style="color:#34d399;">${wxEscapeHtml(sim.windMode)}</div><div class="sim-lbl">Wind Rule</div></div>
        </div>

        ${section("sources", "📡", "Weather Entities & Auto-Push", "#38bdf8", `
          ${this._toggleHtml("opt-wx-push", "weather_push_enabled", "Enable Automatic Weather Push", "Automatically push HA sensors & active modifiers to the controller over LAN.", o.weather_push_enabled)}
          ${this._toggleHtml("opt-auto-delay", "auto_rain_delay", "Automatically Set Rain Delays", "Apply configured delay days when rain thresholds trigger.", o.auto_rain_delay)}
          ${this._toggleHtml("opt-stop-rain", "stop_active_watering", "Stop Active Watering on Rain", "Cancel running zone timers immediately if today's rain reaches threshold.", o.stop_active_watering)}
          <div class="field-grid">
            <div><label class="field-lbl">Forecast Entity (weather.*)</label>${this._selectHtml("ent-wx", "weather_entity", "weather", o.weather_entity)}</div>
            <div><label class="field-lbl">Daily Rain Sensor (in)</label>${this._selectHtml("ent-r24", "rain_sensor", "sensor", o.rain_sensor)}</div>
            <div><label class="field-lbl">48h Collected Rain Sensor</label>${this._selectHtml("ent-r48", "rain_48h_sensor", "sensor", o.rain_48h_sensor)}</div>
            <div><label class="field-lbl">Outdoor Temp Sensor</label>${this._selectHtml("ent-temp", "temp_sensor", "sensor", o.temp_sensor)}</div>
            <div><label class="field-lbl">Forecast 24h Rain Sensor</label>${this._selectHtml("ent-f24", "forecast_rain_sensor", "sensor", o.forecast_rain_sensor)}</div>
            <div><label class="field-lbl">Forecast 48h Rain Sensor</label>${this._selectHtml("ent-f48", "forecast_rain_48h_sensor", "sensor", o.forecast_rain_48h_sensor)}</div>
            <div><label class="field-lbl">Wind Speed Sensor (mph)</label>${this._selectHtml("ent-wind", "wind_sensor", "sensor", o.wind_sensor)}</div>
            <div><label class="field-lbl">Soil Moisture Sensor (%)</label>${this._selectHtml("ent-soil", "soil_moisture_sensor", "sensor", o.soil_moisture_sensor)}</div>
          </div>
          <div style="margin-top:6px;">
            <label class="field-lbl">Friendly Weather Source Name (Optional)</label>
            <input type="text" class="ctrl-input" id="opt-src-name" data-key="source_name" value="${wxEscapeHtml(o.source_name || "")}" placeholder="e.g. Ambient PWS">
          </div>
        `)}

        ${section("rain", "🌧️", "Rain Delay Triggers", "#3b82f6", `
          ${this._sliderHtml("sl-r24", "rain_threshold", "Collected 24h Rain Trigger", o.rain_threshold, 0.05, 1.5, 0.05, '"', (v) => `${Number(v).toFixed(2)}"`)}
          ${this._sliderHtml("sl-r48", "collected_48h_threshold", "Collected 48h Rain Trigger", o.collected_48h_threshold, 0.1, 2.5, 0.05, '"', (v) => `${Number(v).toFixed(2)}"`)}
          ${this._sliderHtml("sl-a24", "anticipated_24h_threshold", "Forecast 24h Rain Trigger", o.anticipated_24h_threshold, 0.05, 1.5, 0.05, '"', (v) => `${Number(v).toFixed(2)}"`)}
          ${this._sliderHtml("sl-a48", "anticipated_48h_threshold", "Forecast 48h Rain Trigger", o.anticipated_48h_threshold, 0.1, 2.5, 0.05, '"', (v) => `${Number(v).toFixed(2)}"`)}
          ${this._sliderHtml("sl-pop", "forecast_pop_threshold", "Forecast Rain Chance Cutoff", o.forecast_pop_threshold, 10, 100, 5, "%")}
          ${this._sliderHtml("sl-hvy", "heavy_rain_threshold", "Heavy Storm Combined 24h Trigger", o.heavy_rain_threshold, 0.2, 2.5, 0.05, '"', (v) => `${Number(v).toFixed(2)}"`)}
          <div class="field-grid">
            <div><label class="field-lbl">Standard Delay Duration</label><select class="ctrl-select" id="sel-std-days" data-key="delay_days" data-type="int">${dayOpts(o.delay_days)}</select></div>
            <div><label class="field-lbl">Heavy Delay Duration</label><select class="ctrl-select" id="sel-hvy-days" data-key="heavy_delay_days" data-type="int">${dayOpts(o.heavy_delay_days)}</select></div>
          </div>
        `)}

        ${section("heat", "🔥", "Heat Wave & Afternoon Cooling Mist", "#ef4444", `
          ${this._toggleHtml("opt-hw-en", "heat_wave_enabled", "Heat Wave Schedule Boost", "Automatically lengthens scheduled runtimes during multi-day hot streaks.", o.heat_wave_enabled)}
          ${this._sliderHtml("sl-hw-temp", "heat_wave_temp_threshold", "Heat Trigger Temperature", o.heat_wave_temp_threshold, 75, 112, 1, "°F")}
          ${this._sliderHtml("sl-hw-days", "heat_wave_days", "Consecutive Hot Days Required", o.heat_wave_days, 1, 5, 1, " days")}
          ${this._sliderHtml("sl-hw-boost", "heat_wave_boost_pct", "Extra Watering Boost", o.heat_wave_boost_pct, 5, 60, 5, "%", (v) => `+${v}%`)}
          <hr style="border:none;border-top:1px solid var(--border);margin:8px 0;">
          ${this._toggleHtml("opt-syr-en", "heat_wave_syringe_enabled", "Afternoon Lawn Cooling Mist (Heat Syringe)", "Quick 1-5 min afternoon mist cools heat-stressed grass blades without soaking soil; drip/flower beds stay skipped.", o.heat_wave_syringe_enabled)}
          ${this._sliderHtml("sl-syr-temp", "heat_wave_syringe_temp_threshold", "Cooling Mist Trigger Temp", o.heat_wave_syringe_temp_threshold, 85, 112, 1, "°F")}
          ${this._sliderHtml("sl-syr-min", "heat_wave_syringe_minutes", "Cooling Mist Duration per Lawn Zone", o.heat_wave_syringe_minutes, 1, 5, 1, " min")}
          <div><label class="field-lbl">Afternoon Trigger Window (<span id="sim-mist">${wxEscapeHtml(sim.mistText)}</span>)</label><select class="ctrl-select" id="sel-syr-time" data-key="heat_wave_syringe_time">${mistTimeOpts}</select></div>
        `)}

        ${section("cool", "❄️", "Cool Wave Water Saver", "#06b6d4", `
          ${this._toggleHtml("opt-cw-en", "cool_wave_enabled", "Trim Watering on Cool Days", "Reduces scheduled runtimes automatically when daytime highs stay mild.", o.cool_wave_enabled)}
          ${this._sliderHtml("sl-cw-temp", "cool_wave_temp_threshold", "Cool High Temp Threshold ≤", o.cool_wave_temp_threshold, 40, 75, 1, "°F")}
          ${this._sliderHtml("sl-cw-red", "cool_wave_reduce_pct", "Runtime Reduction", o.cool_wave_reduce_pct, 5, 50, 5, "%", (v) => `-${v}%`)}
        `)}

        ${section("protect", "🛡️", "Freeze, Wind & Soil Moisture Guards", "#f59e0b", `
          ${this._toggleHtml("opt-frz-en", "freeze_skip_enabled", "Freeze Skip Protection", "Suspends watering when current temp or tonight's low reaches freezing.", o.freeze_skip_enabled)}
          ${this._sliderHtml("sl-frz-temp", "freeze_temp_threshold", "Freeze Cutoff Temperature ≤", o.freeze_temp_threshold, 25, 45, 1, "°F")}
          <hr style="border:none;border-top:1px solid var(--border);margin:8px 0;">
          ${this._toggleHtml("opt-wnd-en", "wind_skip_enabled", "Wind Drift Guard", "Pauses overhead spray zones in high wind to prevent sidewalk/street overspray.", o.wind_skip_enabled)}
          ${this._sliderHtml("sl-wnd-mph", "wind_skip_threshold", "Max Safe Wind Speed", o.wind_skip_threshold, 8, 50, 1, " mph")}
          ${this._toggleHtml("opt-wnd-drip", "wind_protect_drip_exempt", "Keep Drip / Flower Beds Running in Wind", "Ground-level drip and shrub zones ignore high wind skips.", o.wind_protect_drip_exempt)}
          <hr style="border:none;border-top:1px solid var(--border);margin:8px 0;">
          ${this._sliderHtml("sl-soil", "soil_moisture_max_pct", "Soil Saturation Veto Ceiling", o.soil_moisture_max_pct, 15, 85, 1, "%")}
        `)}

        <div class="footer">
          ${this._dirty ? `<button type="button" class="btn" id="btn-discard" ${this._busy ? "disabled" : ""}>Discard Changes</button>` : ""}
          <button type="button" class="btn" id="btn-save" ${this._busy || !modEnt ? "disabled" : ""}>💾 Save Rules</button>
          <button type="button" class="btn btn-primary" id="btn-save-push" ${this._busy || !modEnt ? "disabled" : ""}>⚡ Save &amp; Push Now</button>
        </div>
      </ha-card>
    `;

    this._renderedOnce = true;
    this._bindEvents(entryId);
  }

  _bindEvents(entryId) {
    const root = this.shadowRoot;
    if (!root) return;

    root.querySelectorAll(".acc-head").forEach((btn) => {
      btn.addEventListener("click", () => {
        const sec = btn.getAttribute("data-sec");
        if (!sec) return;
        if (this._openSections.has(sec)) this._openSections.delete(sec);
        else this._openSections.add(sec);
        this._render();
      });
    });

    root.querySelectorAll("[data-preset]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.getAttribute("data-preset");
        const preset = WX_PRESETS[key];
        if (!preset) return;
        this._draftOpts = Object.assign({}, this._draftOpts || WX_DEFAULT_OPTS, preset.values);
        this._dirty = true;
        this._statusToast = `Loaded "${preset.label}" preset — tap Save Rules to persist.`;
        this._render();
      });
    });

    root.querySelectorAll(".ctrl-range").forEach((inp) => {
      inp.addEventListener("input", () => {
        const key = inp.getAttribute("data-key");
        const unit = inp.getAttribute("data-unit") || "";
        const val = Number(inp.value);
        this._draftOpts[key] = val;
        this._dirty = true;
        const lblEl = root.getElementById(`${inp.id}-val`);
        if (lblEl) {
          if (unit === '"') lblEl.textContent = `${val.toFixed(2)}"`;
          else if (key === "heat_wave_boost_pct") lblEl.textContent = `+${val}%`;
          else if (key === "cool_wave_reduce_pct") lblEl.textContent = `-${val}%`;
          else lblEl.textContent = `${val}${unit}`;
        }
        this._updateSimulatorDom();
      });
    });

    root.querySelectorAll(".ctrl-chk").forEach((chk) => {
      chk.addEventListener("change", () => {
        const key = chk.getAttribute("data-key");
        this._draftOpts[key] = Boolean(chk.checked);
        this._dirty = true;
        if (key === "heat_wave_syringe_enabled") {
          this._render();
        } else {
          this._updateSimulatorDom();
        }
      });
    });

    root.querySelectorAll(".ctrl-select").forEach((sel) => {
      sel.addEventListener("change", () => {
        const key = sel.getAttribute("data-key");
        const dtype = sel.getAttribute("data-type");
        this._draftOpts[key] = dtype === "int" ? parseInt(sel.value, 10) : sel.value;
        this._dirty = true;
        this._updateSimulatorDom();
      });
    });

    const srcName = root.getElementById("opt-src-name");
    if (srcName) {
      srcName.addEventListener("input", () => {
        this._draftOpts.source_name = srcName.value;
        this._dirty = true;
      });
    }

    const pushBtn = root.getElementById("btn-push-mod");
    if (pushBtn) {
      pushBtn.addEventListener("click", () =>
        this._callSvc("apply_weather_modifier", Object.assign({ mode: "recommended" }, entryId ? { config_entry_id: entryId } : {}))
      );
    }

    const clearBtn = root.getElementById("btn-clear-mod");
    if (clearBtn) {
      clearBtn.addEventListener("click", () =>
        this._callSvc("apply_weather_modifier", Object.assign({ mode: "clear" }, entryId ? { config_entry_id: entryId } : {}))
      );
    }

    const mistBtn = root.getElementById("btn-run-mist");
    if (mistBtn) {
      mistBtn.addEventListener("click", () => {
        const mins = Number((this._draftOpts && this._draftOpts.heat_wave_syringe_minutes) || 3);
        this._callSvc("run_cooling_mist", Object.assign({ minutes: mins }, entryId ? { config_entry_id: entryId } : {}));
      });
    }

    const discardBtn = root.getElementById("btn-discard");
    if (discardBtn) {
      discardBtn.addEventListener("click", () => {
        const modEnt = this._getWeatherModifierEntity();
        this._dirty = false;
        this._statusToast = "";
        this._draftOpts = Object.assign(
          {},
          WX_DEFAULT_OPTS,
          (modEnt && modEnt.attributes && modEnt.attributes.weather_options) || {}
        );
        this._render();
      });
    }

    const saveBtn = root.getElementById("btn-save");
    if (saveBtn) saveBtn.addEventListener("click", () => this._saveRules(false));

    const savePushBtn = root.getElementById("btn-save-push");
    if (savePushBtn) savePushBtn.addEventListener("click", () => this._saveRules(true));
  }

  static async getConfigElement() {
    return document.createElement("intellidwell-weather-card-editor");
  }

  static getStubConfig() {
    return {
      type: "custom:intellidwell-weather-card",
      title: "Smart Weather Control",
    };
  }
}

class IntelliDwellWeatherCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = Object.assign({ title: "Smart Weather Control", entity: "" }, config || {});
    this.render();
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  render() {
    const states = (this._hass && this._hass.states) || {};
    const candidates = Object.entries(states)
      .filter(([eid, st]) => eid.startsWith("sensor.") && (eid.includes("weather_modifier") || (st.attributes && st.attributes.weather_options !== undefined)))
      .map(([eid, st]) => `<option value="${wxEscapeHtml(eid)}"${this._config.entity === eid ? " selected" : ""}>${wxEscapeHtml((st.attributes && st.attributes.friendly_name) || eid)} (${wxEscapeHtml(eid)})</option>`)
      .join("");

    this.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:12px;padding:10px 0;font-family:inherit;">
        <div>
          <label style="display:block;font-weight:600;font-size:0.9rem;margin-bottom:4px;">Card Title</label>
          <input type="text" id="wxTitle" value="${wxEscapeHtml(this._config.title || "Smart Weather Control")}"
            style="width:100%;padding:9px;border-radius:8px;border:1px solid var(--divider-color, rgba(255,255,255,0.2));background:rgba(255,255,255,0.05);color:inherit;box-sizing:border-box;">
        </div>
        <div>
          <label style="display:block;font-weight:600;font-size:0.9rem;margin-bottom:4px;">Weather Modifier Sensor (Optional)</label>
          <select id="wxEntity" style="width:100%;padding:9px;border-radius:8px;border:1px solid var(--divider-color, rgba(255,255,255,0.2));background:rgba(15,23,42,0.7);color:inherit;box-sizing:border-box;">
            <option value="">Auto-detect IntelliDwell controller</option>
            ${candidates}
          </select>
        </div>
      </div>
    `;

    const titleEl = this.querySelector("#wxTitle");
    const entEl = this.querySelector("#wxEntity");
    const emit = () => {
      const next = { ...this._config, title: titleEl ? titleEl.value : "Smart Weather Control" };
      if (entEl && entEl.value) next.entity = entEl.value;
      else delete next.entity;
      this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: next } }));
    };
    if (titleEl) titleEl.addEventListener("input", emit);
    if (entEl) entEl.addEventListener("change", emit);
  }
}

customElements.define("intellidwell-weather-card-editor", IntelliDwellWeatherCardEditor);
customElements.define("intellidwell-weather-card", IntelliDwellWeatherCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "intellidwell-weather-card",
  name: "IntelliDwell Smart Weather Card",
  description: "Configure Rain Delays, Heat Wave boost, Cooling Mist, Cool Wave, Freeze, Wind & Soil rules directly from your dashboard.",
  preview: true,
  documentationURL: "https://github.com/TannerNelson16/ha-intellidwell",
});
console.info(
  "%c INTELLIDWELL-WEATHER-CARD %c v1.4.0 Loaded ",
  "color: white; background: #0284c7; font-weight: 700;",
  "color: #0284c7; background: #0f172a; font-weight: 700;"
);
