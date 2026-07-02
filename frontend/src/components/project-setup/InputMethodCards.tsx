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
    description: "Draw the project boundary on satellite imagery — recommended for all studies.",
    accuracy: "Full SiteIQ → TerrainIQ → LayoutIQ workflow",
  },
  {
    id: "kml",
    title: "Upload KML / KMZ",
    description: "Import parcel boundaries from Google Earth, QGIS, or CAD exports.",
    accuracy: "Survey-grade polygons",
    accept: ".kml,.kmz",
  },
];

interface Props {
  selected: InputMethod;
  onSelect: (method: InputMethod) => void;
}

export function InputMethodCards({ selected, onSelect }: Props) {
  return (
    <div className="input-method-grid input-method-grid-two">
      {INPUT_METHOD_OPTIONS.map((opt) => (
        <button
          key={opt.id}
          type="button"
          className={`input-method-card input-method-card-lg${selected === opt.id ? " active" : ""}${
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
