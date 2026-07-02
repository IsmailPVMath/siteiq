import { useEffect, useMemo, useState } from "react";
import { workflowEquipmentCurated, workflowEquipmentSearch } from "../lib/api";
import type {
  CuratedModuleLayoutSpec,
  EquipmentSearchHit,
} from "../types/electrical";
import { DEFAULT_ELECTRICAL_MODULE } from "../types/electrical";

type Props = {
  token: string;
  value: string;
  disabled?: boolean;
  onChange: (name: string, spec: CuratedModuleLayoutSpec | null) => void;
};

const FALLBACK_SPECS: CuratedModuleLayoutSpec[] = [
  {
    name: DEFAULT_ELECTRICAL_MODULE,
    Wp: 620,
    module_h_m: 2.278,
    module_w_m: 1.134,
    bifacial: true,
  },
];

export function PvModulePicker({ token, value, disabled, onChange }: Props) {
  const [specs, setSpecs] = useState<CuratedModuleLayoutSpec[]>(FALLBACK_SPECS);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchHits, setSearchHits] = useState<EquipmentSearchHit[]>([]);
  const [searchBusy, setSearchBusy] = useState(false);

  useEffect(() => {
    workflowEquipmentCurated(token)
      .then((data) => {
        if (data.modules?.length) setSpecs(data.modules);
      })
      .catch(() => {
        /* use fallback */
      });
  }, [token]);

  const selectedName = value || DEFAULT_ELECTRICAL_MODULE;
  const activeSpec = useMemo(
    () => specs.find((s) => s.name === selectedName) ?? specs[0] ?? null,
    [selectedName, specs],
  );

  function selectModule(name: string, spec: CuratedModuleLayoutSpec | null) {
    onChange(name, spec);
  }

  async function runSearch() {
    if (!searchQuery.trim()) return;
    setSearchBusy(true);
    try {
      const resp = await workflowEquipmentSearch(token, "module", searchQuery.trim());
      setSearchHits(resp.results as unknown as EquipmentSearchHit[]);
    } catch {
      setSearchHits([]);
    } finally {
      setSearchBusy(false);
    }
  }

  function pickSearchHit(hit: EquipmentSearchHit) {
    const known = specs.find((s) => s.name === hit.name);
    if (known) {
      selectModule(known.name, known);
    } else if (hit.Wp) {
      selectModule(hit.name, {
        name: hit.name,
        Wp: hit.Wp,
        module_h_m: 2.278,
        module_w_m: 1.134,
        bifacial: true,
      });
    } else {
      selectModule(hit.name, null);
    }
    setSearchOpen(false);
    setSearchHits([]);
    setSearchQuery("");
  }

  return (
    <div className="field pv-module-picker">
      <label htmlFor="pv-module-select">PV module</label>
      <select
        id="pv-module-select"
        value={selectedName}
        disabled={disabled}
        onChange={(e) => {
          const name = e.target.value;
          selectModule(name, specs.find((s) => s.name === name) ?? null);
        }}
      >
        {specs.map((m) => (
          <option key={m.name} value={m.name}>
            {m.name}
          </option>
        ))}
      </select>
      {activeSpec ? (
        <p className="module-note">
          {activeSpec.Wp} Wp · {activeSpec.module_h_m} × {activeSpec.module_w_m} m
          {activeSpec.bifacial ? " · bifacial" : ""}
        </p>
      ) : (
        <p className="hint sidebar-hint">Layout uses default dimensions until a curated module is selected.</p>
      )}
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        disabled={disabled}
        onClick={() => setSearchOpen(true)}
      >
        Search database…
      </button>
      {searchOpen ? (
        <div className="electrical-search-modal" role="dialog" aria-label="Module search">
          <div className="electrical-search-card">
            <h4>Search modules (PVFree / CEC)</h4>
            <div className="electrical-search-row">
              <input
                type="search"
                placeholder="e.g. Jinko, LONGi…"
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
                    {hit.Wp ? ` · ${hit.Wp} Wp` : ""}
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
