import { useEffect, useMemo, useRef, useState } from "react";
import {
  analyzeTopo,
  analyzeYield,
  topoExportsZip,
  topoReportPdf,
  workflowGisAnalysis,
  workflowLayoutDetail,
  workflowLayoutDxf,
  workflowLayoutSweep,
  workflowProjectPackage,
  workflowPvmathReportPdf,
  workflowScore,
  workflowTerrainMesh,
} from "../lib/api";
import { ConstraintAnalysisMap } from "../components/ConstraintAnalysisMap";
import { LayoutPreviewMap } from "../components/LayoutPreviewMap";
import { Terrain3DView } from "../components/Terrain3DView";
import type { GateAnalyzeRequest } from "../types/gate";
import {
  DEFAULT_LAYOUT_CONFIG,
  ROAD_PRESETS,
  layoutPayloadFrom,
  type RoadMode,
} from "../types/layoutConfig";
import type { TopoIQAnalyzeRequest, TopoIQAnalyzeResponse, YieldIQAnalyzeResponse } from "../types/topoiq";
import type {
  LayoutOptimizationMode,
  LayoutLandCost,
  LayoutSweepRow,
  OutputModuleStage,
  WorkflowGisAnalysisResponse,
  WorkflowLayoutDetailResponse,
  WorkflowLayoutSweepResponse,
  WorkflowScoreResponse,
  WorkflowScreenResponse,
  WorkflowTerrainMeshResponse,
} from "../types/workflow";
import type * as GeoJSON from "geojson";

interface Props {
  token: string;
  result: WorkflowScreenResponse;
  input?: GateAnalyzeRequest;
  activeModule: OutputModuleStage;
  onModuleChange: (stage: OutputModuleStage) => void;
  onNewScreening: () => void;
  onEditInput: () => void;
}

function metric(label: string, rating?: string, detail?: string, extra?: string) {
  return (
    <div className="metric">
      <div className="label">{label}</div>
      <div className="value">{rating || "—"}</div>
      {detail ? <div className="sub">{detail}</div> : null}
      {extra ? <div className="sub">{extra}</div> : null}
    </div>
  );
}

function formatLayoutMwp(row: LayoutSweepRow) {
  if (row.dc_mwp != null) return row.dc_mwp.toFixed(1);
  if (row.dc_kwp != null) return (row.dc_kwp / 1000).toFixed(1);
  return "—";
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

type LatLonRing = { lat: number; lon: number }[];

function scoreLandFromBuildablePct(pct?: number | null) {
  if (pct == null || !Number.isFinite(pct)) return undefined;
  if (pct >= 80) return 95;
  if (pct >= 65) return 85;
  if (pct >= 50) return 72;
  if (pct >= 35) return 58;
  if (pct >= 20) return 42;
  return 25;
}

function ringFromLonLat(coords: GeoJSON.Position[]): LatLonRing | null {
  const ring = coords
    .map((p) => ({ lon: Number(p[0]), lat: Number(p[1]) }))
    .filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lon));
  if (ring.length < 3) return null;
  return ring;
}

function geoJsonToLatLonRings(geo?: GeoJSON.GeoJSON | null): LatLonRing[] {
  if (!geo) return [];
  if (geo.type === "Feature") {
    return geoJsonToLatLonRings(geo.geometry);
  }
  if (geo.type === "FeatureCollection") {
    return geo.features.flatMap((feature) => geoJsonToLatLonRings(feature));
  }
  if (geo.type === "GeometryCollection") {
    return geo.geometries.flatMap((geometry) => geoJsonToLatLonRings(geometry));
  }
  if (geo.type === "Polygon") {
    return geo.coordinates
      .map((ring) => ringFromLonLat(ring))
      .filter((ring): ring is LatLonRing => !!ring);
  }
  if (geo.type === "MultiPolygon") {
    return geo.coordinates.flatMap((poly) =>
      poly
        .map((ring) => ringFromLonLat(ring))
        .filter((ring): ring is LatLonRing => !!ring),
    );
  }
  return [];
}

function ringsToFeatureCollection(rings: LatLonRing[]): GeoJSON.FeatureCollection | null {
  const features = rings
    .filter((ring) => ring.length >= 3)
    .map((ring, i) => {
      const closed = ring[0] === ring[ring.length - 1] ? ring : [...ring, ring[0]];
      return {
        type: "Feature" as const,
        properties: { id: `manual_${i}` },
        geometry: {
          type: "Polygon" as const,
          coordinates: [closed.map((p) => [p.lon, p.lat])],
        },
      };
    });
  return features.length ? { type: "FeatureCollection", features } : null;
}

function isTopoGridTooLarge(message: string) {
  const m = message.toLowerCase();
  return m.includes("too large") || m.includes("allow_coarsen") || m.includes("grid_m");
}

