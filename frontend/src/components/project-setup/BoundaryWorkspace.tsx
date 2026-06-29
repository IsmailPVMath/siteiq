import type * as GeoJSON from "geojson";
import { SiteMap, type OverlayParcel } from "../SiteMap";
import type { BoundaryPoint } from "../../types/gate";
import type { InputMethod, ProjectSetupDraft, SetupParcel } from "../../types/projectSetup";
import { INPUT_METHOD_OPTIONS } from "./InputMethodCards";

interface ParcelGroup {
  group: string;
  items: SetupParcel[];
  enabled: number;
  total: number;
  area: number;
}

interface Props {
  draft: ProjectSetupDraft;
  inputMethod: InputMethod;
  drawMode: "site" | "restriction";
  coordPaste: string;
  searchQ: string;
  searchResults: { lat: number; lon: number; label: string }[];
  parcelGroups: ParcelGroup[];
  collapsedGroups: Record<string, boolean>;
  overlayParcels: OverlayParcel[];
  buildableAreaGeoJson: GeoJSON.GeoJSON | null;
  busy: boolean;
  onDrawModeChange: (mode: "site" | "restriction") => void;
  onPick: (lat: number, lon: number) => void;
  onSiteBoundaryChange: (boundary?: BoundaryPoint[]) => void;
  onRestrictionsChange: (restrictions: BoundaryPoint[][]) => void;
  onFileUpload: (file: File) => void;
  onCoordPasteChange: (v: string) => void;
  onApplyPaste: () => void;
  onSearchChange: (v: string) => void;
  onSearch: () => void;
  onPickSearch: (r: { lat: number; lon: number; label: string }) => void;
  onLatLonChange: (lat: number, lon: number) => void;
  onToggleParcel: (id: string) => void;
  onToggleGroup: (group: string, enabled: boolean) => void;
  onToggleGroupCollapsed: (group: string) => void;
  onRemoveParcel: (id: string) => void;
  onRemoveGroup: (group: string) => void;
  onClearBoundary: () => void;
  onExpandAllGroups: () => void;
  onCollapseAllGroups: () => void;
  onRemoveOverlayParcels: (ids: string[]) => void;
  hasBoundary: boolean;
  hasUserLocation: boolean;
  boundaryAreaHa: number | null;
  grossAreaHa: number;
  locationLabel: string;
  onAreaChange: (gross_area_ha: number) => void;
}

