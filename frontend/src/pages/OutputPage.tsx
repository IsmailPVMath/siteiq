import { COMPANY_NAME } from "../lib/brand";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  analyzeTopo,
  analyzeYield,
  createProject,
  updateProject,
  reverseGeocode,
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
import {
  persistWorkflowProject,
  type WorkflowRestore,
} from "../lib/workflowSave";
import { mergeLayoutIQSnapshot, type LayoutIQSnapshot } from "../lib/layoutIQSettings";
import { ConstraintAnalysisMap } from "../components/ConstraintAnalysisMap";
import { LayoutPreviewMap } from "../components/LayoutPreviewMap";
import { NumberField } from "../components/NumberField";
import { YieldResultsPanel } from "../components/YieldResultsPanel";
import { SlopeTopMap } from "../components/SlopeTopMap";
import { Terrain3DView } from "../components/Terrain3DView";
import type { GateAnalyzeRequest } from "../types/gate";
import {
  DEFAULT_LAYOUT_CONFIG,
  ROAD_PRESETS,
  layoutPayloadFrom,
  roadParamsFromPreset,
  type RoadMode,
  type RowAlignment,
} from "../types/layoutConfig";
import type { TerrainIQAnalyzeRequest, TerrainIQAnalyzeResponse, YieldIQAnalyzeResponse } from "../types/terrainiq";
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

// Realistic global PV module / slope bounds (utility-scale, 2026 market survey).
// Largest mass-production modules are ~2.4-2.5 m long and ~1.3-1.34 m wide
// (Trina Vertex, Jinko Tiger Neo, Canadian Solar large-format). Caps are set a
// little above that to flag decimal-point mistakes (e.g. 2384 instead of 2.384)
// without rejecting any real module. Steepest SAT terrain in the market is ~36%
// (≈20°), so slope is capped there.
const MODULE_H_RANGE = { min: 0.5, max: 3.0 }; // module length (m)
const MODULE_W_RANGE = { min: 0.3, max: 1.6 }; // module width (m)
const SLOPE_MAX_PCT = 36;

