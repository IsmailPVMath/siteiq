import { FormEvent, useMemo, useState } from "react";
import type { GateAnalyzeRequest, LandUse } from "../types/gate";

interface Props {
  loading: boolean;
  onSubmit: (body: GateAnalyzeRequest) => void;
}

export function AnalysisForm({ loading, onSubmit }: Props) {
  const [projectName, setProjectName] = useState("Gate POC");
  const [lat, setLat] = useState("48.1351");
  const [lon, setLon] = useState("11.5820");
  const [areaHa, setAreaHa] = useState("25");
  const [country, setCountry] = useState("Germany");
  const [landUse, setLandUse] = useState<LandUse>("Standard");
  const [mountType, setMountType] = useState("Fixed Tilt");

  const latNum = Number(lat);
  const lonNum = Number(lon);

  const mapSrc = useMemo(() => {
    if (!Number.isFinite(latNum) || !Number.isFinite(lonNum)) return "";
    const delta = 0.08;
    const bbox = [lonNum - delta, latNum - delta, lonNum + delta, latNum + delta].join(
      "%2C",
    );
    return `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${latNum}%2C${lonNum}`;
  }, [latNum, lonNum]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onSubmit({
      project_name: projectName.trim() || "Gate analysis",
      lat: latNum,
      lon: lonNum,
      area_ha: Number(areaHa),
      land_use: landUse,
      mount_type: mountType,
      country: country.trim(),
      run_layout: false,
    });
  }

  return (
    <div className="card">
      <h2>Site setup</h2>
      <p className="hint">
        Pin coordinates and area — same inputs as SiteIQ screening. Layout/BOM skipped in POC
        for speed.
      </p>
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="project">Project name</label>
          <input
            id="project"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
          />
        </div>
        <div className="grid-2">
          <div className="field">
            <label htmlFor="lat">Latitude</label>
            <input
              id="lat"
              type="number"
              step="any"
              value={lat}
              onChange={(e) => setLat(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="lon">Longitude</label>
            <input
              id="lon"
              type="number"
              step="any"
              value={lon}
              onChange={(e) => setLon(e.target.value)}
              required
            />
          </div>
        </div>
        {mapSrc ? (
          <div className="map-preview" aria-label="Map preview">
            <iframe title="Site map preview" src={mapSrc} loading="lazy" />
          </div>
        ) : null}
        <p className="hint">
          <a
            href={`https://www.google.com/maps?q=${lat},${lon}`}
            target="_blank"
            rel="noreferrer"
          >
            Open in Google Maps
          </a>
        </p>
        <div className="grid-2">
          <div className="field">
            <label htmlFor="area">Area (ha)</label>
            <input
              id="area"
              type="number"
              step="any"
              min="0.1"
              value={areaHa}
              onChange={(e) => setAreaHa(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="country">Country</label>
            <input
              id="country"
              value={country}
              onChange={(e) => setCountry(e.target.value)}
            />
          </div>
        </div>
        <div className="grid-2">
          <div className="field">
            <label htmlFor="land">Land use</label>
            <select
              id="land"
              value={landUse}
              onChange={(e) => setLandUse(e.target.value as LandUse)}
            >
              <option value="Standard">Standard Ground Mount</option>
              <option value="Agri-PV">Agri-PV (Dual Use)</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="mount">Mounting</label>
            <select
              id="mount"
              value={mountType}
              onChange={(e) => setMountType(e.target.value)}
            >
              <option value="Fixed Tilt">Fixed Tilt</option>
              <option value="Single-Axis Tracker">Single-Axis Tracker</option>
            </select>
          </div>
        </div>
        <button className="btn btn-primary" type="submit" disabled={loading}>
          {loading ? (
            <>
              <span className="spinner" />
              Running gate analysis…
            </>
          ) : (
            "Run gate analysis"
          )}
        </button>
      </form>
    </div>
  );
}