export function BoundaryWorkspace({
  draft,
  inputMethod,
  drawMode,
  coordPaste,
  searchQ,
  searchResults,
  parcelGroups,
  collapsedGroups,
  overlayParcels,
  buildableAreaGeoJson,
  busy,
  onDrawModeChange,
  onPick,
  onSiteBoundaryChange,
  onRestrictionsChange,
  onFileUpload,
  onCoordPasteChange,
  onApplyPaste,
  onSearchChange,
  onSearch,
  onPickSearch,
  onLatLonChange,
  onToggleParcel,
  onToggleGroup,
  onToggleGroupCollapsed,
  onRemoveParcel,
  onRemoveGroup,
  onClearBoundary,
  onExpandAllGroups,
  onCollapseAllGroups,
  onRemoveOverlayParcels,
  hasBoundary,
  hasUserLocation,
  boundaryAreaHa,
  grossAreaHa,
  locationLabel,
  onAreaChange,
}: Props) {
  const uploadOpt = INPUT_METHOD_OPTIONS.find((o) => o.id === inputMethod);
  const isUpload = ["kml", "kmz", "geojson"].includes(inputMethod);
  const enabledCount = draft.geometry.parcels.filter((p) => p.enabled).length;

  return (
    <section className="setup-card setup-site-card">
      <h2>Site boundary</h2>

      {isUpload ? (
        <div className="input-method-panel">
          <div className="field kml-upload-field">
            <label htmlFor="boundary-file">Upload file</label>
            <input
              id="boundary-file"
              type="file"
              accept={uploadOpt?.accept}
              disabled={busy}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onFileUpload(f);
              }}
            />
          </div>
          {draft.geometry.parcels.length > 0 ? (
            <div className="parcel-manager">
              <div className="parcel-manager-head">
                <strong>
                  {enabledCount}/{draft.geometry.parcels.length} parcels selected
                </strong>
                <div className="parcel-manager-actions">
                  <button className="btn btn-ghost btn-sm" type="button" onClick={onExpandAllGroups}>
                    Expand all
                  </button>
                  <button className="btn btn-ghost btn-sm" type="button" onClick={onCollapseAllGroups}>
                    Collapse all
                  </button>
                  <button className="btn btn-ghost btn-sm" type="button" onClick={onClearBoundary}>
                    Clear
                  </button>
                </div>
              </div>
              <div className="parcel-groups">
                {parcelGroups.map((grp) => {
                  const collapsed = !!collapsedGroups[grp.group];
                  const allOn = grp.enabled === grp.total;
                  return (
                    <div
                      key={grp.group}
                      className={`parcel-group${grp.enabled === 0 ? " group-off" : ""}`}
                    >
                      <div className="parcel-group-head">
                        <input
                          type="checkbox"
                          checked={allOn}
                          ref={(el) => {
                            if (el) el.indeterminate = grp.enabled > 0 && !allOn;
                          }}
                          onChange={() => onToggleGroup(grp.group, !allOn)}
                        />
                        <button
                          type="button"
                          className="parcel-group-toggle"
                          onClick={() => onToggleGroupCollapsed(grp.group)}
                        >
                          <span className="parcel-caret">{collapsed ? "▸" : "▾"}</span>
                          <span className="parcel-group-name">{grp.group}</span>
                          <span className="parcel-group-meta">
                            {grp.enabled}/{grp.total} · {grp.area.toFixed(1)} ha
                          </span>
                        </button>
                        <button
                          type="button"
                          className="parcel-remove"
                          title={`Remove ${grp.group} layer`}
                          aria-label={`Remove ${grp.group} layer`}
                          onClick={() => onRemoveGroup(grp.group)}
                        >
                          ×
                        </button>
                      </div>
                      {!collapsed ? (
                        <ul className="parcel-list">
                          {grp.items.map((p) => (
                            <li key={p.id} className={p.enabled ? "parcel-on" : "parcel-off"}>
                              <label className="parcel-check">
                                <input
                                  type="checkbox"
                                  checked={p.enabled}
                                  onChange={() => onToggleParcel(p.id)}
                                />
                                <span className="parcel-name">{p.name}</span>
                                <span className="parcel-area">
                                  {p.area_ha > 0 ? `${p.area_ha} ha` : `${p.coords.length} pts`}
                                </span>
                              </label>
                              <button
                                type="button"
                                className="parcel-remove"
                                title={`Remove ${p.name}`}
                                aria-label={`Remove ${p.name}`}
                                onClick={() => onRemoveParcel(p.id)}
                              >
                                ×
                              </button>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {inputMethod === "paste" ? (
        <div className="input-method-panel">
          <div className="field">
            <label htmlFor="search">Search location</label>
            <div className="paste-row">
              <input
                id="search"
                value={searchQ}
                onChange={(e) => onSearchChange(e.target.value)}
                placeholder="City, address, or region"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    onSearch();
                  }
                }}
              />
              <button className="btn btn-ghost" type="button" onClick={onSearch}>
                Search
              </button>
            </div>
            {searchResults.length > 0 ? (
              <ul className="search-results">
                {searchResults.map((r) => (
                  <li key={`${r.lat}-${r.lon}-${r.label}`}>
                    <button type="button" onClick={() => onPickSearch(r)}>
                      {r.label}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          <div className="field">
            <label htmlFor="paste">Paste coordinates / Maps link</label>
            <div className="paste-row">
              <input
                id="paste"
                value={coordPaste}
                onChange={(e) => onCoordPasteChange(e.target.value)}
                placeholder="48.1351, 11.5820"
              />
              <button className="btn btn-ghost" type="button" onClick={onApplyPaste}>
                Apply
              </button>
            </div>
          </div>
          <div className="grid-2">
            <div className="field">
              <label htmlFor="lat">Latitude</label>
              <input
                id="lat"
                type="number"
                step="any"
                value={draft.location.lat}
                onChange={(e) => onLatLonChange(Number(e.target.value), draft.location.lon)}
              />
            </div>
            <div className="field">
              <label htmlFor="lon">Longitude</label>
              <input
                id="lon"
                type="number"
                step="any"
                value={draft.location.lon}
                onChange={(e) => onLatLonChange(draft.location.lat, Number(e.target.value))}
              />
            </div>
          </div>
        </div>
      ) : null}

      {inputMethod === "map" ? (
        <div className="input-method-panel">
          <div className="field">
            <label htmlFor="map-search">Search city or address</label>
            <div className="paste-row">
              <input
                id="map-search"
                value={searchQ}
                onChange={(e) => onSearchChange(e.target.value)}
                placeholder="e.g. Regensburg, Germany"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    onSearch();
                  }
                }}
              />
              <button className="btn btn-ghost" type="button" onClick={onSearch} disabled={busy}>
                Go
              </button>
            </div>
            {searchResults.length > 0 ? (
              <ul className="search-results">
                {searchResults.map((r) => (
                  <li key={`${r.lat}-${r.lon}-${r.label}`}>
                    <button type="button" onClick={() => onPickSearch(r)}>
                      {r.label}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          <div className="grid-2">
            <div className="field">
              <label htmlFor="map-lat">Latitude</label>
              <input
                id="map-lat"
                type="number"
                step="any"
                value={draft.location.lat}
                onChange={(e) => onLatLonChange(Number(e.target.value), draft.location.lon)}
              />
            </div>
            <div className="field">
              <label htmlFor="map-lon">Longitude</label>
              <input
                id="map-lon"
                type="number"
                step="any"
                value={draft.location.lon}
                onChange={(e) => onLatLonChange(draft.location.lat, Number(e.target.value))}
              />
            </div>
          </div>
          <div className="paste-row">
            <select
              value={drawMode}
              onChange={(e) => onDrawModeChange(e.target.value as "site" | "restriction")}
            >
              <option value="site">Draw site boundary</option>
              <option value="restriction">Draw restriction zone</option>
            </select>
            <button className="btn btn-ghost btn-sm" type="button" onClick={onClearBoundary}>
              Clear
            </button>
          </div>
          <p className="hint">Use the polygon tool on the map to trace the site.</p>
        </div>
      ) : null}

      {draft.geometry.parcels.length > 0 ? (
        <p className="hint map-draw-hint">
          Map tools (top-left): <strong>delete</strong> removes imported boundary/access layers —
          click a polygon, then confirm with ✓. <strong>Edit</strong> adjusts hand-drawn site or
          restriction zones.
        </p>
      ) : null}

      <SiteMap
        lat={draft.location.lat}
        lon={draft.location.lon}
        siteBoundary={draft.geometry.site_boundary}
        restrictions={draft.geometry.restrictions}
        overlayParcels={overlayParcels}
        buildableAreaGeoJson={buildableAreaGeoJson}
        drawMode={drawMode}
        onPick={onPick}
        onSiteBoundaryChange={onSiteBoundaryChange}
        onRestrictionsChange={onRestrictionsChange}
        onRemoveOverlayParcels={onRemoveOverlayParcels}
      />

      <div className="setup-area-panel">
        {locationLabel ? (
          <p className="setup-location-label">
            <span className="setup-location-label-kicker">Location</span>
            {locationLabel}
          </p>
        ) : null}

        {hasBoundary && boundaryAreaHa != null && boundaryAreaHa > 0 ? (
          <div className="setup-area-calculated">
            <span className="setup-area-calculated-label">Site area</span>
            <strong>{boundaryAreaHa.toFixed(2)} ha</strong>
            <span className="hint">Calculated from boundary</span>
          </div>
        ) : (
          <div className={`setup-area-pin${hasUserLocation ? "" : " is-disabled"}`}>
            <label htmlFor="pin-area">Assumed site area around pin (ha)</label>
            <input
              id="pin-area"
              type="number"
              step="any"
              min="0.1"
              value={grossAreaHa > 0 ? grossAreaHa : ""}
              placeholder={hasUserLocation ? "e.g. 25" : "Drop a pin or enter coordinates first"}
              disabled={!hasUserLocation}
              onChange={(e) => onAreaChange(Number(e.target.value))}
            />
            <p className="hint">
              {hasUserLocation
                ? "Used for SiteIQ screening when no boundary is drawn."
                : "Enable by placing a pin on the map, searching, or pasting coordinates."}
            </p>
          </div>
        )}

        {draft.geometry.buildable_area_ha != null ? (
          <p className="hint setup-buildable">
            Buildable: <strong>{draft.geometry.buildable_area_ha} ha</strong>
          </p>
        ) : null}
      </div>
    </section>
  );
}