interface Props {
  token: string;
  result: WorkflowScreenResponse;
  input?: GateAnalyzeRequest;
  activeModule: OutputModuleStage;
  onModuleChange: (stage: OutputModuleStage) => void;
  onNewScreening: () => void;
  onEditInput: () => void;
  projectId?: string;
  initialTopo?: TerrainIQAnalyzeResponse | null;
  initialFinalScore?: WorkflowScoreResponse | null;
  initialGisSetbacks?: Record<string, number> | null;
  initialLayoutSettings?: LayoutIQSnapshot | null;
  onProjectIdChange?: (id: string) => void;
  onWorkflowDepth?: (stage: OutputModuleStage) => void;
  onWorkflowPersist?: (patch: Partial<WorkflowRestore>) => void;
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
  if (row.dc_mwp != null) return row.dc_mwp.toFixed(3);
  if (row.dc_kwp != null) return (row.dc_kwp / 1000).toFixed(3);
  return "—";
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  window.setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 1500);
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
  projectId: projectIdProp = "",
  initialTopo = null,
  initialFinalScore = null,
  initialGisSetbacks = null,
  initialLayoutSettings = null,
  onProjectIdChange,
  onWorkflowDepth,
  onWorkflowPersist,
}: Props) {
  const activeStage = activeModule;
  const setActiveStage = onModuleChange;
  const layoutInit = useRef(mergeLayoutIQSnapshot(initialLayoutSettings, input)).current;

  const SIDEBAR_MIN = 240;
  const SIDEBAR_MAX = 560;
  const SIDEBAR_DEFAULT = 320;
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    const stored = Number(localStorage.getItem("pvm_results_sb_width"));
    return stored ? Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, stored)) : SIDEBAR_DEFAULT;
  });
  const sidebarDraggingRef = useRef(false);
  useEffect(() => {
    localStorage.setItem("pvm_results_sb_width", String(sidebarWidth));
  }, [sidebarWidth]);
  const onSidebarPointerMove = useRef((e: PointerEvent) => {
    if (!sidebarDraggingRef.current) return;
    const shell = document.querySelector(".results-shell") as HTMLElement | null;
    const left = shell?.getBoundingClientRect().left ?? 0;
    const next = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, e.clientX - left));
    setSidebarWidth(next);
  });
  const stopSidebarDrag = useRef(() => {
    sidebarDraggingRef.current = false;
    document.body.classList.remove("sb-resizing");
    window.removeEventListener("pointermove", onSidebarPointerMove.current);
    window.removeEventListener("pointerup", stopSidebarDrag.current);
  });
  function startSidebarDrag(e: React.PointerEvent) {
    e.preventDefault();
    sidebarDraggingRef.current = true;
    document.body.classList.add("sb-resizing");
    window.addEventListener("pointermove", onSidebarPointerMove.current);
    window.addEventListener("pointerup", stopSidebarDrag.current);
  }
  useEffect(() => () => stopSidebarDrag.current(), []);

  const [projectId, setProjectId] = useState(projectIdProp);
  const [saveBusy, setSaveBusy] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [topoBusy, setTopoBusy] = useState(false);
  const [topoError, setTopoError] = useState("");
  const [topoResult, setTopoResult] = useState<TerrainIQAnalyzeResponse | null>(initialTopo);
  const [topoGridM, setTopoGridM] = useState(5);
  const [topoAllowCoarsen, setTopoAllowCoarsen] = useState(true);
  const topoAutoRan = useRef(Boolean(initialTopo));
  const autoSaveBusy = useRef(false);
  const yieldAutoRan = useRef(false);
  const [topoPdfBusy, setTopoPdfBusy] = useState(false);
  const [topoZipBusy, setTopoZipBusy] = useState(false);
  const [topoMesh, setTopoMesh] = useState<WorkflowTerrainMeshResponse | null>(null);
  const [topoMeshBusy, setTopoMeshBusy] = useState(false);
  const [yieldBusy, setYieldBusy] = useState(false);
  const [yieldError, setYieldError] = useState("");
  const [yieldResult, setYieldResult] = useState<YieldIQAnalyzeResponse | null>(null);
  const [finalScore, setFinalScore] = useState<WorkflowScoreResponse | null>(initialFinalScore);
  const [layoutBusy, setLayoutBusy] = useState(false);
  const [layoutError, setLayoutError] = useState("");
  const [layoutSweep, setLayoutSweep] = useState<WorkflowLayoutSweepResponse | null>(null);
  const [layoutFilter, setLayoutFilter] = useState<string>("all");
  const [selectedLayoutRow, setSelectedLayoutRow] = useState<LayoutSweepRow | null>(
    layoutInit.selected_layout_row,
  );
  const [layoutDetailBusy, setLayoutDetailBusy] = useState(false);
  const [layoutDxfBusy, setLayoutDxfBusy] = useState(false);
  const [layoutDetail, setLayoutDetail] = useState<WorkflowLayoutDetailResponse | null>(null);
  const [terrain3DBusy, setTerrain3DBusy] = useState(false);
  const [terrain3D, setTerrain3D] = useState<WorkflowTerrainMeshResponse | null>(null);
  const [layoutOptimization, setLayoutOptimization] = useState<LayoutOptimizationMode>(
    layoutInit.optimization_mode,
  );
  const [layoutLandCost, setLayoutLandCost] = useState<LayoutLandCost>(layoutInit.land_cost);
  const [layoutBifacial, setLayoutBifacial] = useState(layoutInit.bifacial);
  const [allowPartialStrings, setAllowPartialStrings] = useState(layoutInit.allow_partial_strings);
  const [layoutMountType, setLayoutMountType] = useState<"Fixed Tilt" | "Single-Axis Tracker">(
    layoutInit.mount_type,
  );
  const [layoutPortrait, setLayoutPortrait] = useState<"all" | "1" | "2" | "3" | "4">(
    layoutInit.portrait,
  );
  const [layoutRowAlignment, setLayoutRowAlignment] = useState<RowAlignment>(layoutInit.row_alignment);
  const [layoutCustomGcr, setLayoutCustomGcr] = useState(layoutInit.custom_gcr);
  const [layoutCustomPitch, setLayoutCustomPitch] = useState(layoutInit.custom_pitch);
  const [moduleH, setModuleH] = useState(layoutInit.module_h);
  const [moduleW, setModuleW] = useState(layoutInit.module_w);
  const [moduleWp, setModuleWp] = useState(layoutInit.module_wp);
  const [modulesPerString, setModulesPerString] = useState(layoutInit.modules_per_string);
  const [interStringGap, setInterStringGap] = useState(layoutInit.inter_string_gap_m);
  const [trackerStringOptions, setTrackerStringOptions] = useState(layoutInit.tracker_string_options);
  const [maxTrackerLength, setMaxTrackerLength] = useState(layoutInit.max_tracker_length_m);
  const [excludeTrackerSlope, setExcludeTrackerSlope] = useState(layoutInit.exclude_tracker_slope);
  const [trackerSlopeLimit, setTrackerSlopeLimit] = useState(layoutInit.tracker_slope_limit_pct);
  const [roadMode, setRoadMode] = useState<RoadMode>(layoutInit.road_mode);
  const [roadPreset, setRoadPreset] = useState(layoutInit.road_preset);
  const [azimuthDeg, setAzimuthDeg] = useState<number>(layoutInit.azimuth_deg);
  const [azimuthCustom, setAzimuthCustom] = useState<boolean>(layoutInit.azimuth_custom);
  const [rowsPerBlock, setRowsPerBlock] = useState(layoutInit.rows_per_block);
  const [blockGapM, setBlockGapM] = useState(layoutInit.block_gap_m);
  const [nsGap1M, setNsGap1M] = useState(layoutInit.ns_gap_1_m);
  const [colsPerBlock, setColsPerBlock] = useState(layoutInit.cols_per_block);
  const [ewGapM, setEwGapM] = useState(layoutInit.ew_gap_m);
  const [reportBusy, setReportBusy] = useState(false);
  const [packageBusy, setPackageBusy] = useState(false);
  const [exportError, setExportError] = useState("");
  const [locationLabel, setLocationLabel] = useState("");
  const [gisBusy, setGisBusy] = useState(false);
  const [gisRecomputeBusy, setGisRecomputeBusy] = useState(false);
  const [gisError, setGisError] = useState("");
  const [gisResult, setGisResult] = useState<WorkflowGisAnalysisResponse | null>(null);
  const [gisSetbacks, setGisSetbacks] = useState<Record<string, number>>(initialGisSetbacks ?? {});
  const gisLayersRef = useRef<Record<string, GeoJSON.FeatureCollection> | null>(null);
  const setbacksEditedRef = useRef(false);

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
  const [useFullBoundary, setUseFullBoundary] = useState(layoutInit.use_full_boundary);
  const gisExcludedRings = useMemo(
    () => geoJsonToLatLonRings(gisResult?.excluded_area_geojson ?? null),
    [gisResult?.excluded_area_geojson],
  );
  const layoutRestrictionPolygons = useMemo(
    () =>
      useFullBoundary
        ? restrictionPolygons
        : gisResult?.success && gisExcludedRings.length
          ? gisExcludedRings
          : restrictionPolygons,
    [useFullBoundary, gisExcludedRings, gisResult?.success, restrictionPolygons],
  );
  const layoutUsesGisBuildable = !useFullBoundary && !!(gisResult?.success && gisExcludedRings.length);
  const landScoreFromGis = useFullBoundary
    ? scoreLandFromBuildablePct(100)
    : scoreLandFromBuildablePct(gisResult?.buildable_pct);
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

  const moduleHWarning =
    moduleH < MODULE_H_RANGE.min || moduleH > MODULE_H_RANGE.max
      ? `Please check the dimension you entered — module length is normally ${MODULE_H_RANGE.min}–${MODULE_H_RANGE.max} m (you entered ${moduleH} m).`
      : "";
  const moduleWWarning =
    moduleW < MODULE_W_RANGE.min || moduleW > MODULE_W_RANGE.max
      ? `Please check the dimension you entered — module width is normally ${MODULE_W_RANGE.min}–${MODULE_W_RANGE.max} m (you entered ${moduleW} m).`
      : "";
  const slopeWarning =
    excludeTrackerSlope && trackerSlopeLimit > SLOPE_MAX_PCT
      ? `Max buildable SAT slope in the market is about ${SLOPE_MAX_PCT}% (≈20°). Please lower the slope limit.`
      : "";

  function layoutInputError(): string {
    return moduleHWarning || moduleWWarning || slopeWarning || "";
  }

  function applyRoadPresetToState(id: string) {
    const p = roadParamsFromPreset(id);
    setColsPerBlock(p.cols_per_block ?? 0);
    setEwGapM(p.ew_gap_m ?? 0);
    setRowsPerBlock(p.rows_per_block ?? 0);
    setNsGap1M(p.ns_gap_1_m ?? 0);
    setBlockGapM(p.block_gap_m ?? 0);
  }

  function buildLayoutIQSnapshot(): LayoutIQSnapshot {
    return {
      optimization_mode: layoutOptimization,
      land_cost: layoutLandCost,
      bifacial: layoutBifacial,
      allow_partial_strings: allowPartialStrings,
      mount_type: layoutMountType,
      portrait: layoutPortrait,
      row_alignment: layoutRowAlignment,
      custom_gcr: layoutCustomGcr,
      custom_pitch: layoutCustomPitch,
      module_h: moduleH,
      module_w: moduleW,
      module_wp: moduleWp,
      modules_per_string: modulesPerString,
      inter_string_gap_m: interStringGap,
      tracker_string_options: trackerStringOptions,
      max_tracker_length_m: maxTrackerLength,
      exclude_tracker_slope: excludeTrackerSlope,
      tracker_slope_limit_pct: trackerSlopeLimit,
      road_mode: roadMode,
      road_preset: roadPreset,
      rows_per_block: rowsPerBlock,
      block_gap_m: blockGapM,
      ns_gap_1_m: nsGap1M,
      cols_per_block: colsPerBlock,
      ew_gap_m: ewGapM,
      azimuth_deg: azimuthDeg,
      azimuth_custom: azimuthCustom,
      use_full_boundary: useFullBoundary,
      selected_layout_row: selectedLayoutRow,
    };
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
      ns_gap_1_m: nsGap1M,
      cols_per_block: colsPerBlock,
      ew_gap_m: ewGapM,
      exclude_tracker_slope: excludeTrackerSlope,
      tracker_slope_limit_pct: trackerSlopeLimit,
    });
    if (roadPreset === "custom") {
      return {
        ...base,
        azimuth: azimuthDeg,
        road_mode: "manual" as RoadMode,
        road_preset: "custom",
        rows_per_block: rowsPerBlock,
        block_gap_m: blockGapM,
        ns_gap_1_m: nsGap1M,
        cols_per_block: colsPerBlock,
        ew_gap_m: ewGapM,
        allow_partial_strings: allowPartialStrings,
        row_alignment: layoutRowAlignment,
      };
    }
    return { ...base, azimuth: azimuthDeg, allow_partial_strings: allowPartialStrings, row_alignment: layoutRowAlignment };
  }

  const buildableMask = useFullBoundary
    ? null
    : gisResult?.success
      ? (gisResult.buildable_area_geojson ?? null)
      : null;

  const topoPayload: TerrainIQAnalyzeRequest | null = useMemo(() => {
    if (!hasBoundary) return null;
    return {
      project_name: input?.project_name || result.project_name || "TerrainIQ run",
      country: input?.country || "",
      land_use: input?.land_use || "Standard",
      polygons: boundaries.map((ring) => ring.map((p) => ({ lat: p.lat, lon: p.lon }))),
      grid_m: topoGridM,
      allow_coarsen: topoAllowCoarsen,
      contour_minor: 0.5,
      contour_major: 1.0,
      mask_geojson: buildableMask,
    };
  }, [boundaries, hasBoundary, input, result.project_name, topoAllowCoarsen, topoGridM, buildableMask]);

  function updateGisSetback(category: string, raw: string) {
    const value = Math.max(0, Number(raw));
    if (!Number.isFinite(value)) return;
    setbacksEditedRef.current = true;
    setGisSetbacks((prev) => ({ ...prev, [category]: value }));
  }

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
          setbacks_m: Object.keys(gisSetbacks).length ? gisSetbacks : undefined,
          include_grid: false,
        });
        if (!cancelled) {
          setGisResult(data);
          setGisSetbacks(data.setbacks_m || {});
          gisLayersRef.current = data.constraint_layers;
          setbacksEditedRef.current = false;
        }
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, boundaries, hasBoundary, restrictionPolygons]);

  useEffect(() => {
    if (!hasBoundary || !setbacksEditedRef.current || !gisLayersRef.current) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void (async () => {
        setGisRecomputeBusy(true);
        setGisError("");
        try {
          const data = await workflowGisAnalysis(token, {
            boundaries,
            restriction_polygons_geojson: ringsToFeatureCollection(restrictionPolygons),
            setbacks_m: gisSetbacks,
            constraint_layers: gisLayersRef.current ?? undefined,
            include_grid: false,
          });
          if (!cancelled) {
            if (data.success) {
              setGisResult(data);
            } else {
              setGisError(data.error || "Could not update setbacks");
            }
          }
        } catch (err) {
          if (!cancelled) {
            setGisError(err instanceof Error ? err.message : "Setback update failed");
          }
        } finally {
          if (!cancelled) setGisRecomputeBusy(false);
        }
      })();
    }, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [gisSetbacks, token, boundaries, hasBoundary, restrictionPolygons]);

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
      mount_type: selectedLayoutRow?.mount_type || layoutMountType,
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

  async function refreshFinalScore(topo: TerrainIQAnalyzeResponse) {
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

  async function handleRunTopo(overrides?: Partial<TerrainIQAnalyzeRequest>) {
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
      void fetchTopoMesh();
      onWorkflowDepth?.("topo");
      autoSaveWorkflow("topo");
    } catch (err) {
      setTopoError(err instanceof Error ? err.message : "TerrainIQ analysis failed");
    } finally {
      setTopoBusy(false);
    }
  }

  async function fetchTopoMesh() {
    if (!boundaries.length) return;
    setTopoMeshBusy(true);
    try {
      const mesh = await workflowTerrainMesh(token, {
        boundaries,
        grid_m: 10,
        max_vertices: 40000,
        mask_geojson: buildableMask,
      });
      setTopoMesh(mesh);
    } catch {
      setTopoMesh(null);
    } finally {
      setTopoMeshBusy(false);
    }
  }

  async function persistWorkflow(options?: { silent?: boolean; stage?: OutputModuleStage }) {
    if (!input) return null;
    const stage = options?.stage ?? activeStage;
    setSaveBusy(true);
    if (!options?.silent) setSaveMsg("");
    try {
      const id = await persistWorkflowProject(
        token,
        projectId || undefined,
        input,
        result,
        stage,
        createProject,
        updateProject,
        {
          topo: topoResult,
          finalScore,
          gisSetbacks: Object.keys(gisSetbacks).length ? gisSetbacks : null,
          layoutSettings: buildLayoutIQSnapshot(),
        },
      );
      setProjectId(id);
      onProjectIdChange?.(id);
      const layoutSettings = buildLayoutIQSnapshot();
      onWorkflowPersist?.({
        projectId: id,
        lastStage: stage,
        topo: topoResult,
        finalScore,
        gisSetbacks: Object.keys(gisSetbacks).length ? gisSetbacks : null,
        layoutSettings,
      });
      if (!options?.silent) {
        setSaveMsg("Project saved — LayoutIQ settings and progress restored from My projects.");
      }
      return id;
    } catch (err) {
      if (!options?.silent) {
        setSaveMsg(err instanceof Error ? err.message : "Save failed");
      }
      return null;
    } finally {
      setSaveBusy(false);
    }
  }

  function autoSaveWorkflow(stage: OutputModuleStage) {
    if (autoSaveBusy.current) return;
    autoSaveBusy.current = true;
    void persistWorkflow({ silent: true, stage }).finally(() => {
      autoSaveBusy.current = false;
    });
  }

  async function handleSaveProject() {
    await persistWorkflow();
  }

  // Keep LayoutIQ settings in parent workflow state while editing (survives step navigation).
  useEffect(() => {
    if (!onWorkflowPersist) return;
    const timer = window.setTimeout(() => {
      onWorkflowPersist({ layoutSettings: buildLayoutIQSnapshot() });
    }, 600);
    return () => window.clearTimeout(timer);
  }, [
    onWorkflowPersist,
    layoutOptimization,
    layoutLandCost,
    layoutBifacial,
    allowPartialStrings,
    layoutMountType,
    layoutPortrait,
    layoutRowAlignment,
    layoutCustomGcr,
    layoutCustomPitch,
    moduleH,
    moduleW,
    moduleWp,
    modulesPerString,
    interStringGap,
    trackerStringOptions,
    maxTrackerLength,
    excludeTrackerSlope,
    trackerSlopeLimit,
    roadMode,
    roadPreset,
    rowsPerBlock,
    blockGapM,
    colsPerBlock,
    ewGapM,
    azimuthDeg,
    azimuthCustom,
    useFullBoundary,
    selectedLayoutRow,
  ]);

  useEffect(() => {
    if (projectIdProp) setProjectId(projectIdProp);
  }, [projectIdProp]);

  useEffect(() => {
    const lat = result.coordinates?.lat;
    const lon = result.coordinates?.lon;
    if (lat == null || lon == null) return;
    let cancelled = false;
    void (async () => {
      try {
        const geo = await reverseGeocode(token, lat, lon);
        if (!cancelled) setLocationLabel(geo.label || "");
      } catch {
        if (!cancelled) setLocationLabel("");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, result.coordinates?.lat, result.coordinates?.lon]);

  useEffect(() => {
    const name = result.project_name || input?.project_name || "Project";
    const where =
      locationLabel ||
      (result.coordinates
        ? `${result.coordinates.lat.toFixed(3)}°, ${result.coordinates.lon.toFixed(3)}°`
        : "");
    document.title = where ? `${name} · ${where} — ${COMPANY_NAME}` : `${name} — ${COMPANY_NAME}`;
  }, [result.project_name, input?.project_name, locationLabel, result.coordinates]);

  useEffect(() => {
    if (initialTopo && boundaries.length && !topoMesh) {
      void fetchTopoMesh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
    // Wait for SiteIQ GIS so TerrainIQ can clip to the buildable area (red zones omitted).
    if (gisBusy) return;
    topoAutoRan.current = true;
    void handleRunTopo();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeStage, topoPayload, topoResult, topoBusy, gisBusy]);

  useEffect(() => {
    if (initialTopo) onWorkflowDepth?.("topo");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function proceedToTopo() {
    setActiveStage("topo");
    onWorkflowDepth?.("topo");
    onWorkflowPersist?.({ lastStage: "topo", topo: topoResult, finalScore, gisSetbacks: Object.keys(gisSetbacks).length ? gisSetbacks : null });
    autoSaveWorkflow("topo");
  }

  function proceedToLayout() {
    setActiveStage("layout");
    onWorkflowDepth?.("layout");
    onWorkflowPersist?.({ lastStage: "layout", topo: topoResult, finalScore, gisSetbacks: Object.keys(gisSetbacks).length ? gisSetbacks : null });
    autoSaveWorkflow("layout");
  }

  function proceedToYield() {
    setActiveStage("yield");
    onWorkflowDepth?.("yield");
    onWorkflowPersist?.({ lastStage: "yield", topo: topoResult, finalScore, gisSetbacks: Object.keys(gisSetbacks).length ? gisSetbacks : null });
    autoSaveWorkflow("yield");
  }

  function goBackStage() {
    if (activeStage === "topo") setActiveStage("screen");
    else if (activeStage === "layout") setActiveStage("topo");
    else if (activeStage === "yield") setActiveStage("layout");
    else onEditInput();
  }

  const backLabel =
    activeStage === "topo"
      ? "← Back to SiteIQ"
      : activeStage === "layout"
        ? "← Back to TerrainIQ"
        : activeStage === "yield"
          ? "← Back to LayoutIQ"
          : "← Edit input";

  function renderStageBar(proceed: ReactNode, leftHint?: ReactNode) {
    const saveError =
      saveMsg.includes("failed") ||
      saveMsg.includes("expired") ||
      saveMsg.includes("Network");
    return (
      <div className="stage-proceed-bar stage-proceed-bar-split">
        <button className="btn btn-ghost" type="button" onClick={goBackStage}>
          {backLabel}
        </button>
        {leftHint ?? null}
        <div className="stage-proceed-right">
          <button
            className="btn btn-ghost"
            type="button"
            onClick={() => void handleSaveProject()}
            disabled={saveBusy || !input}
            title="Save progress and resume later from My projects"
          >
            {saveBusy ? "Saving…" : "Save project"}
          </button>
          {proceed}
        </div>
        {saveMsg ? (
          <p className={`stage-save-msg${saveError ? " save-error" : ""}`}>{saveMsg}</p>
        ) : null}
      </div>
    );
  }

  async function handleTopoPdf() {
    if (!topoPayload) return;
    setTopoPdfBusy(true);
    setTopoError("");
    try {
      const blob = await topoReportPdf(token, topoPayload);
      const safe = (topoPayload.project_name || "terrainiq").replace(/\s+/g, "_");
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
      const safe = (topoPayload.project_name || "terrainiq").replace(/\s+/g, "_");
      saveBlob(blob, `${safe}_terrainiq_exports.zip`);
    } catch (err) {
      setTopoError(err instanceof Error ? err.message : "CAD ZIP failed");
    } finally {
      setTopoZipBusy(false);
    }
  }

  async function runYieldAnalysis() {
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

  useEffect(() => {
    if (activeStage !== "yield") {
      yieldAutoRan.current = false;
      return;
    }
    if (yieldAutoRan.current || yieldResult || yieldBusy || !selectedLayoutRow) return;
    yieldAutoRan.current = true;
    void runYieldAnalysis();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeStage, selectedLayoutRow, yieldResult, yieldBusy]);

  async function handleLayoutSweep() {
    if (!hasBoundary) return;
    const inputError = layoutInputError();
    if (inputError) {
      setActiveStage("layout");
      setLayoutError(inputError);
      return;
    }
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
        mount_filter: mountFilter,
        ...(layoutPortrait !== "all" ? { portrait_filter: [Number(layoutPortrait)] } : {}),
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
      setTerrain3D(
        await workflowTerrainMesh(token, {
          boundaries,
          grid_m: 10,
          max_vertices: 24000,
          mask_geojson: buildableMask,
        }),
      );
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

  const mountFilter: "all" | "fixed" | "sat" =
    layoutMountType === "Single-Axis Tracker" ? "sat" : "fixed";

  const azimuthSelectValue =
    azimuthCustom
      ? "custom"
      : mountFilter === "fixed" && azimuthDeg === 180
        ? "optimal"
        : String(azimuthDeg);

  const overallScore = finalScore?.pvmath_score;
  const overallReady = overallScore != null;
  const topoGridTooLarge = topoError ? isTopoGridTooLarge(topoError) : false;

  function renderModuleRunning(title: string, detail: string) {
    return (
      <div className="module-running">
        <div className="processing-spinner" aria-hidden />
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
    );
  }

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

  function renderTerrainDrivers(topo: TerrainIQAnalyzeResponse) {
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

  function renderSlopeAnalysisTable(topo: TerrainIQAnalyzeResponse) {
    const bins = Array.isArray(topo.slope.bins) ? topo.slope.bins : null;
    const ex = (topo.extras ?? {}) as Record<string, unknown>;
    const crMean = typeof ex.cross_row_mean === "number" ? ex.cross_row_mean : null;
    const crP95 = typeof ex.cross_row_p95 === "number" ? ex.cross_row_p95 : null;
    const classes: { label: string; color: string; pct: number | null }[] = [
      { label: "0 – 2.5% (excellent)", color: "#1b8a3a", pct: bins?.[0] ?? null },
      { label: "2.5 – 5% (very good)", color: "#5fae3a", pct: bins?.[1] ?? null },
      { label: "5 – 7.5% (acceptable)", color: "#8bc34a", pct: bins?.[2] ?? null },
      { label: "7.5 – 10% (challenging)", color: "#f5a623", pct: bins?.[3] ?? null },
      { label: "> 10% (critical)", color: "#d0021b", pct: bins?.[4] ?? null },
    ];
    return (
      <div className="slope-analysis-table">
        <div className="terrain-drivers-head">
          <span className="terrain-drivers-tag">Slope distribution</span>
        </div>
        <table className="slope-dist-table">
          <thead>
            <tr>
              <th>Slope class</th>
              <th>Area</th>
            </tr>
          </thead>
          <tbody>
            {classes.map((c) => (
              <tr key={c.label}>
                <td>
                  <span className="slope-dist-swatch" style={{ background: c.color }} />
                  {c.label}
                </td>
                <td className="slope-dist-pct">
                  {c.pct != null ? `${c.pct.toFixed(1)}%` : "—"}
                  {c.pct != null ? (
                    <span className="slope-dist-bar">
                      <span
                        className="slope-dist-bar-fill"
                        style={{ width: `${Math.min(100, c.pct)}%`, background: c.color }}
                      />
                    </span>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <table className="slope-summary-table">
          <tbody>
            <tr>
              <th>Mean slope</th>
              <td>{topo.slope.mean.toFixed(1)}%</td>
            </tr>
            <tr>
              <th>Max slope</th>
              <td>{topo.slope.max.toFixed(1)}%</td>
            </tr>
            <tr>
              <th>Area &gt; 5%</th>
              <td>{topo.slope.pct_over5.toFixed(1)}%</td>
            </tr>
            <tr>
              <th>Area &gt; 10%</th>
              <td>{topo.slope.pct_over10.toFixed(1)}%</td>
            </tr>
            {crMean !== null ? (
              <tr>
                <th>Cross-row mean</th>
                <td>{crMean.toFixed(1)}%</td>
              </tr>
            ) : null}
            {crP95 !== null ? (
              <tr>
                <th>Cross-row 95th pctile</th>
                <td>{crP95.toFixed(1)}%</td>
              </tr>
            ) : null}
            <tr>
              <th>Elevation range</th>
              <td>
                {topo.elevation.z_min.toFixed(0)}–{topo.elevation.z_max.toFixed(0)} m (
                {topo.elevation.z_range.toFixed(0)} m)
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    );
  }

  function renderSlopeMap() {
    if (!topoResult) return null;
    const terrainSrc = topoResult.terrain_source_used || "Routed public DEM";
    const disclaimer =
      typeof topoResult.terrain_source?.disclaimer === "string"
        ? topoResult.terrain_source.disclaimer
        : topoResult.disclaimer || "";
    return (
      <div className="slope-section">
        <div className="slope-section-head">
          <span className="terrain-drivers-tag">Slope map · top view</span>
          <span className="slope-map-legend">
            {topoResult.grid_m_used.toFixed(0)} m grid · {terrainSrc}
            {topoMesh ? ` · ${topoMesh.vertices.length.toLocaleString()} points` : ""}
          </span>
        </div>
        <div className="slope-section-grid">
          <div className="slope-section-map">
            {topoMesh ? (
              <SlopeTopMap
                mesh={topoMesh}
                boundaries={boundaries}
                excludedGeoJson={gisResult?.excluded_area_geojson ?? null}
                height={420}
              />
            ) : topoMeshBusy ? (
              <p className="hint">Rendering high-resolution slope terrain…</p>
            ) : (
              <p className="hint">Slope terrain unavailable for this boundary.</p>
            )}
          </div>
          {renderSlopeAnalysisTable(topoResult)}
        </div>
        {disclaimer ? <p className="module-note slope-source-note">{disclaimer}</p> : null}
        {buildableMask ? (
          <p className="module-note slope-source-note">
            Slope analysis is clipped to the SiteIQ <strong>buildable area</strong> — building, road
            and water setback zones (red on SiteIQ) are excluded.
          </p>
        ) : null}
        <p className="module-note slope-source-note">
          Data sources: {terrainSrc} · PVGIS (JRC) for solar · OpenStreetMap for GIS constraints.
          Output grid is resampled for layout screening — not LiDAR-grade survey data.
        </p>
      </div>
    );
  }

  return (
    <div
      className={`workflow-page results-shell${
        activeStage === "screen" ? " results-shell-full" : ""
      }`}
      style={
        activeStage === "screen"
          ? undefined
          : ({ "--results-sb-w": `${sidebarWidth}px` } as React.CSSProperties)
      }
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
          <h3>TerrainIQ</h3>
          {!hasBoundary ? (
            <p className="hint sidebar-hint">
              Add a site boundary on Project input to enable terrain analysis.
            </p>
          ) : (
            <>
              <details className="sidebar-advanced" open>
                <summary>Terrain settings</summary>
                <div className="field">
                  <label htmlFor="topo-grid-m">Grid resolution</label>
                  <select
                    id="topo-grid-m"
                    value={topoGridM}
                    onChange={(e) => setTopoGridM(Number(e.target.value))}
                  >
                    <option value={3}>3 m — highest detail (small sites)</option>
                    <option value={5}>5 m — high detail (default)</option>
                    <option value={10}>10 m — balanced</option>
                    <option value={20}>20 m — fast (large sites)</option>
                    <option value={30}>30 m — coarse overview</option>
                  </select>
                </div>
                <label className="checkbox-field layout-bifacial">
                  <input
                    type="checkbox"
                    checked={topoAllowCoarsen}
                    onChange={(e) => setTopoAllowCoarsen(e.target.checked)}
                  />
                  Auto-coarsen if the grid is too large
                </label>
                <p className="hint sidebar-hint">
                  Finer grids give more accurate slope but take longer. Change a setting, then
                  re-run.
                </p>
              </details>
              <button
                className="btn btn-primary btn-block"
                type="button"
                onClick={() => void handleRunTopo()}
                disabled={topoBusy}
              >
                {topoBusy ? "Running TerrainIQ…" : topoResult ? "Re-run TerrainIQ" : "Run TerrainIQ"}
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
                <label htmlFor="layout-mount-type">Mounting system</label>
                <select
                  id="layout-mount-type"
                  value={layoutMountType}
                  onChange={(e) => {
                    const next = e.target.value as "Fixed Tilt" | "Single-Axis Tracker";
                    setLayoutMountType(next);
                    setLayoutPortrait(next === "Single-Axis Tracker" ? "1" : "2");
                  }}
                >
                  <option value="Fixed Tilt">Fixed Tilt</option>
                  <option value="Single-Axis Tracker">Single-Axis Tracker</option>
                </select>
                <p className="hint sidebar-hint">
                  Choose here — SiteIQ and TerrainIQ run mount-agnostic; layout and yield use this
                  selection.
                </p>
              </div>
              <div className="field">
                <label htmlFor="layout-portrait">Modules in portrait (per table)</label>
                <select
                  id="layout-portrait"
                  value={layoutPortrait}
                  onChange={(e) =>
                    setLayoutPortrait(e.target.value as "all" | "1" | "2" | "3" | "4")
                  }
                >
                  {mountFilter === "sat" ? (
                    <>
                      <option value="1">1P — single row (lighter, faster)</option>
                      <option value="2">2P — stacked pair</option>
                      <option value="all">Compare 1P & 2P (slower)</option>
                    </>
                  ) : (
                    <>
                      <option value="1">1P — single row (lighter, faster)</option>
                      <option value="2">2P — two-high</option>
                      <option value="3">3P — three-high</option>
                      <option value="4">4P — four-high</option>
                      <option value="all">Compare 1P–4P (slower)</option>
                    </>
                  )}
                </select>
                <p className="hint sidebar-hint">
                  Pick one portrait to keep the sweep fast on large sites. Use Compare only when you
                  need to weigh portraits side by side.
                </p>
              </div>
              <div className="field">
                <label htmlFor="layout-row-align">Row alignment</label>
                <select
                  id="layout-row-align"
                  value={layoutRowAlignment}
                  onChange={(e) => setLayoutRowAlignment(e.target.value as RowAlignment)}
                >
                  <option value="horizontal">
                    Aligned — string-aligned grid (best buildability)
                  </option>
                  <option value="boundary">
                    Non-aligned — fill to the edge (max capacity)
                  </option>
                </select>
                <p className="hint sidebar-hint">
                  Aligned snaps every row to one shared string grid, so trackers line up
                  string-for-string across the whole field — clean, road-friendly, slightly lower
                  MWp. Non-aligned fills each pocket to its own edge for maximum capacity with
                  ragged, staggered ends.
                </p>
              </div>
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
              <div className="field">
                <label htmlFor="layout-azimuth">
                  {mountFilter === "sat" ? "Tracker axis azimuth" : "Array orientation"}
                </label>
                <select
                  id="layout-azimuth"
                  value={azimuthSelectValue}
                  onChange={(e) => {
                    const value = e.target.value;
                    if (value === "custom") {
                      setAzimuthCustom(true);
                      return;
                    }
                    setAzimuthCustom(false);
                    if (value === "optimal") {
                      setAzimuthDeg(180);
                      return;
                    }
                    setAzimuthDeg(Number(value));
                  }}
                >
                  {mountFilter === "fixed" ? (
                    <option value="optimal">Optimal tilt (due south · PVGIS)</option>
                  ) : (
                    <option value={180}>180° — N–S axis (default)</option>
                  )}
                  <option value={90}>90° — east</option>
                  <option value={135}>135° — south-east</option>
                  <option value={225}>225° — south-west</option>
                  <option value={270}>270° — west</option>
                  <option value="custom">Custom angle…</option>
                </select>
                {azimuthCustom ? (
                  <input
                    type="number"
                    className="layout-azimuth-custom"
                    min="0"
                    max="360"
                    step="1"
                    value={azimuthDeg}
                    placeholder="0–360°"
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      setAzimuthDeg(Math.min(360, Math.max(0, v || 0)));
                    }}
                  />
                ) : null}
                <p className="hint sidebar-hint">
                  {mountFilter === "sat"
                    ? "Trackers default to a North–South axis (rotating E→W). Pick a preset or enter a custom axis azimuth (0–360°) to align with the parcel."
                    : "Default uses PVGIS optimal tilt on a due-south array (180°). Choose another compass bearing or enter a custom azimuth for skewed parcels."}
                </p>
              </div>
              <details className="sidebar-advanced" open>
                <summary>Module, strings, trackers &amp; roads</summary>
                <div className="grid-2 layout-custom-row">
                  <div className="field">
                    <label htmlFor="out-module-wp">Module Wp</label>
                    <NumberField
                      id="out-module-wp"
                      min={200}
                      max={1000}
                      value={moduleWp}
                      onChange={setModuleWp}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="out-mps">Modules / string</label>
                    <NumberField
                      id="out-mps"
                      min={8}
                      max={50}
                      value={modulesPerString}
                      onChange={setModulesPerString}
                    />
                  </div>
                </div>
                <div className="grid-2 layout-custom-row">
                  <div className="field">
                    <label htmlFor="out-mod-h">Height (m)</label>
                    <NumberField
                      id="out-mod-h"
                      step="0.001"
                      value={moduleH}
                      onChange={setModuleH}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="out-mod-w">Width (m)</label>
                    <NumberField
                      id="out-mod-w"
                      step="0.001"
                      value={moduleW}
                      onChange={setModuleW}
                    />
                  </div>
                </div>
                {moduleHWarning ? (
                  <p className="field-warning">{moduleHWarning}</p>
                ) : null}
                {moduleWWarning ? (
                  <p className="field-warning">{moduleWWarning}</p>
                ) : null}
                <div className="field">
                  <label htmlFor="out-string-gap">String gap (m)</label>
                  <NumberField
                    id="out-string-gap"
                    step="0.05"
                    min={0}
                    value={interStringGap}
                    onChange={setInterStringGap}
                  />
                </div>
                {mountFilter !== "fixed" ? (
                  <>
                    <div className="grid-2 layout-custom-row">
                      <div className="field">
                        <label htmlFor="out-tracker-strings">Tracker strings</label>
                        <input
                          id="out-tracker-strings"
                          value={trackerStringOptions}
                          onChange={(e) => setTrackerStringOptions(e.target.value)}
                          placeholder="8,7,6,5,4,3,2,1"
                        />
                      </div>
                      <div className="field">
                        <label htmlFor="out-max-tracker">Max tracker m</label>
                        <NumberField
                          id="out-max-tracker"
                          min={20}
                          max={500}
                          value={maxTrackerLength}
                          onChange={setMaxTrackerLength}
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
                      <NumberField
                        id="out-slope-limit"
                        step="0.5"
                        min={0.5}
                        max={SLOPE_MAX_PCT}
                        value={trackerSlopeLimit}
                        onChange={setTrackerSlopeLimit}
                        disabled={!excludeTrackerSlope}
                      />
                    </div>
                    {slopeWarning ? (
                      <p className="field-warning">{slopeWarning}</p>
                    ) : null}
                  </>
                ) : null}
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
                      applyRoadPresetToState("sat_auto");
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
                  <p className="hint sidebar-hint">
                    Constant pitch; E-W gap after 50 columns (6 m); N-S gaps 0.6 + 5 m
                    after 16 full-width pitch bands.
                  </p>
                ) : (
                  <div className="field">
                    <label htmlFor="out-road-preset">Road preset</label>
                    <select
                      id="out-road-preset"
                      value={roadPreset}
                      onChange={(e) => {
                        const id = e.target.value;
                        setRoadPreset(id);
                        if (id === "no_roads") {
                          setRoadMode("off");
                        } else if (id === "sat_auto") {
                          setRoadMode("auto");
                        } else {
                          setRoadMode("manual");
                        }
                        if (id !== "custom") applyRoadPresetToState(id);
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
                {roadPreset === "custom" || roadMode === "auto" ? (
                  <>
                    <p className="hint sidebar-hint">
                      PVCase-style: trackers at constant pitch; E-W gap after N columns; at the
                      north end of each block, first then second N-S gap before the next band row.
                    </p>
                    <div className="grid-2 layout-custom-row">
                      <div className="field">
                        <label htmlFor="out-cols-block">Columns before E-W gap</label>
                        <NumberField
                          id="out-cols-block"
                          min={0}
                          value={colsPerBlock}
                          onChange={setColsPerBlock}
                          disabled={roadMode === "auto"}
                        />
                      </div>
                      <div className="field">
                        <label htmlFor="out-ew-gap">E-W gap / road (m)</label>
                        <NumberField
                          id="out-ew-gap"
                          step="0.5"
                          min={0}
                          value={ewGapM}
                          onChange={setEwGapM}
                          disabled={roadMode === "auto"}
                        />
                      </div>
                    </div>
                    <div className="field">
                      <label htmlFor="out-rows-block">Pitch bands before N-S road</label>
                      <NumberField
                        id="out-rows-block"
                        min={0}
                        value={rowsPerBlock}
                        onChange={setRowsPerBlock}
                        disabled={roadMode === "auto"}
                      />
                    </div>
                    <div className="grid-2 layout-custom-row">
                      <div className="field">
                        <label htmlFor="out-ns-gap-1">First N-S gap (m)</label>
                        <NumberField
                          id="out-ns-gap-1"
                          step="0.1"
                          min={0}
                          value={nsGap1M}
                          onChange={setNsGap1M}
                          disabled={roadMode === "auto"}
                        />
                      </div>
                      <div className="field">
                        <label htmlFor="out-block-gap">Second N-S gap / road (m)</label>
                        <NumberField
                          id="out-block-gap"
                          step="0.5"
                          min={0}
                          value={blockGapM}
                          onChange={setBlockGapM}
                          disabled={roadMode === "auto"}
                        />
                      </div>
                    </div>
                    <p className="hint sidebar-hint">
                      Set columns or pitch bands to 0 to skip that road type. Gaps snap to whole
                      pitch slots so tracker spacing stays on-grid.
                    </p>
                  </>
                ) : roadPreset !== "no_roads" ? (
                  <p className="hint sidebar-hint">
                    {colsPerBlock > 0
                      ? `E-W: ${colsPerBlock} columns → ${ewGapM} m gap. `
                      : ""}
                    {rowsPerBlock > 0
                      ? `N-S: ${rowsPerBlock} bands → ${nsGap1M} + ${blockGapM} m gaps.`
                      : ""}
                  </p>
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
              <label className="checkbox-field layout-bifacial">
                <input
                  type="checkbox"
                  checked={allowPartialStrings}
                  onChange={(e) => setAllowPartialStrings(e.target.checked)}
                />
                Allow half-strings at row ends
              </label>
              <p className="hint sidebar-hint">
                When off, layout stops at the last complete string (no clipped tables at parcel
                edges). When on, places a partial string if at least half a string fits (e.g. 14 of
                28 modules).
              </p>
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
          {yieldBusy && !yieldResult ? (
            <p className="hint sidebar-hint">Running YieldIQ automatically…</p>
          ) : null}
          <button
            className="btn btn-primary btn-block"
            type="button"
            onClick={() => void runYieldAnalysis()}
            disabled={yieldBusy || !selectedLayoutRow}
          >
            {yieldBusy ? "Running YieldIQ…" : yieldResult ? "Re-run YieldIQ" : "Run YieldIQ"}
          </button>
        </div>

        {yieldResult ? (
        <>
        <div className="sidebar-group sidebar-deliverables">
          <h3>Project deliverables</h3>
          <p className="hint sidebar-hint">
            PVMath report combines SiteIQ, TerrainIQ, LayoutIQ, and YieldIQ. Project package adds A3 layout sheet, BOM CSV, and DXF.
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
          {exportError ? <div className="error-banner">{exportError}</div> : null}
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
              Complete TerrainIQ to compute the overall PVMath score.
            </p>
          )}
        </div>
        </>
        ) : null}
        </>
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

      {activeStage !== "screen" ? (
        <div
          className="results-resizer"
          onPointerDown={startSidebarDrag}
          onDoubleClick={() => setSidebarWidth(SIDEBAR_DEFAULT)}
          role="separator"
          aria-orientation="vertical"
          title="Drag to resize · double-click to reset"
        />
      ) : null}

      <div className="results-main">
      {activeStage === "screen" ? (
      <div className="results-stage-header">
        <div>
          <h1>{result.project_name}</h1>
          {locationLabel ? <p className="results-location-label">{locationLabel}</p> : null}
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
        {(() => {
          const monthly = (result.solar as Record<string, unknown>)?.monthly_ghi;
          if (!Array.isArray(monthly) || monthly.length !== 12) return null;
          const vals = monthly.map((v) => Number(v) || 0);
          const dataMax = Math.max(...vals, 1);
          const annual = vals.reduce((s, v) => s + v, 0);
          const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

          // "Nice" axis maximum + tick step so the Y scale lands on round numbers.
          const niceCeil = (x: number) => {
            const exp = Math.floor(Math.log10(x));
            const base = Math.pow(10, exp);
            const f = x / base;
            const nf = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
            return nf * base;
          };
          const axisMax = niceCeil(dataMax);
          const TICKS = 4;
          const step = axisMax / TICKS;
          const ticks = Array.from({ length: TICKS + 1 }, (_, i) => axisMax - i * step);

          return (
            <div className="ghi-section">
              <h3 className="setup-subhead">Monthly GHI (kWh/m²)</h3>
              <div
                className="ghi-chart"
                role="img"
                aria-label={`Monthly global horizontal irradiation. Annual total ${annual.toFixed(0)} kilowatt hours per square metre.`}
              >
                <div className="ghi-yaxis">
                  <span className="ghi-yaxis-title">kWh/m²</span>
                  <div className="ghi-yaxis-ticks">
                    {ticks.map((t) => (
                      <span className="ghi-ytick" key={t}>
                        {t.toFixed(0)}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="ghi-plot">
                  <div className="ghi-gridlines">
                    {ticks.map((t) => (
                      <div className="ghi-gridline" key={t} />
                    ))}
                  </div>
                  <div className="ghi-bars">
                    {vals.map((val, i) => (
                      <div className="ghi-col" key={i}>
                        <div className="ghi-bar-track">
                          <span className="ghi-bar-value">{val.toFixed(0)}</span>
                          <div
                            className="ghi-bar"
                            style={{ height: `${(val / axisMax) * 100}%` }}
                            title={`${months[i]}: ${val.toFixed(0)} kWh/m²`}
                          />
                        </div>
                        <span className="ghi-xlabel">{months[i]}</span>
                      </div>
                    ))}
                  </div>
                  <span className="ghi-xaxis-title">Month</span>
                </div>
              </div>
              <p className="hint">
                Global horizontal irradiation per month at this location (PVGIS). Annual
                total ≈ {annual.toFixed(0)} kWh/m²/yr (sum of monthly values).
              </p>
            </div>
          );
        })()}
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
            {gisBusy && !gisResult
              ? renderModuleRunning(
                  "Detecting site constraints",
                  "Querying OpenStreetMap for roads, buildings, water, and transmission lines, then computing the buildable area. This can take up to a minute for large or dense sites.",
                )
              : null}
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
                    <strong>
                      {(useFullBoundary
                        ? scoreLandFromBuildablePct(100)
                        : scoreLandFromBuildablePct(gisResult.buildable_pct)) ?? "—"}/100
                    </strong>
                  </div>
                </div>
                <label className="checkbox-field gis-fullboundary-toggle">
                  <input
                    type="checkbox"
                    checked={useFullBoundary}
                    onChange={(e) => setUseFullBoundary(e.target.checked)}
                  />
                  Use full site boundary — ignore buildable exclusions in TerrainIQ & LayoutIQ
                </label>
                {useFullBoundary ? (
                  <p className="hint sidebar-hint">
                    Exclusions are shown below for reference but will <strong>not</strong> be
                    removed — TerrainIQ and LayoutIQ will use the entire {gisResult.site_area_ha} ha
                    boundary.
                  </p>
                ) : null}
                {gisResult.constraint_summary.length > 0 ? (
                  <>
                    <p className="hint gis-setback-hint">
                      Adjust setbacks below — buildable area and map update automatically.
                      {gisRecomputeBusy ? " Updating…" : null}
                    </p>
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
                            <td>
                              <label className="gis-setback-edit">
                                <input
                                  type="number"
                                  className="gis-setback-input"
                                  min={0}
                                  step={1}
                                  value={gisSetbacks[row.category] ?? row.setback_m}
                                  onChange={(e) => updateGisSetback(row.category, e.target.value)}
                                  disabled={gisBusy || gisRecomputeBusy}
                                  aria-label={`${row.label} setback metres`}
                                />
                                <span>m</span>
                              </label>
                            </td>
                            <td>{row.excluded_ha} ha</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </>
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
        {renderStageBar(
          <button className="btn btn-primary" type="button" onClick={proceedToTopo}>
            Proceed to TerrainIQ →
          </button>,
        )}
      </section>
      ) : null}

      {activeStage === "topo" ? (
      <section className="module-card module-terrainiq">
        <div className="module-head">
          <h2>TerrainIQ</h2>
          <span className="module-tag">Step 2 · authoritative terrain</span>
        </div>
        {!hasBoundary ? (
          <p className="hint">
            Draw or upload a site boundary on Project input. Terrain slope and the PVMath
            terrain score come only from TerrainIQ — not from site screening.
          </p>
        ) : (
          <>
            {topoBusy && !topoResult ? (
              renderModuleRunning(
                "Running TerrainIQ terrain analysis",
                "Fetching the public DEM, building the grid, and computing slope across your buildable area.",
              )
            ) : !topoResult ? (
              <p className="hint">TerrainIQ runs automatically when you open this step.</p>
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
                {renderSlopeMap()}
                {renderTerrainDrivers(topoResult)}
              </>
            ) : null}
          </>
        )}
        {topoError ? <div className="error-banner">{topoError}</div> : null}
        {renderTopoRecovery()}
        {exportError ? <div className="error-banner">{exportError}</div> : null}
        {renderStageBar(
          <button
            className="btn btn-primary"
            type="button"
            onClick={proceedToLayout}
            disabled={!hasBoundary}
          >
            {topoResult ? "Proceed to LayoutIQ →" : "Continue without terrain →"}
          </button>,
          topoError && !topoResult ? (
            <p className="hint stage-proceed-hint">
              You can continue to LayoutIQ without terrain — the PVMath score will be incomplete until
              TerrainIQ succeeds.
            </p>
          ) : null,
        )}
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
              {(() => {
                const mountLabel =
                  mountFilter === "sat" ? "Single-Axis Tracker" : "Fixed Tilt";
                const portraitLabel =
                  layoutPortrait === "all"
                    ? mountFilter === "sat"
                      ? "1P & 2P"
                      : "1P–4P"
                    : `${layoutPortrait}P`;
                return `Showing the layout sweep for ${mountLabel} (${portraitLabel}) — set Mounting and portrait in the LayoutIQ panel on the left.`;
              })()}
            </p>
            {!topoResult ? (
              <p className="module-note">TerrainIQ should finish first — layout uses your boundary polygon.</p>
            ) : null}
            {!layoutSweep && !layoutBusy ? (
              <div className="layout-cta">
                <strong>Next step:</strong> open the <em>LayoutIQ</em> panel on the left and press{" "}
                <strong>“Run layout sweep”</strong>. PVMath will pack {input?.mount_type || "your"} rows
                across the buildable area and compare capacity at each row pitch.
                <div className="layout-cta-actions">
                  <button
                    className="btn btn-primary btn-sm"
                    type="button"
                    onClick={() => void handleLayoutSweep()}
                    disabled={layoutBusy}
                  >
                    Run layout sweep
                  </button>
                </div>
              </div>
            ) : null}
            {layoutBusy
              ? renderModuleRunning(
                  "Running LayoutIQ sweep",
                  "Packing strings and tracker rows across the buildable area at each pitch/GCR step.",
                )
              : null}
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
                {layoutFilter !== "all" ? (
                  <p className="module-note layout-rec-explain">
                    <strong>Rec.</strong> = PVMath's techno-economic pick — the row spacing that
                    balances energy yield (less row-to-row shading), O&amp;M access, and capacity.
                    It is <em>not</em> the maximum MWp: tighter pitch packs more MWp but increases
                    shading losses and narrows the maintenance corridor. Pick a higher-GCR row if you
                    want maximum capacity, or the Rec. row for the best yield/access balance.
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
                          Preview: {layoutDetail.total_rows.toLocaleString()} rows ·{" "}
                          {layoutDetail.total_modules.toLocaleString()} modules (blue strings on
                          buildable parcel outline).
                        </p>
                      </>
                    ) : layoutDetailBusy ? (
                      renderModuleRunning(
                        "Generating layout preview",
                        "Packing strings across the buildable parcel and rendering the row geometry.",
                      )
                    ) : (
                      <p className="module-note">
                        Select a row or press Refresh preview.
                      </p>
                    )}
                    {terrain3D ? (
                      <>
        <Terrain3DView
                          mesh={terrain3D}
                          layoutGeoJson={layoutDetail?.geojson ?? null}
                          projectName={result.project_name || input?.project_name || "SiteIQ"}
                          mountType={layoutMountType === "Single-Axis Tracker" ? "tracker" : "fixed"}
                        />
                        <p className="module-note">
                          3D preview of the selected {mountFilter === "sat" ? "tracker" : "fixed-tilt"}{" "}
                          layout on the TerrainIQ DEM ({terrain3D.terrain_source_used}). Use Export GLB
                          for external 3D tools.
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
        {renderStageBar(
          <button
            className="btn btn-primary"
            type="button"
            onClick={proceedToYield}
            disabled={!selectedLayoutRow}
          >
            Proceed to YieldIQ →
          </button>,
        )}
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
            {selectedLayoutRow.gcr.toFixed(2)}, and {selectedLayoutRow.dc_kwp?.toLocaleString(undefined, {
              maximumFractionDigits: 3,
            })}{" "}
            kWp DC from LayoutIQ.
            {yieldBusy ? " Running YieldIQ…" : yieldResult ? "" : " YieldIQ runs automatically when you open this step."}
          </p>
        ) : (
          <p className="hint">Select a LayoutIQ row to run yield for that configuration.</p>
        )}
        {yieldResult ? (
          <YieldResultsPanel
            result={yieldResult}
            selectedConfigKey={selectedYieldConfigKey}
            selectedDcKwp={selectedLayoutRow?.dc_kwp ?? null}
            mountFilter={mountFilter}
            layoutGeoJson={layoutDetail?.geojson ?? null}
          />
        ) : yieldBusy ? (
          renderModuleRunning(
            "Running YieldIQ",
            "Querying PVGIS for plane-of-array irradiance and computing specific yield for your configuration.",
          )
        ) : null}
        {yieldError ? <div className="error-banner">{yieldError}</div> : null}
        {renderStageBar(<span />)}
      </section>
      ) : null}

      <p className="disclaimer footer-note">
        Screening-grade only — not bankable. Terrain from TerrainIQ grid only. Data: PVGIS (JRC),
        routed public DEM, OpenStreetMap.
      </p>
      </div>
    </div>
  );
}
