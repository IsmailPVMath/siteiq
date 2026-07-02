/** Public engineering help — mirrors pvmath_help.py (no proprietary formulas). */

export const GUIDE_BASE = "https://pvmath.com/guides";

export type TerrainHelpKey =
  | "cross_row"
  | "cross_row_p95"
  | "mean_slope";

export interface TerrainHelpTopic {
  title: string;
  slug: string;
  body: string;
}

export const TERRAIN_HELP: Record<TerrainHelpKey, TerrainHelpTopic> = {
  cross_row: {
    title: "Cross-row slope",
    slug: "mean-slope-vs-cross-row",
    body:
      "For single-axis trackers, rows run north–south. Cross-row slope is the terrain grade perpendicular to the rows (east–west) — how much the ground rises or falls as you move across a row.\n\n" +
      "This drives tracker structural clearance, drainage, and grading cost. A site can show a modest mean slope while cross-row grades still flag review zones.",
  },
  cross_row_p95: {
    title: "Cross-row 95th percentile",
    slug: "mean-slope-vs-cross-row",
    body:
      "The 95th percentile cross-row slope is the grade exceeded on only 5% of the site — a “worst typical” spot, not a single outlier cell.\n\n" +
      "Use it for tracker screening: if the mean looks flat but the 95th percentile is high, rolling terrain may still need localized grading or clearance review.",
  },
  mean_slope: {
    title: "Mean slope",
    slug: "mean-slope-vs-cross-row",
    body:
      "Average terrain gradient across all valid points inside your boundary. Good for overall constructability, but for single-axis trackers also check cross-row statistics — mean slope alone can miss rolling terrain.",
  },
};

export function guideUrl(slug: string): string {
  return `${GUIDE_BASE}/${slug}.html`;
}
