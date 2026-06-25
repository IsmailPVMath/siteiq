import { FormEvent, useState } from "react";
import { SiteMap } from "../components/SiteMap";
import { parseCoordinates } from "../lib/coords";
import { parseBoundaryFile, searchLocation } from "../lib/api";
import type { BoundaryPoint, GateAnalyzeRequest, LandUse } from "../types/gate";

export type ScreeningFormValues = GateAnalyzeRequest;

interface Props {
  token: string;
  initial?: Partial<ScreeningFormValues>;
  onSubmit: (body: ScreeningFormValues) => void;
}

const DEFAULTS: ScreeningFormValues = {
  project_name: "New project",
  lat: 48.1351,
  lon: 11.582,
  area_ha: 25,
  land_use: "Standard",
  mount_type: "Fixed Tilt",
  country: "Germany",
  run_layout: false,
};

export function InputPage({ token, initial, onSubmit }: Props) {
  const [projectName, setProjectName] = useState(
    initial?.project_name ?? DEFAULTS.project_name,
  );
  const [lat, setLat] = useState(initial?.lat ?? DEFAULTS.lat);
  const [lon, setLon] = useState(initial?.lon ?? DEFAULTS.lon);
  const [areaHa, setAreaHa] = useState(initial?.area_ha ?? DEFAULTS.area_ha);
  const [country, setCountry] = useState(initial?.country ?? DEFAULTS.country);
  const [landUse, setLandUse] = useState<LandUse>(initial?.land_use ?? DEFAULTS.land_use);
  const [mountType, setMountType] = useState(initial?.mount_type ?? DEFAULTS.mount_type);
  const [runLayout, setRunLayout] = useState(initial?.run_layout ?? false);
  const [boundary, setBoundary] = useState<BoundaryPoint[] | undefined>(
    initial?.boundary,
  );
  const [coordPaste, setCoordPaste] = useState("");
  const [searchQ, setSearchQ] = useState("");
  const [searchResults, setSearchResults] = useState<
    { lat: number; lon: number; label: string }[]
  >([]);
  const [hint, setHint] = useState("");
  const [busy, setBusy] = useState(false);

  function applyPick(newLat: number, newLon: number) {
    setLat(Number(newLat.toFixed(6)));
    setLon(Number(newLon.toFixed(6)));
  }

  function applyPaste() {
    const parsed = parseCoordinates(coordPaste);
    if (!parsed) {
      setHint("Could not read coordinates — paste lat, lon or a Google Maps link.");
      return;
    }
    applyPick(parsed.lat, parsed.lon);
    setHint("Location updated from paste.");
  }

  async function runSearch() {
    if (!searchQ.trim()) return;
    setBusy(true);
    setHint("");
    try {
      const { results } = await searchLocation(token, searchQ.trim());
      setSearchResults(results);
      if (!results.length) setHint("No results — try a city, region, or address.");
    } catch (err) {
      setHint(err instanceof Error ? err.message : "Search failed");
    } finally {
      setBusy(false);
    }
  }

  function pickSearchResult(r: { lat: number; lon: number; label: string }) {
    applyPick(r.lat, r.lon);
    if (!country && r.label) {
      const parts = r.label.split(",").map((s) => s.trim());
      if (parts.length) setCountry(parts[parts.length - 1]);
    }
    setSearchResults([]);
    setSearchQ(r.label);
    setHint("Location set from search.");
  }

  async function onKmlFile(file: File | null) {
    if (!file) return;
    setBusy(true);
    setHint("");
    try {
      const parsed = await parseBoundaryFile(token, file);
      applyPick(parsed.lat, parsed.lon);
      setBoundary(parsed.boundary);
      if (parsed.area_ha > 0) setAreaHa(parsed.area_ha);
      if (!projectName || projectName === DEFAULTS.project_name) {
        setProjectName(parsed.name);
      }
      setHint(
        `Loaded boundary: ${parsed.point_count} points, ${parsed.area_ha} ha (from KML/KMZ).`,
      );
    } catch (err) {
      setHint(err instanceof Error ? err.message : "KML upload failed");
    } finally {
      setBusy(false);
    }
  }

  function clearBoundary() {
    setBoundary(undefined);
    setHint("Boundary cleared — using pin location only.");
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onSubmit({
      project_name: projectName.trim() || "Site screening",
      lat,
      lon,
      area_ha: Number(areaHa),
      land_use: landUse,
      mount_type: mountType,
      country: country.trim(),
      boundary: boundary && boundary.length >= 3 ? boundary : undefined,
      run_layout: runLayout,
    });
  }

  return (
    <div className="workflow-page">
      <div className="page-intro">
        <h1>Project input</h1>
        <p>
          Search, click the map, paste coordinates, or upload KML — then run unified site
          screening (SiteIQ engines via API).
        </p>
      </div>

      <form className="card card-wide" onSubmit={handleSubmit}>
        <section className="form-section">
          <h2>Project</h2>
          <div className="field">
            <label htmlFor="project">Project name</label>
            <input
              id="project"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
            />
          </div>
        </section>

        <section className="form-section">
          <h2>Site location</h2>
          <div className="field">
            <label htmlFor="search">Search location</label>
            <div className="paste-row">
              <input
                id="search"
                value={searchQ}
                onChange={(e) => setSearchQ(e.target.value)}
                placeholder="Munich, Germany or project address"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void runSearch();
                  }
                }}
              />
              <button className="btn btn-ghost" type="button" onClick={() => void runSearch()}>
                Search
              </button>
            </div>
            {searchResults.length > 0 ? (
              <ul className="search-results">
                {searchResults.map((r) => (
                  <li key={`${r.lat}-${r.lon}-${r.label}`}>
                    <button type="button" onClick={() => pickSearchResult(r)}>
                      {r.label}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>

          <div className="field">
            <label htmlFor="paste">Or paste coordinates / Google Maps link</label>
            <div className="paste-row">
              <input
                id="paste"
                value={coordPaste}
                onChange={(e) => setCoordPaste(e.target.value)}
                placeholder="48.1351, 11.5820"
              />
              <button className="btn btn-ghost" type="button" onClick={applyPaste}>
                Apply
              </button>
            </div>
          </div>

          <SiteMap lat={lat} lon={lon} boundary={boundary} onPick={applyPick} />
          <p className="hint">Click map or drag pin to set site centre.</p>

          <div className="grid-2">
            <div className="field">
              <label htmlFor="lat">Latitude</label>
              <input
                id="lat"
                type="number"
                step="any"
                value={lat}
                onChange={(e) => setLat(Number(e.target.value))}
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
                onChange={(e) => setLon(Number(e.target.value))}
                required
              />
            </div>
          </div>

          <div className="field">
            <label htmlFor="kml">Upload KML / KMZ boundary</label>
            <input
              id="kml"
              type="file"
              accept=".kml,.kmz"
              onChange={(e) => void onKmlFile(e.target.files?.[0] ?? null)}
            />
            {boundary && boundary.length >= 3 ? (
              <button className="btn btn-ghost btn-sm" type="button" onClick={clearBoundary}>
                Clear boundary
              </button>
            ) : null}
          </div>
        </section>

        <section className="form-section">
          <h2>Site parameters</h2>
          <div className="grid-3">
            <div className="field">
              <label htmlFor="area">Gross area (ha)</label>
              <input
                id="area"
                type="number"
                step="any"
                min="0.1"
                value={areaHa}
                onChange={(e) => setAreaHa(Number(e.target.value))}
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
          </div>
          <div className="grid-2">
            <div className="field">
              <label htmlFor="mount">Mounting system</label>
              <select
                id="mount"
                value={mountType}
                onChange={(e) => setMountType(e.target.value)}
              >
                <option value="Fixed Tilt">Fixed Tilt</option>
                <option value="Single-Axis Tracker">Single-Axis Tracker</option>
              </select>
            </div>
            <div className="field checkbox-field">
              <label>
                <input
                  type="checkbox"
                  checked={runLayout}
                  onChange={(e) => setRunLayout(e.target.checked)}
                />
                Include layout + BOM (slower; needs boundary polygon)
              </label>
            </div>
          </div>
        </section>

        {hint ? <p className="hint hint-banner">{hint}</p> : null}

        <div className="form-actions">
          <button className="btn btn-primary btn-lg" type="submit" disabled={busy}>
            Continue to screening →
          </button>
        </div>
      </form>
    </div>
  );
}
