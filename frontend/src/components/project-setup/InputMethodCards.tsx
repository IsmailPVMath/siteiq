import type { InputMethod } from "../../types/projectSetup";

export const INPUT_METHOD_OPTIONS: {
  id: InputMethod;
  title: string;
  description: string;
  accuracy: string;
  disabled?: boolean;
  accept?: string;
}[] = [
  {
    id: "map",
    title: "Interactive map",
    description: "Draw the project boundary directly on satellite imagery.",
    accuracy: "Best for quick site selection",
  },
  {
    id: "kml",
    title: "Upload KML",
    description: "Import parcel boundaries from Google Earth or CAD exports.",
    accuracy: "Survey-grade polygons",
    accept: ".kml",
  },
  {
    id: "kmz",
    title: "Upload KMZ",
    description: "Compressed KML archive with multiple parcels.",
    accuracy: "Survey-grade polygons",
    accept: ".kmz",
  },
  {
    id: "geojson",
    title: "Upload GeoJSON",
    description: "Import vector boundaries from GIS workflows.",
    accuracy: "GIS-compatible",
    accept: ".geojson,.json",
  },
  {
    id: "shapefile",
    title: "Upload Shapefile",
    description: "Import .shp geometry from survey deliverables.",
    accuracy: "Coming soon",
    disabled: true,
  },
  {
    id: "paste",
    title: "Paste coordinates",
    description: "Enter lat/lon or paste a Google Maps link.",
    accuracy: "Pin-only or manual boundary",
  },
  {
    id: "import",
    title: "Import project",
    description: "Load an existing PVMath project as a template.",
    accuracy: "Future",
    disabled: true,
  },
];

interface Props {
  selected: InputMethod;
  onSelect: (method: InputMethod) => void;
}

export function InputMethodCards({ selected, onSelect }: Props) {
  return (
    <div className="input-method-grid">
      {INPUT_METHOD_OPTIONS.map((opt) => (
        <button
          key={opt.id}
          type="button"
          className={`input-method-card${selected === opt.id ? " active" : ""}${
            opt.disabled ? " disabled" : ""
          }`}
          disabled={opt.disabled}
          onClick={() => !opt.disabled && onSelect(opt.id)}
        >
          <span className="input-method-card-title">{opt.title}</span>
          <span className="input-method-card-desc">{opt.description}</span>
          <span className="input-method-card-acc">{opt.accuracy}</span>
        </button>
      ))}
    </div>
  );
}