export function OutputPage({
  token,
  result,
  input,
  activeModule,
  onModuleChange,
  onNewScreening,
  onEditInput,
}: Props) {
  const activeStage = activeModule;
  const setActiveStage = onModuleChange;
  const [topoBusy, setTopoBusy] = useState(false);
  const [topoError, setTopoError] = useState("");
  const [topoResult, setTopoResult] = useState<TopoIQAnalyzeResponse | null>(null);
  const [topoGridM, setTopoGridM] = useState(5);
  const [topoAllowCoarsen, setTopoAllowCoarsen] = useState(true);
  const topoAutoRan = useRef(false);
  const [topoPdfBusy, setTopoPdfBusy] = useState(false);
  const [topoZipBusy, setTopoZipBusy] = useState(false);
  const [yieldBusy, setYieldBusy] = useState(false);
  const [yieldError, setYieldError] = useState("");
  const [yieldResult, setYieldResult] = useState<YieldIQAnalyzeResponse | null>(null);
  const [finalScore, setFinalScore] = useState<WorkflowScoreResponse | null>(null);
  const [layoutBusy, setLayoutBusy] = useState(false);
  const [layoutError, setLayoutError] = useState("");
  const [layoutSweep, setLayoutSweep] = useState<WorkflowLayoutSweepResponse | null>(null);
  const [layoutFilter, setLayoutFilter] = useState<string>("all");
  const [selectedLayoutRow, setSelectedLayoutRow] = useState<LayoutSweepRow | null>(null);
  const [layoutDetailBusy, setLayoutDetailBusy] = useState(false);
  const [layoutDxfBusy, setLayoutDxfBusy] = useState(false);
  const [layoutDetail, setLayoutDetail] = useState<WorkflowLayoutDetailResponse | null>(null);
  const [terrain3DBusy, setTerrain3DBusy] = useState(false);
  const [terrain3D, setTerrain3D] = useState<WorkflowTerrainMeshResponse | null>(null);
  const [layoutOptimization, setLayoutOptimization] = useState<LayoutOptimizationMode>("balanced");
  const [layoutLandCost, setLayoutLandCost] = useState<LayoutLandCost>("auto");
  const [layoutBifacial, setLayoutBifacial] = useState(false);
  const [layoutCustomGcr, setLayoutCustomGcr] = useState("");
  const [layoutCustomPitch, setLayoutCustomPitch] = useState("");
  const [moduleH, setModuleH] = useState(input?.module_h ?? DEFAULT_LAYOUT_CONFIG.module_h);
  const [moduleW, setModuleW] = useState(input?.module_w ?? DEFAULT_LAYOUT_CONFIG.module_w);
  const [moduleWp, setModuleWp] = useState(input?.module_wp ?? DEFAULT_LAYOUT_CONFIG.module_wp);
  const [modulesPerString, setModulesPerString] = useState(
    input?.modules_per_string ?? DEFAULT_LAYOUT_CONFIG.modules_per_string,
  );
  const [interStringGap, setInterStringGap] = useState(
    input?.inter_string_gap_m ?? DEFAULT_LAYOUT_CONFIG.inter_string_gap_m,
  );
  const [trackerStringOptions, setTrackerStringOptions] = useState(
    (input?.tracker_string_options ?? DEFAULT_LAYOUT_CONFIG.tracker_string_options).join(","),
  );
  const [maxTrackerLength, setMaxTrackerLength] = useState(
    input?.max_tracker_length_m ?? DEFAULT_LAYOUT_CONFIG.max_tracker_length_m,
  );
  const [excludeTrackerSlope, setExcludeTrackerSlope] = useState(
    input?.exclude_tracker_slope ?? DEFAULT_LAYOUT_CONFIG.exclude_tracker_slope,
  );
  const [trackerSlopeLimit, setTrackerSlopeLimit] = useState(
    input?.tracker_slope_limit_pct ?? DEFAULT_LAYOUT_CONFIG.tracker_slope_limit_pct,
  );
  const [roadMode, setRoadMode] = useState<RoadMode>(
    input?.road_mode ?? DEFAULT_LAYOUT_CONFIG.road_mode,
  );
  const [roadPreset, setRoadPreset] = useState(
    input?.road_preset ?? DEFAULT_LAYOUT_CONFIG.road_preset,
  );
  const [rowsPerBlock, setRowsPerBlock] = useState(
    input?.rows_per_block ?? DEFAULT_LAYOUT_CONFIG.rows_per_block,
  );
  const [blockGapM, setBlockGapM] = useState(
    input?.block_gap_m ?? DEFAULT_LAYOUT_CONFIG.block_gap_m,
  );
  const [reportBusy, setReportBusy] = useState(false);
  const [packageBusy, setPackageBusy] = useState(false);
  const [exportError, setExportError] = useState("");
  const [gisBusy, setGisBusy] = useState(false);
  const [gisError, setGisError] = useState("");
  const [gisResult, setGisResult] = useState<WorkflowGisAnalysisResponse | null>(null);

  const grid = result.grid as Record<string, unknown>;
  const nearest = grid?.nearest as Record<string, unknown> | undefined;
  const boundaries = useMemo<{ lat: number; lon: number }[][]>(() => {
    const rings = (input?.boundaries || []).filter((r) => r && r.length >= 3);
    if (rings.length) return rings;
    if (input?.boundary && input.boundary.length >= 3) return [input.boundary];
    return [];
  }, [input?.boundaries, input?.boundary]);
  const restrictionPolygons = useMemo<{ lat: number; lon: number }[][]>(
    () => (input?.restriction_polygons || []).filter((r) => r && r.length >= 3),
    [input?.restriction_polygons],
  );
  const hasBoundary = boundaries.length > 0;
  const gisExcludedRings = useMemo(
    () => geoJsonToLatLonRings(gisResult?.excluded_area_geojson ?? null),
    [gisResult?.excluded_area_geojson],
  );
  const layoutRestrictionPolygons = useMemo(
    () => (gisResult?.success && gisExcludedRings.length ? gisExcludedRings : restrictionPolygons),
    [gisExcludedRings, gisResult?.success, restrictionPolygons],
  );
  const layoutUsesGisBuildable = !!(gisResult?.success && gisExcludedRings.length);
  const landScoreFromGis = scoreLandFromBuildablePct(gisResult?.buildable_pct);
  const scoreComponents = useMemo(() => {
    if (landScoreFromGis == null) return result.score_components;
    return { ...result.score_components, land: landScoreFromGis };
  }, [landScoreFromGis, result.score_components]);

  function parseTrackerStringOptions() {
    const parsed = trackerStringOptions
      .split(/[,\s]+/)
      .map((v) => Number(v.trim()))
      .filter((v) => Number.isFinite(v) && v > 0);
    return parsed.length ? parsed : DEFAULT_LAYOUT_CONFIG.tracker_string_options;
  }

  function layoutApiParams() {
    const base = layoutPayloadFrom({
      module_h: moduleH,
      module_w: moduleW,
      module_wp: moduleWp,
      modules_per_string: modulesPerString,
      inter_string_gap_m: interStringGap,
      tracker_string_options: parseTrackerStringOptions(),
      max_tracker_length_m: maxTrackerLength,
      road_mode: roadMode,
      road_preset: roadPreset,
      rows_per_block: rowsPerBlock,
      block_gap_m: blockGapM,
      exclude_tracker_slope: excludeTrackerSlope,
      tracker_slope_limit_pct: trackerSlopeLimit,
    });
    if (roadPreset === "custom") {
      return {
        ...base,
        road_mode: "manual" as RoadMode,
        road_preset: "custom",
        rows_per_block: rowsPerBlock,
        block_gap_m: blockGapM,
      };
    }
    return base;
  }

  const topoPayload: TopoIQAnalyzeRequest | null = useMemo(() => {
    if (!hasBoundary) return null;
    return {
      project_name: input?.project_name || result.project_name || "TopoIQ run",
      country: input?.country || "",
      land_use: input?.land_use || "Standard",
      polygons: boundaries.map((ring) => ring.map((p) => ({ lat: p.lat, lon: p.lon }))),
      grid_m: topoGridM,
      allow_coarsen: topoAllowCoarsen,
      contour_minor: 0.5,
      contour_major: 1.0,
    };
  }, [boundaries, hasBoundary, input, result.project_name, topoAllowCoarsen, topoGridM]);

  useEffect(() => {
    if (!hasBoundary) return;
    let cancelled = false;
    async function runGis() {
      setGisBusy(true);
      setGisError("");
      try {
        const data = await workflowGisAnalysis(token, {
          boundaries,
          restriction_polygons_geojson: ringsToFeatureCollection(restrictionPolygons),
          include_grid: false,
        });
        if (!cancelled) setGisResult(data);
      } catch (err) {
        if (!cancelled) {
          setGisError(err instanceof Error ? err.message : "GIS analysis failed");
          setGisResult(null);
        }
      } finally {
        if (!cancelled) setGisBusy(false);
      }
    }
    void runGis();
    return () => {
      cancelled = true;
    };
  }, [token, boundaries, hasBoundary, restrictionPolygons]);

  const selectedYieldConfigKey = useMemo(() => {
    if (!selectedLayoutRow) return null;
    const tracker = selectedLayoutRow.mount_type === "Single-Axis Tracker";
    const portraitGroup = selectedLayoutRow.n_portrait === 1 ? "1P" : "2P";
    return `${portraitGroup} ${tracker ? "Tracker" : "Fixed"}`;
  }, [selectedLayoutRow]);

  const yieldPayload = useMemo(() => {
    const selectedGcr = selectedLayoutRow?.gcr;
    const selectedIs1P = selectedLayoutRow?.n_portrait === 1;
    return {
      lat: result.coordinates.lat,
      lon: result.coordinates.lon,
      mount_type: selectedLayoutRow?.mount_type || input?.mount_type || "Fixed Tilt",
      gcr_1p: selectedIs1P && selectedGcr ? selectedGcr : 0.35,
      gcr_2p: !selectedIs1P && selectedGcr ? selectedGcr : 0.42,
      soiling_loss: 2.0,
      other_loss: 6.0,
    };
  }, [input?.mount_type, result.coordinates.lat, result.coordinates.lon, selectedLayoutRow]);

  const selectedYieldConfig = selectedYieldConfigKey
    ? yieldResult?.configs[selectedYieldConfigKey]
    : null;
  const selectedAnnualMwh =
    selectedLayoutRow?.dc_kwp && selectedYieldConfig?.spec_y
      ? (selectedLayoutRow.dc_kwp * selectedYieldConfig.spec_y) / 1000
      : null;

  async function refreshFinalScore(topo: TopoIQAnalyzeResponse) {
    const terrainScore = topo.terrain_drivers.terrain_score as number | undefined;
    if (terrainScore == null) return;
    try {
      const scored = await workflowScore(token, {
        score_components: scoreComponents,
        terrain_score: terrainScore,
      });
      setFinalScore(scored);
    } catch {
      setFinalScore(null);
    }
  }

  useEffect(() => {
    if (topoResult) {
      void refreshFinalScore(topoResult);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scoreComponents, topoResult]);

  async function handleRunTopo(overrides?: Partial<TopoIQAnalyzeRequest>) {
    const payload = topoPayload ? { ...topoPayload, ...overrides } : null;
    if (!payload) return;
    setTopoBusy(true);
    setTopoError("");
    try {
      const topo = await analyzeTopo(token, payload);
      setTopoResult(topo);
      if (overrides?.grid_m != null) setTopoGridM(overrides.grid_m);
      if (overrides?.allow_coarsen != null) setTopoAllowCoarsen(overrides.allow_coarsen);
      await refreshFinalScore(topo);
    } catch (err) {
      setTopoError(err instanceof Error ? err.message : "TopoIQ analysis failed");
    } finally {
      setTopoBusy(false);
    }
  }

  function runTopoAdaptiveGrid() {
    setTopoAllowCoarsen(true);
    setTopoGridM(5);
    void handleRunTopo({ allow_coarsen: true, grid_m: 5 });
  }

  function runTopoFixedGrid(gridM: number) {
    setTopoAllowCoarsen(false);
    setTopoGridM(gridM);
    void handleRunTopo({ allow_coarsen: false, grid_m: gridM });
  }

  useEffect(() => {
    if (activeStage !== "topo") {
      topoAutoRan.current = false;
      return;
    }
    if (topoAutoRan.current || !topoPayload || topoResult || topoBusy) return;
    topoAutoRan.current = true;
    void handleRunTopo();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeStage, topoPayload, topoResult, topoBusy]);

  function proceedToTopo() {
    setActiveStage("topo");
  }

  function proceedToLayout() {
    setActiveStage("layout");
  }

  function proceedToYield() {
    setActiveStage("yield");
  }

  async function handleTopoPdf() {
    if (!topoPayload) return;
    setTopoPdfBusy(true);
    setTopoError("");
    try {
      const blob = await topoReportPdf(token, topoPayload);
      const safe = (topoPayload.project_name || "topoiq").replace(/\s+/g, "_");
      saveBlob(blob, `${safe}_terrain_report.pdf`);
    } catch (err) {
      setTopoError(err instanceof Error ? err.message : "Terrain PDF failed");
    } finally {
      setTopoPdfBusy(false);
    }
  }

  async function handleTopoZip() {
    if (!topoPayload) return;
    setTopoZipBusy(true);
    setTopoError("");
    try {
      const blob = await topoExportsZip(token, topoPayload);
      const safe = (topoPayload.project_name || "topoiq").replace(/\s+/g, "_");
      saveBlob(blob, `${safe}_topoiq_exports.zip`);
    } catch (err) {
      setTopoError(err instanceof Error ? err.message : "CAD ZIP failed");
    } finally {
      setTopoZipBusy(false);
    }
  }

  async function handleRunYield() {
    setActiveStage("yield");
    setYieldBusy(true);
    setYieldError("");
    try {
      setYieldResult(await analyzeYield(token, yieldPayload));
    } catch (err) {
      setYieldError(err instanceof Error ? err.message : "YieldIQ analysis failed");
    } finally {
      setYieldBusy(false);
    }
  }

  async function handleLayoutSweep() {
    if (!hasBoundary) return;
    setActiveStage("layout");
    setLayoutBusy(true);
    setLayoutError("");
    try {
      const body: Parameters<typeof workflowLayoutSweep>[1] = {
        boundaries,
        restriction_polygons: layoutRestrictionPolygons,
        include_bom: false,
        optimization_mode: layoutOptimization,
        land_cost: layoutLandCost,
        country: input?.country || "",
        lat: result.coordinates.lat,
        bifacial: layoutBifacial,
        ...layoutApiParams(),
      };
      if (layoutOptimization === "custom") {
        const gcr = Number(layoutCustomGcr);
        const pitch = Number(layoutCustomPitch);
        if (gcr > 0) body.custom_gcr = gcr;
        if (pitch > 0) body.custom_pitch_m = pitch;
      }
      const res = await workflowLayoutSweep(token, body);
      setLayoutSweep(res);
      setLayoutFilter("all");
      setSelectedLayoutRow(null);
      setLayoutDetail(null);
      setTerrain3D(null);
      setYieldResult(null);
    } catch (err) {
      setLayoutError(err instanceof Error ? err.message : "Layout sweep failed");
    } finally {
      setLayoutBusy(false);
    }
  }

  function selectedLayoutPayload(row = selectedLayoutRow) {
    if (!hasBoundary || !row) return null;
    return {
      project_name: result.project_name || "LayoutIQ",
      boundaries,
      restriction_polygons: layoutRestrictionPolygons,
      config_key: row.config_key,
      pitch_m: row.pitch_m,
      ...layoutApiParams(),
    };
  }

  async function handleLayoutDetail(row = selectedLayoutRow) {
    const payload = selectedLayoutPayload(row);
    if (!payload) return;
    setLayoutDetailBusy(true);
    setLayoutError("");
    try {
      setLayoutDetail(await workflowLayoutDetail(token, payload));
    } catch (err) {
      setLayoutError(err instanceof Error ? err.message : "Layout preview failed");
    } finally {
      setLayoutDetailBusy(false);
    }
  }

  async function handleLayoutDxf() {
    const payload = selectedLayoutPayload();
    if (!payload) return;
    setLayoutDxfBusy(true);
    setLayoutError("");
    try {
      const blob = await workflowLayoutDxf(token, payload);
      const safe = (payload.project_name || "LayoutIQ").replace(/\s+/g, "_");
      saveBlob(blob, `${safe}_${payload.config_key}_${payload.pitch_m}m_layout.dxf`);
    } catch (err) {
      setLayoutError(err instanceof Error ? err.message : "Layout DXF failed");
    } finally {
      setLayoutDxfBusy(false);
    }
  }

  async function handleTerrain3D() {
    if (!hasBoundary) return;
    setTerrain3DBusy(true);
    setLayoutError("");
    try {
      setTerrain3D(await workflowTerrainMesh(token, { boundaries, grid_m: 20, max_vertices: 12000 }));
    } catch (err) {
      setLayoutError(err instanceof Error ? err.message : "3D terrain failed");
    } finally {
      setTerrain3DBusy(false);
    }
  }

  function reportPayload() {
    return {
      project_name: result.project_name || input?.project_name || "Project",
      country: input?.country || "",
      lat: result.coordinates.lat,
      lon: result.coordinates.lon,
      land_use: input?.land_use || "Standard",
      screening: result as unknown as Record<string, unknown>,
      topo: topoResult as unknown as Record<string, unknown> | null,
      score: finalScore as unknown as Record<string, unknown> | null,
      layout_row: selectedLayoutRow,
      yield_result: yieldResult as unknown as Record<string, unknown> | null,
      selected_yield_mwh: selectedAnnualMwh,
    };
  }

  async function handlePvmathReport() {
    setReportBusy(true);
    setExportError("");
    try {
      const blob = await workflowPvmathReportPdf(token, reportPayload());
      const safe = (result.project_name || "PVMath").replace(/\s+/g, "_");
      saveBlob(blob, `${safe}_PVMath_Report.pdf`);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "PVMath report failed");
    } finally {
      setReportBusy(false);
    }
  }

  async function handleProjectPackage() {
    if (!selectedLayoutRow || !hasBoundary) return;
    setPackageBusy(true);
    setExportError("");
    try {
      const blob = await workflowProjectPackage(token, {
        ...reportPayload(),
        boundaries,
        restriction_polygons: layoutRestrictionPolygons,
        config_key: selectedLayoutRow.config_key,
        pitch_m: selectedLayoutRow.pitch_m,
        ...layoutApiParams(),
      });
      const safe = (result.project_name || "PVMath").replace(/\s+/g, "_");
      saveBlob(blob, `${safe}_Project_Package.zip`);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Project package failed");
    } finally {
      setPackageBusy(false);
    }
  }

  const layoutRows: LayoutSweepRow[] = useMemo(() => {
    if (!layoutSweep?.rows) return [];
    if (layoutFilter === "all") return layoutSweep.rows.filter((r) => r.success);
    return layoutSweep.rows.filter((r) => r.success && r.config_key === layoutFilter);
  }, [layoutFilter, layoutSweep]);

  const layoutConfigKeys = useMemo(() => {
    if (!layoutSweep?.best_by_config) return [];
    return Object.keys(layoutSweep.best_by_config).sort();
  }, [layoutSweep]);

  const overallScore = finalScore?.pvmath_score;
  const overallReady = overallScore != null;
  const topoGridTooLarge = topoError ? isTopoGridTooLarge(topoError) : false;

  function renderTopoRecovery(compact = false) {
    if (!topoGridTooLarge) return null;
    return (
      <div className={`topo-recovery${compact ? " topo-recovery-compact" : ""}`}>
        <p className="hint">
          This site is large for a fine terrain grid. Pick an option — you are not blocked:
        </p>
        <div className="topo-recovery-actions">
          <button
            className="btn btn-primary"
            type="button"
            onClick={runTopoAdaptiveGrid}
            disabled={topoBusy}
          >
            {topoBusy ? "Running…" : "Use adaptive grid (recommended)"}
          </button>
          <button
            className="btn btn-ghost"
            type="button"
            onClick={() => runTopoFixedGrid(10)}
            disabled={topoBusy}
          >
            10 m grid — more detail, slower
          </button>
          <button
            className="btn btn-ghost"
            type="button"
            onClick={() => runTopoFixedGrid(15)}
            disabled={topoBusy}
          >
            15 m grid — faster screening
          </button>
        </div>
        <p className="hint topo-recovery-note">
          Adaptive spacing uses the same DEM tiles but fewer sample points on very large boundaries —
          best default for preliminary studies. Fixed 10 m keeps uniform spacing and takes longer.
        </p>
      </div>
    );
  }

  function renderTerrainDrivers(topo: TopoIQAnalyzeResponse) {
    const td = topo.terrain_drivers;
    if (!td || typeof td.terrain_score !== "number") return null;
    const drivers = Array.isArray(td.drivers) ? td.drivers : [];
    const why = Array.isArray(td.why_bullets) ? td.why_bullets : [];
    const ex = (topo.extras ?? {}) as Record<string, unknown>;
    const crMean = typeof ex.cross_row_mean === "number" ? ex.cross_row_mean : null;
    const crP95 = typeof ex.cross_row_p95 === "number" ? ex.cross_row_p95 : null;
    const kindIcon = (k: string) =>
      k === "positive" ? "✓" : k === "warn" ? "⚠" : "•";
    return (
      <div className="terrain-drivers">
        <div className="terrain-drivers-head">
          <span className="terrain-drivers-tag">Terrain drivers</span>
          <span className="terrain-score">
            Terrain Score: <strong>{td.terrain_score}/100</strong>{" "}
            {td.terrain_score_label ? <em>({td.terrain_score_label})</em> : null}
          </span>
        </div>
        {drivers.length > 0 ? (
          <table className="terrain-drivers-table">
            <thead>
              <tr>
                <th>Driver</th>
                <th>Impact</th>
              </tr>
            </thead>
            <tbody>
              {drivers.map(([driver, impact, kind], i) => (
                <tr key={i}>
                  <td>{driver}</td>
                  <td className={`td-impact td-${kind}`}>
                    {kindIcon(kind)} {impact}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
        {why.length > 0 ? (
          <div className="terrain-why">
            <span className="terrain-why-title">Why this verdict?</span>
            <ul>
              {why.map(([kind, text], i) => (
                <li key={i} className={`td-${kind}`}>
                  {kindIcon(kind)} {text}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {crMean !== null || crP95 !== null ? (
          <p className="module-note terrain-crossrow">
            <strong>Cross-row slope (tracker screening):</strong>{" "}
            {crMean !== null ? `mean ${crMean.toFixed(1)}%` : ""}
            {crMean !== null && crP95 !== null ? " · " : ""}
            {crP95 !== null ? `95th pctile ${crP95.toFixed(1)}%` : ""}
          </p>
        ) : null}
      </div>
    );
  }

  function renderSlopeMap() {
    const slopeMapUrl = topoResult?.slope_map_png_data_url;
    if (!slopeMapUrl) return null;
    return (
      <div className="slope-map">
        <div className="slope-map-head">
          <span className="terrain-drivers-tag">Slope map · top view</span>
          <span className="slope-map-legend">green &lt;3% · red &gt;10%</span>
        </div>
        <div className="slope-map-canvas">
          <img src={slopeMapUrl} alt="Slope map: top view with satellite basemap and north arrow" />
        </div>
      </div>
    );
  }

  return (
    <div
      className={`workflow-page results-shell${
        activeStage === "screen" ? " results-shell-full" : ""
      }`}
    >
      {activeStage !== "screen" ? (
      <aside className="results-sidebar">
        <div className="sidebar-project">
          <h1>{result.project_name}</h1>
          <div className="coord-pill">
            {result.coordinates.lat.toFixed(4)}°, {result.coordinates.lon.toFixed(4)}°
          </div>
        </div>

        {activeStage === "topo" ? (
        <div className="sidebar-group">
          <h3>TopoIQ terrain</h3>
          {!hasBoundary ? (
            <p className="hint sidebar-hint">
              Add a site boundary on Project input to enable terrain analysis.
            </p>
          ) : (
            <>
              <button
                className="btn btn-primary btn-block"
                type="button"
                onClick={() => void handleRunTopo()}
                disabled={topoBusy}
              >
                {topoBusy ? "Running TopoIQ…" : topoResult ? "Re-run TopoIQ" : "Run TopoIQ"}
              </button>
              <div className="sidebar-btn-row">
                <button
                  className="btn btn-ghost btn-sm"
                  type="button"
                  onClick={() => void handleTopoPdf()}
                  disabled={topoPdfBusy || !topoResult}
                >
                  {topoPdfBusy ? "Generating…" : "Terrain PDF"}
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  type="button"
                  onClick={() => void handleTopoZip()}
                  disabled={topoZipBusy || !topoResult}
                >
                  {topoZipBusy ? "Preparing…" : "CAD ZIP"}
                </button>
              </div>
            </>
          )}
          {renderTopoRecovery(true)}
        </div>
        ) : null}

        {activeStage === "layout" ? (
        <div className="sidebar-group">
          <h3>LayoutIQ strategy</h3>
          {!hasBoundary ? (
            <p className="hint sidebar-hint">Boundary required for layout generation.</p>
          ) : (
            <>
              <div className="field">
                <label htmlFor="layout-opt-mode">Optimization mode</label>
                <select
                  id="layout-opt-mode"
                  value={layoutOptimization}
                  onChange={(e) => setLayoutOptimization(e.target.value as LayoutOptimizationMode)}
                >
                  <option value="balanced">Balanced (industry default)</option>
                  <option value="high_energy">High energy — wider spacing</option>
                  <option value="land_optimized">Land optimized — tighter</option>
                  <option value="custom">Custom GCR or pitch</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="layout-land-cost">Land cost</label>
                <select
                  id="layout-land-cost"
                  value={layoutLandCost}
                  onChange={(e) => setLayoutLandCost(e.target.value as LayoutLandCost)}
                >
                  <option value="auto">Auto (from country)</option>
                  <option value="cheap">Cheap (TX, AU, SA, IN…)</option>
                  <option value="balanced">Moderate</option>
                  <option value="expensive">Expensive (DE, NL, JP, KR…)</option>
                </select>
              </div>
              <label className="checkbox-field layout-bifacial">
                <input
                  type="checkbox"
                  checked={layoutBifacial}
                  onChange={(e) => setLayoutBifacial(e.target.checked)}
                />
                Bifacial (wider spacing bias)
              </label>
              <details className="sidebar-advanced" open>
                <summary>Module, strings, trackers &amp; roads</summary>
                <div className="grid-2 layout-custom-row">
                  <div className="field">
                    <label htmlFor="out-module-wp">Module Wp</label>
                    <input
                      id="out-module-wp"
                      type="number"
                      min="200"
                      max="1000"
                      value={moduleWp}
                      onChange={(e) => setModuleWp(Number(e.target.value))}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="out-mps">Modules / string</label>
                    <input
                      id="out-mps"
                      type="number"
                      min="8"
                      max="50"
                      value={modulesPerString}
                      onChange={(e) => setModulesPerString(Number(e.target.value))}
                    />
                  </div>
                </div>
                <div className="grid-2 layout-custom-row">
                  <div className="field">
                    <label htmlFor="out-mod-h">Height (m)</label>
                    <input
                      id="out-mod-h"
                      type="number"
                      step="0.001"
                      value={moduleH}
                      onChange={(e) => setModuleH(Number(e.target.value))}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="out-mod-w">Width (m)</label>
                    <input
                      id="out-mod-w"
                      type="number"
                      step="0.001"
                      value={moduleW}
                      onChange={(e) => setModuleW(Number(e.target.value))}
                    />
                  </div>
                </div>
                <div className="field">
                  <label htmlFor="out-string-gap">String gap (m)</label>
                  <input
                    id="out-string-gap"
                    type="number"
                    step="0.05"
                    min="0"
                    value={interStringGap}
                    onChange={(e) => setInterStringGap(Number(e.target.value))}
                  />
                </div>
                <div className="grid-2 layout-custom-row">
                  <div className="field">
                    <label htmlFor="out-tracker-strings">Tracker strings</label>
                    <input
                      id="out-tracker-strings"
                      value={trackerStringOptions}
                      onChange={(e) => setTrackerStringOptions(e.target.value)}
                      placeholder="8,7,6,5"
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="out-max-tracker">Max tracker m</label>
                    <input
                      id="out-max-tracker"
                      type="number"
                      min="20"
                      max="500"
                      value={maxTrackerLength}
                      onChange={(e) => setMaxTrackerLength(Number(e.target.value))}
                    />
                  </div>
                </div>
                <label className="checkbox-field layout-bifacial">
                  <input
                    type="checkbox"
                    checked={excludeTrackerSlope}
                    onChange={(e) => setExcludeTrackerSlope(e.target.checked)}
                  />
                  Exclude SAT zones above slope limit
                </label>
                <div className="field">
                  <label htmlFor="out-slope-limit">SAT slope limit (%)</label>
                  <input
                    id="out-slope-limit"
                    type="number"
                    step="0.5"
                    min="0.5"
                    max="30"
                    value={trackerSlopeLimit}
                    onChange={(e) => setTrackerSlopeLimit(Number(e.target.value))}
                    disabled={!excludeTrackerSlope}
                  />
                </div>
                {restrictionPolygons.length ? (
                  <p className="hint sidebar-hint">
                    {restrictionPolygons.length} manual no-build zone
                    {restrictionPolygons.length === 1 ? "" : "s"} will be excluded.
                  </p>
                ) : null}
                {gisBusy ? (
                  <p className="hint sidebar-hint">
                    Preparing GIS buildable envelope before LayoutIQ…
                  </p>
                ) : layoutUsesGisBuildable ? (
                  <p className="hint sidebar-hint">
                    LayoutIQ will use SiteIQ buildable constraints ({gisResult?.buildable_pct}% buildable).
                  </p>
                ) : gisError ? (
                  <p className="hint sidebar-hint">
                    GIS constraints unavailable; LayoutIQ will use the submitted boundary.
                  </p>
                ) : null}
                <div className="layout-road-tab-row">
                  <button
                    type="button"
                    className={`btn btn-ghost btn-sm${roadMode === "auto" ? " active" : ""}`}
                    onClick={() => {
                      setRoadMode("auto");
                      setRoadPreset("sat_auto");
                    }}
                  >
                    Auto roads
                  </button>
                  <button
                    type="button"
                    className={`btn btn-ghost btn-sm${roadMode !== "auto" ? " active" : ""}`}
                    onClick={() => setRoadMode("manual")}
                  >
                    Presets
                  </button>
                </div>
                {roadMode === "auto" ? (
                  <p className="hint sidebar-hint">2 tracker rows + 5 m N-S gap</p>
                ) : (
                  <div className="field">
                    <label htmlFor="out-road-preset">Road preset</label>
                    <select
                      id="out-road-preset"
                      value={roadPreset}
                      onChange={(e) => {
                        const id = e.target.value;
                        setRoadPreset(id);
                        setRoadMode(id === "no_roads" ? "off" : "manual");
                      }}
                    >
                      {ROAD_PRESETS.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                {roadPreset === "custom" ? (
                  <div className="grid-2 layout-custom-row">
                    <div className="field">
                      <label htmlFor="out-rows-block">Rows / block</label>
                      <input
                        id="out-rows-block"
                        type="number"
                        min="1"
                        value={rowsPerBlock}
                        onChange={(e) => setRowsPerBlock(Number(e.target.value))}
                      />
                    </div>
                    <div className="field">
                      <label htmlFor="out-block-gap">N-S gap (m)</label>
                      <input
                        id="out-block-gap"
                        type="number"
                        step="0.5"
                        min="0"
                        value={blockGapM}
                        onChange={(e) => setBlockGapM(Number(e.target.value))}
                      />
                    </div>
                  </div>
                ) : null}
              </details>
              {layoutOptimization === "custom" ? (
                <div className="grid-2 layout-custom-row">
                  <div className="field">
                    <label htmlFor="layout-custom-gcr">Custom GCR</label>
                    <input
                      id="layout-custom-gcr"
                      type="number"
                      step="0.01"
                      min="0.15"
                      max="0.75"
                      placeholder="0.45"
                      value={layoutCustomGcr}
                      onChange={(e) => setLayoutCustomGcr(e.target.value)}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="layout-custom-pitch">Custom pitch m</label>
                    <input
                      id="layout-custom-pitch"
                      type="number"
                      step="0.1"
                      min="3"
                      max="20"
                      placeholder="6.5"
                      value={layoutCustomPitch}
                      onChange={(e) => setLayoutCustomPitch(e.target.value)}
                    />
                  </div>
                </div>
              ) : null}
              <button
                className="btn btn-primary btn-block"
                type="button"
                onClick={() => void handleLayoutSweep()}
                disabled={layoutBusy || gisBusy}
              >
                {layoutBusy ? "Running layout sweep…" : gisBusy ? "Preparing buildable area…" : "Run layout sweep"}
              </button>
            </>
          )}
        </div>
        ) : null}

        {activeStage === "yield" ? (
        <>
        <div className="sidebar-group">
          <h3>YieldIQ</h3>
          {selectedLayoutRow ? (
            <p className="hint sidebar-hint">
              {selectedLayoutRow.label} · {selectedLayoutRow.pitch_m} m · GCR{" "}
              {selectedLayoutRow.gcr.toFixed(2)}
            </p>
          ) : (
            <p className="hint sidebar-hint">Select a layout row to enable yield.</p>
          )}
          <button
            className="btn btn-primary btn-block"
            type="button"
            onClick={() => void handleRunYield()}
            disabled={yieldBusy || !selectedLayoutRow}
          >
            {yieldBusy ? "Running YieldIQ…" : "Run YieldIQ"}
          </button>
        </div>

        <div className="sidebar-group sidebar-deliverables">
          <h3>Project deliverables</h3>
          <p className="hint sidebar-hint">
            PVMath report combines SiteIQ, TopoIQ, LayoutIQ, and YieldIQ. Project package adds A3 layout sheet, BOM CSV, and DXF.
          </p>
          <button
            className="btn btn-primary btn-block"
            type="button"
            onClick={() => void handlePvmathReport()}
            disabled={reportBusy}
          >
            {reportBusy ? "Generating report…" : "PVMath report (PDF)"}
          </button>
          <button
            className="btn btn-ghost btn-block"
            type="button"
            onClick={() => void handleProjectPackage()}
            disabled={packageBusy || !selectedLayoutRow || !hasBoundary}
          >
            {packageBusy ? "Building package…" : "Project package (ZIP)"}
          </button>
          {!selectedLayoutRow || !hasBoundary ? (
            <p className="hint sidebar-hint">Select a layout row and boundary for the full package.</p>
          ) : null}
        </div>

        <div className="sidebar-group sidebar-score">
          <h3>Overall PVMath score</h3>
          {overallReady ? (
            <div className="overall-score-body">
              <span className="score-pill score-pill-lg">{overallScore}</span>
              <div>
                <strong>{finalScore?.verdict}</strong>
                <p>{finalScore?.verdict_detail}</p>
              </div>
            </div>
          ) : (
            <p className="hint sidebar-hint">
              Complete TopoIQ to compute the overall PVMath score.
            </p>
          )}
        </div>
        </>
        ) : null}

        {activeStage === "topo" && overallReady ? (
        <div className="sidebar-group sidebar-score">
          <h3>Overall PVMath score</h3>
          <div className="overall-score-body">
            <span className="score-pill score-pill-lg">{overallScore}</span>
            <div>
              <strong>{finalScore?.verdict}</strong>
              <p>{finalScore?.verdict_detail}</p>
            </div>
          </div>
        </div>
        ) : null}

        <div className="sidebar-actions">
          <button className="btn btn-ghost btn-block" type="button" onClick={onEditInput}>
            ← Edit input
          </button>
          <button className="btn btn-primary btn-block" type="button" onClick={onNewScreening}>
            New project
          </button>
        </div>
      </aside>
      ) : null}

      <div className="results-main">
      {activeStage === "screen" ? (
      <div className="results-stage-header">
        <div>
          <h1>{result.project_name}</h1>
          <div className="coord-pill">
            {result.coordinates.lat.toFixed(4)}°, {result.coordinates.lon.toFixed(4)}°
          </div>
        </div>
        <div className="results-stage-header-actions">
          <button className="btn btn-ghost btn-sm" type="button" onClick={onEditInput}>
            Edit input
          </button>
          <button className="btn btn-ghost btn-sm" type="button" onClick={onNewScreening}>
            New project
          </button>
        </div>
      </div>
      ) : null}
      {activeStage === "screen" ? (
      <section className="module-card module-screen">
        <div className="module-head">
          <h2>Site screening</h2>
          <span className="module-tag">Step 1</span>
        </div>
        <div className="metrics">
          {metric(
            "Solar",
            String(result.solar.rating ?? "—"),
            String(result.solar.detail ?? ""),
            result.solar.annual_ghi ? `${result.solar.annual_ghi} kWh/m²/yr` : undefined,
          )}
          {metric(
            "Flood",
            String(result.flood.risk ?? "—"),
            String(result.flood.detail ?? ""),
          )}
          {metric(
            "Grid proximity",
            String(grid.rating ?? "—"),
            String(grid.detail ?? ""),
            grid.found && nearest
              ? `${nearest.name ?? "Substation"} · ${grid.distance_km} km${
                  nearest.voltage ? ` · ${nearest.voltage}` : ""
                }`
              : grid.found === false
                ? `No OSM substation within ${grid.search_radius_km ?? "?"} km`
                : undefined,
          )}
          {metric(
            "Regulatory",
            String(result.regulatory.status ?? "—"),
            String(result.regulatory.note ?? ""),
          )}
        </div>
        <p className="module-note">{result.terrain_note}</p>
        <p className="module-note">
          Capacity is computed in LayoutIQ in the next steps (per mount type, portrait,
          and GCR) — not estimated here.
        </p>
        {grid.disclaimer ? <p className="module-note">{String(grid.disclaimer)}</p> : null}
        {result.errors.length > 0 ? (
          <div className="error-banner" style={{ marginTop: "1rem" }}>
            {result.errors.join(" · ")}
          </div>
        ) : null}

        {hasBoundary ? (
          <div className="gis-analysis-block">
            <h3 className="setup-subhead">Intelligent GIS analysis</h3>
            <p className="hint">
              Automatic constraint detection from OpenStreetMap — roads, railways, buildings,
              water, forests, and transmission lines — with engineering setbacks applied to
              compute buildable area. No extra input required.
            </p>
            {gisBusy && !gisResult ? (
              <p className="hint">Detecting site constraints and computing buildable area…</p>
            ) : null}
            {gisError ? <div className="error-banner">{gisError}</div> : null}
            {gisResult?.success ? (
              <>
                <div className="gis-stats">
                  <div className="gis-stat">
                    <span className="gis-stat-label">Total site</span>
                    <strong>{gisResult.site_area_ha} ha</strong>
                  </div>
                  <div className="gis-stat">
                    <span className="gis-stat-label">Buildable</span>
                    <strong>{gisResult.buildable_area_ha} ha</strong>
                  </div>
                  <div className="gis-stat gis-stat-accent">
                    <span className="gis-stat-label">Buildable %</span>
                    <strong>{gisResult.buildable_pct}%</strong>
                  </div>
                  <div className="gis-stat">
                    <span className="gis-stat-label">Land score</span>
                    <strong>{scoreLandFromBuildablePct(gisResult.buildable_pct) ?? "—"}/100</strong>
                  </div>
                </div>
                {gisResult.constraint_summary.length > 0 ? (
                  <table className="gis-summary-table">
                    <thead>
                      <tr>
                        <th>Constraint</th>
                        <th>Features</th>
                        <th>Setback</th>
                        <th>Excluded</th>
                      </tr>
                    </thead>
                    <tbody>
                      {gisResult.constraint_summary.map((row) => (
                        <tr key={row.category}>
                          <td>{row.label}</td>
                          <td>{row.feature_count}</td>
                          <td>{row.setback_m} m</td>
                          <td>{row.excluded_ha} ha</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="hint">No mapped constraints detected inside the boundary.</p>
                )}
                <ConstraintAnalysisMap
                  lat={gisResult.coordinates?.lat ?? input?.lat ?? 0}
                  lon={gisResult.coordinates?.lon ?? input?.lon ?? 0}
                  siteBoundary={gisResult.site_boundary_geojson ?? undefined}
                  constraintLayers={gisResult.constraint_layers}
                  layerStyles={gisResult.layer_styles}
                  buildableArea={gisResult.buildable_area_geojson ?? undefined}
                  excludedArea={gisResult.excluded_area_geojson ?? undefined}
                />
                {gisResult.disclaimer ? (
                  <p className="module-note">{gisResult.disclaimer}</p>
                ) : null}
              </>
            ) : null}
          </div>
        ) : (
          <p className="hint">
            Draw or upload a site boundary to run automatic GIS constraint analysis and
            buildable-area calculation.
          </p>
        )}
        <div className="stage-proceed-bar">
          <button className="btn btn-primary" type="button" onClick={proceedToTopo}>
            Proceed to TopoIQ →
          </button>
        </div>
      </section>
      ) : null}

      {activeStage === "topo" ? (
      <section className="module-card module-topoiq">
        <div className="module-head">
          <h2>TopoIQ terrain</h2>
          <span className="module-tag">Step 2 · authoritative terrain</span>
        </div>
        {!hasBoundary ? (
          <p className="hint">
            Draw or upload a site boundary on Project input. Terrain slope and the PVMath
            terrain score come only from TopoIQ — not from site screening.
          </p>
        ) : (
          <>
            {topoBusy && !topoResult ? (
              <p className="hint">Running TopoIQ on your boundary grid…</p>
            ) : !topoResult ? (
              <p className="hint">TopoIQ runs automatically when you open this step.</p>
            ) : null}
            {topoResult ? (
              <>
                {topoResult.grid_m_used > topoResult.grid_m_requested ? (
                  <p className="module-note topo-grid-note">
                    Grid coarsened to <strong>{topoResult.grid_m_used.toFixed(0)} m</strong> (requested{" "}
                    {topoResult.grid_m_requested.toFixed(0)} m) for this boundary size — suitable for
                    preliminary screening.
                  </p>
                ) : null}
                <div className="metrics module-metrics">
                  {metric("Elev Range", `${topoResult.elevation.z_range.toFixed(0)} m`)}
                  {metric("Mean Slope", `${topoResult.slope.mean.toFixed(1)}%`)}
                  {metric("Max Slope", `${topoResult.slope.max.toFixed(1)}%`)}
                  {metric(">5% Area", `${topoResult.slope.pct_over5.toFixed(1)}%`)}
                  {metric(">10% Area", `${topoResult.slope.pct_over10.toFixed(1)}%`)}
                </div>
                <div className="module-note">
                  <strong>Fixed Tilt:</strong> {topoResult.verdict_fixed.label} —{" "}
                  {topoResult.verdict_fixed.detail}
                  <br />
                  <strong>Single-Axis Tracker:</strong> {topoResult.verdict_tracker.label} —{" "}
                  {topoResult.verdict_tracker.detail}
                  <br />
                  <strong>Source:</strong> {topoResult.terrain_source_used}
                </div>
                {renderTerrainDrivers(topoResult)}
                {renderSlopeMap()}
              </>
            ) : null}
          </>
        )}
        {topoError ? <div className="error-banner">{topoError}</div> : null}
        {renderTopoRecovery()}
        {exportError ? <div className="error-banner">{exportError}</div> : null}
        <div className="stage-proceed-bar stage-proceed-bar-split">
          {topoError && !topoResult ? (
            <p className="hint stage-proceed-hint">
              You can continue to LayoutIQ without terrain — the PVMath score will be incomplete until
              TopoIQ succeeds.
            </p>
          ) : (
            <span />
          )}
          <button
            className="btn btn-primary"
            type="button"
            onClick={proceedToLayout}
            disabled={!hasBoundary}
          >
            {topoResult ? "Proceed to LayoutIQ →" : "Continue without terrain →"}
          </button>
        </div>
      </section>
      ) : null}

      {activeStage === "layout" ? (
      <section className="module-card module-layout">
        <div className="module-head">
          <h2>LayoutIQ — capacity vs pitch</h2>
          <span className="module-tag">Step 3</span>
        </div>
        {!hasBoundary ? (
          <p className="hint">Draw a site boundary to run the layout sweep.</p>
        ) : (
          <>
            <p className="hint">
              Sweeps Fixed Tilt 1P–4P and Single-Axis Tracker 1P–2P across industry pitch/GCR
              bands. Configure options in the sidebar, then run the sweep.
            </p>
            {!topoResult ? (
              <p className="module-note">TopoIQ should finish first — layout uses your boundary polygon.</p>
            ) : null}
            {!layoutSweep && !layoutBusy ? (
              <p className="module-note">Run the layout sweep from the LayoutIQ sidebar.</p>
            ) : null}
            {layoutBusy ? <p className="hint">Running layout sweep…</p> : null}
            {layoutSweep && layoutConfigKeys.length > 0 ? (
              <div className="layout-matrix">
                {layoutSweep.strategy?.mode_label ? (
                  <p className="module-note layout-strategy-note">
                    <strong>{layoutSweep.strategy.mode_label}</strong>
                    {layoutSweep.strategy.land_cost_label
                      ? ` · ${layoutSweep.strategy.land_cost_label}`
                      : null}
                    {layoutSweep.strategy.note ? ` — ${layoutSweep.strategy.note}` : null}
                  </p>
                ) : null}
                <div className="layout-filter-row">
                  <button
                    type="button"
                    className={`btn btn-ghost btn-sm${layoutFilter === "all" ? " active" : ""}`}
                    onClick={() => setLayoutFilter("all")}
                  >
                    All
                  </button>
                  {layoutConfigKeys.map((key) => (
                    <button
                      key={key}
                      type="button"
                      className={`btn btn-ghost btn-sm${layoutFilter === key ? " active" : ""}`}
                      onClick={() => setLayoutFilter(key)}
                    >
                      {layoutSweep.best_by_config[key]?.label ?? key}
                    </button>
                  ))}
                </div>
                {layoutFilter !== "all" && layoutSweep.recommended_by_config?.[layoutFilter] ? (
                  <p className="module-note">
                    Recommended for this config:{" "}
                    <strong>
                      GCR {layoutSweep.recommended_by_config[layoutFilter].gcr?.toFixed(2)} · pitch{" "}
                      {layoutSweep.recommended_by_config[layoutFilter].pitch_m} m
                    </strong>
                    {layoutSweep.recommended_by_config[layoutFilter].success ? (
                      <>
                        {" "}
                        → {formatLayoutMwp(layoutSweep.recommended_by_config[layoutFilter])} MWp
                      </>
                    ) : (
                      " (did not fit boundary at recommended pitch)"
                    )}
                    {layoutSweep.best_by_config[layoutFilter] ? (
                      <>
                        {" "}
                        · Max capacity: {formatLayoutMwp(layoutSweep.best_by_config[layoutFilter])}{" "}
                        MWp at GCR {layoutSweep.best_by_config[layoutFilter].gcr?.toFixed(2)}
                      </>
                    ) : null}
                  </p>
                ) : null}
                <table className="yield-table">
                  <thead>
                    <tr>
                      <th>Configuration</th>
                      <th>Pitch (m)</th>
                      <th>GCR</th>
                      <th>Modules</th>
                      <th>DC (MWp)</th>
                      <th>MW/ha</th>
                      <th>Yield input</th>
                    </tr>
                  </thead>
                  <tbody>
                    {layoutRows.map((row) => (
                      <tr
                        key={`${row.config_key}-${row.pitch_m}`}
                        className={
                          selectedLayoutRow?.config_key === row.config_key &&
                          selectedLayoutRow?.pitch_m === row.pitch_m
                            ? "layout-row-selected"
                            : row.is_recommended
                              ? "layout-row-recommended"
                              : ""
                        }
                      >
                        <td>
                          {row.label}
                          {row.is_recommended ? (
                            <span className="layout-rec-badge">Rec.</span>
                          ) : null}
                        </td>
                        <td>{row.pitch_m}</td>
                        <td>{row.gcr.toFixed(2)}</td>
                        <td>{row.total_modules?.toLocaleString() ?? "—"}</td>
                        <td>{formatLayoutMwp(row)}</td>
                        <td>{row.mw_per_ha != null ? row.mw_per_ha.toFixed(2) : "—"}</td>
                        <td>
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            onClick={() => {
                              setSelectedLayoutRow(row);
                              setLayoutDetail(null);
                              setTerrain3D(null);
                              setYieldResult(null);
                              void handleLayoutDetail(row);
                            }}
                          >
                            {selectedLayoutRow?.config_key === row.config_key &&
                            selectedLayoutRow?.pitch_m === row.pitch_m
                              ? "Selected"
                              : "Select"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="module-note">
                  {layoutSweep.row_count} pitch steps · whole strings only ({modulesPerString} modules
                  / string, {interStringGap} m gap) · N-S access per road preset.{" "}
                  <strong>Rec.</strong> marks industry-recommended GCR/pitch.
                </p>
                {selectedLayoutRow ? (
                  <div className="layout-preview-panel">
                    <div className="layout-preview-head">
                      <div>
                        <strong>Selected web layout</strong>
                        <p>
                          {selectedLayoutRow.label} · {selectedLayoutRow.pitch_m} m pitch · GCR{" "}
                          {selectedLayoutRow.gcr.toFixed(2)}
                        </p>
                      </div>
                      <div className="layout-preview-actions">
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => void handleLayoutDetail()}
                          disabled={layoutDetailBusy}
                        >
                          {layoutDetailBusy ? "Loading preview…" : "Refresh preview"}
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => void handleLayoutDxf()}
                          disabled={layoutDxfBusy}
                        >
                          {layoutDxfBusy ? "Preparing DXF…" : "Download layout DXF"}
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => void handleTerrain3D()}
                          disabled={terrain3DBusy}
                        >
                          {terrain3DBusy ? "Building 3D…" : "3D terrain"}
                        </button>
                      </div>
                    </div>
                    {layoutDetail ? (
                      <>
                        <LayoutPreviewMap
                          center={{ lat: result.coordinates.lat, lon: result.coordinates.lon }}
                          layoutGeoJson={layoutDetail.geojson}
                        />
                        <p className="module-note">
                          Preview contains {layoutDetail.total_rows.toLocaleString()} PV rows and{" "}
                          {layoutDetail.total_modules.toLocaleString()} modules. DXF uses the same
                          row polygons in local metric coordinates.
                        </p>
                      </>
                    ) : (
                      <p className="module-note">
                        {layoutDetailBusy ? "Generating row polygons…" : "Select or refresh to load row polygons."}
                      </p>
                    )}
                    {terrain3D ? (
                      <>
                        <Terrain3DView mesh={terrain3D} layoutGeoJson={layoutDetail?.geojson ?? null} />
                        <p className="module-note">
                          3D terrain uses a coarse TopoIQ DEM mesh from {terrain3D.terrain_source_used}.
                          PV rows are draped above sampled terrain elevation; the sun slider is the
                          first visual layer before full shading-loss simulation.
                        </p>
                      </>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}
          </>
        )}
        {layoutError ? <div className="error-banner">{layoutError}</div> : null}
        <div className="stage-proceed-bar">
          <button
            className="btn btn-primary"
            type="button"
            onClick={proceedToYield}
            disabled={!selectedLayoutRow}
          >
            Proceed to YieldIQ →
          </button>
        </div>
      </section>
      ) : null}

      {activeStage === "yield" ? (
      <section className="module-card module-yieldiq">
        <div className="module-head">
          <h2>YieldIQ — selected layout yield</h2>
          <span className="module-tag">Step 4</span>
        </div>
        {selectedLayoutRow ? (
          <p className="hint">
            Using {selectedLayoutRow.label}, {selectedLayoutRow.pitch_m} m pitch, GCR{" "}
            {selectedLayoutRow.gcr.toFixed(2)}, and {selectedLayoutRow.dc_kwp?.toLocaleString()} kWp
            DC from LayoutIQ. Run YieldIQ from the YieldIQ sidebar.
          </p>
        ) : (
          <p className="hint">Select a LayoutIQ row, then run YieldIQ from the YieldIQ sidebar.</p>
        )}
        {yieldResult ? (
          <div className="yield-table-wrap">
            {selectedYieldConfig && selectedAnnualMwh != null ? (
              <div className="selected-yield-summary">
                <strong>Selected layout estimate:</strong>{" "}
                {selectedAnnualMwh.toFixed(0)} MWh/yr at{" "}
                {Number(selectedYieldConfig.spec_y).toFixed(0)} kWh/kWp/yr.
              </div>
            ) : null}
            <table className="yield-table">
              <thead>
                <tr>
                  <th>Configuration</th>
                  <th>Specific Yield</th>
                  <th>PR</th>
                  <th>GCR</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(yieldResult.configs).map(([cfg, payload]) => (
                  <tr key={cfg}>
                    <td>{payload.display_name}</td>
                    <td>{Number(payload.spec_y).toFixed(0)} kWh/kWp/yr</td>
                    <td>{payload.pr != null ? `${Number(payload.pr).toFixed(1)}%` : "—"}</td>
                    <td>{Number(payload.gcr).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="module-note">
              {yieldResult.disclosure} For FT 3P/4P, YieldIQ uses the selected GCR through the
              fixed-tilt PVGIS profile while LayoutIQ keeps the exact portrait count for capacity.
            </p>
          </div>
        ) : null}
        {yieldError ? <div className="error-banner">{yieldError}</div> : null}
      </section>
      ) : null}

      <p className="disclaimer footer-note">
        Screening-grade only — not bankable. Terrain from TopoIQ grid only. Data: PVGIS (JRC),
        routed public DEM, OpenStreetMap.
      </p>
      </div>
    </div>
  );
}
