import { useEffect, useMemo, useState } from "react";
import {
  workflowEquipmentList,
  workflowEquipmentSearch,
  workflowLayoutElectrical,
} from "../lib/api";
import type { WorkflowLayoutDetailRequest } from "../types/workflow";
import type {
  ElectricalResult,
  ElectricalScreeningConfig,
  EquipmentSearchHit,
} from "../types/electrical";
import {
  DEFAULT_ELECTRICAL_INVERTER_CENTRAL,
  defaultInverterForMount,
} from "../types/electrical";

type Props = {
  token: string;
  mountType: string;
  moduleName: string;
  lat?: number;
  disabled?: boolean;
  calculateDisabled?: boolean;
  layoutPayload: WorkflowLayoutDetailRequest | null;
  value: ElectricalScreeningConfig;
  onChange: (next: ElectricalScreeningConfig) => void;
  onResult?: (result: ElectricalResult | null) => void;
};

export function ElectricalConfigPanel({
  token,
  mountType,
  moduleName,
  lat,
  disabled,
  calculateDisabled,
  layoutPayload,
  value,
  onChange,
  onResult,
}: Props) {
  const [open, setOpen] = useState(true);
  const [inverters, setInverters] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ElectricalResult | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchHits, setSearchHits] = useState<EquipmentSearchHit[]>([]);
  const [searchBusy, setSearchBusy] = useState(false);

  const inverterDefault = useMemo(() => defaultInverterForMount(mountType), [mountType]);
  const inverterName =
    value.electrical_inverter ||
    (inverterDefault.includes("Sungrow") ? DEFAULT_ELECTRICAL_INVERTER_CENTRAL : inverterDefault);
  const isCentral =
    inverterName.toLowerCase().includes("sungrow") ||
    inverterName.toLowerCase().includes("goodwe");

  useEffect(() => {
    workflowEquipmentList(token)
      .then((data) => setInverters(data.inverters))
      .catch(() => {
        /* curated fallbacks only */
      });
  }, [token]);

  useEffect(() => {
    setResult(null);
    onResult?.(null);
  }, [moduleName, layoutPayload?.config_key, layoutPayload?.pitch_m]);

  async function handleCalculate() {
    if (!layoutPayload) {
      setError("Run layout sweep and select a pitch row first.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const resp = await workflowLayoutElectrical(token, {
        ...layoutPayload,
        lat,
        electrical_module: moduleName,
        electrical_inverter: inverterName,
        system_voltage_v: value.system_voltage_v ?? 1500,
        electrical_dc_ac_ratio: value.electrical_dc_ac_ratio ?? 1.2,
        strings_per_combiner: value.strings_per_combiner ?? 12,
        tmy_t2m: value.tmy_t2m,
      });
      setResult(resp.electrical);
      onResult?.(resp.electrical);
      if (resp.warnings?.length) {
        setError(resp.warnings.join(" "));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Electrical calculation failed");
      setResult(null);
      onResult?.(null);
    } finally {
      setBusy(false);
    }
  }

  async function runSearch() {
    if (!searchQuery.trim()) return;
    setSearchBusy(true);
    try {
      const resp = await workflowEquipmentSearch(token, "inverter", searchQuery.trim());
      setSearchHits(resp.results as unknown as EquipmentSearchHit[]);
    } catch {
      setSearchHits([]);
    } finally {
      setSearchBusy(false);
    }
  }

  function pickSearchHit(hit: EquipmentSearchHit) {
    onChange({ ...value, electrical_inverter: hit.name });
    setSearchOpen(false);
    setSearchHits([]);
    setSearchQuery("");
  }

  const eb = result?.electrical_bom;
  const stringSizing = result?.string_sizing as Record<string, unknown> | undefined;
  const vocMarginPct =
    eb?.voc_margin_pct ??
    (typeof stringSizing?.voc_margin_pct === "number" ? stringSizing.voc_margin_pct : undefined);
  const vocMarginLow =
    eb?.voc_margin_low === true || stringSizing?.voc_margin_low === true || (vocMarginPct != null && vocMarginPct < 3);
  const calcBlocked = calculateDisabled ?? !layoutPayload;

  return (
    <div className="sidebar-group electrical-panel">
      <button type="button" className="electrical-panel-toggle" onClick={() => setOpen((v) => !v)}>
        <h3>Inverter &amp; electrical</h3>
        <span>{open ? "−" : "+"}</span>
      </button>
      {open ? (
        <>
          <p className="hint sidebar-hint">
            Module is set above — shared for layout capacity and string sizing. Calculate runs after
            you pick a sweep row.
          </p>
          <div className="field">
            <label htmlFor="electrical-inverter">Inverter</label>
            <select
              id="electrical-inverter"
              value={inverterName}
              disabled={disabled}
              onChange={(e) => onChange({ ...value, electrical_inverter: e.target.value })}
            >
              {(inverters.length ? inverters : [inverterDefault]).map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={disabled}
              onClick={() => setSearchOpen(true)}
            >
              Search database…
            </button>
          </div>
          <div className="field">
            <label htmlFor="electrical-system-v">System voltage</label>
            <select
              id="electrical-system-v"
              value={String(value.system_voltage_v ?? 1500)}
              disabled={disabled}
              onChange={(e) => onChange({ ...value, system_voltage_v: Number(e.target.value) })}
            >
              <option value="1500">1500 V DC</option>
              <option value="1000">1000 V DC</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="electrical-dcac">DC:AC ratio</label>
            <input
              id="electrical-dcac"
              type="number"
              min={1}
              max={1.5}
              step={0.01}
              value={value.electrical_dc_ac_ratio ?? 1.2}
              disabled={disabled}
              onChange={(e) =>
                onChange({ ...value, electrical_dc_ac_ratio: Number(e.target.value) || 1.2 })
              }
            />
          </div>
          {isCentral ? (
            <div className="field">
              <label htmlFor="electrical-combiner">Strings per combiner</label>
              <input
                id="electrical-combiner"
                type="number"
                min={4}
                max={24}
                step={1}
                value={value.strings_per_combiner ?? 12}
                disabled={disabled}
                onChange={(e) =>
                  onChange({ ...value, strings_per_combiner: Number(e.target.value) || 12 })
                }
              />
            </div>
          ) : null}
          <button
            type="button"
            className="btn btn-ghost btn-block"
            disabled={disabled || busy || calcBlocked}
            onClick={() => void handleCalculate()}
          >
            {busy ? "Calculating…" : "Calculate electrical"}
          </button>
          {calcBlocked && !busy ? (
            <p className="hint sidebar-hint">Run layout sweep and select a row to calculate strings and cables.</p>
          ) : null}
          {error ? <p className="hint sidebar-hint error-text">{error}</p> : null}
          {eb ? (
            <div className="module-note electrical-summary">
              <strong>{eb.modules_per_string}</strong> modules/string ·{" "}
              <strong>{eb.total_strings?.toLocaleString()}</strong> strings ·{" "}
              <strong>{eb.inverter_count}</strong> inverters · DC:AC{" "}
              <strong>{eb.dc_ac_ratio}</strong>
              <br />
              String Voc max <strong>{eb.Voc_max_string_V} V</strong>
              {vocMarginPct != null ? (
                <>
                  {" "}
                  · Voc margin{" "}
                  <strong className={vocMarginLow ? "voc-margin-warn" : undefined}>
                    {vocMarginPct.toFixed(1)}%
                  </strong>
                  {vocMarginLow ? " (low — target ≥3%)" : ""}
                </>
              ) : null}
              {" · "}
              DC string cable <strong>{eb.dc_string_cable_mm2} mm²</strong>
              {eb.string_combiners ? (
                <>
                  {" "}
                  · Combiners <strong>{eb.string_combiners}</strong>
                </>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}
      {searchOpen ? (
        <div className="electrical-search-modal" role="dialog" aria-label="Inverter search">
          <div className="electrical-search-card">
            <h4>Search inverters (PVFree / CEC)</h4>
            <div className="electrical-search-row">
              <input
                type="search"
                placeholder="e.g. Sungrow, Huawei…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void runSearch();
                }}
              />
              <button type="button" className="btn btn-primary btn-sm" onClick={() => void runSearch()}>
                {searchBusy ? "…" : "Search"}
              </button>
            </div>
            <ul className="electrical-search-list">
              {searchHits.map((hit) => (
                <li key={hit.name}>
                  <button type="button" className="btn btn-ghost btn-sm btn-block" onClick={() => pickSearchHit(hit)}>
                    {hit.name}
                    {hit.Paco_kW ? ` · ${hit.Paco_kW} kW AC` : ""}
                  </button>
                </li>
              ))}
            </ul>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setSearchOpen(false)}>
              Close
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
