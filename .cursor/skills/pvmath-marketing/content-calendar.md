# PVMath content calendar — 12-week rotation

The content bot cycles `week_index = ISO_week % 12`. Each week = **2 LinkedIn posts** (Tue + Thu assignments).

| Wk | Pillar | Tue — LinkedIn | Thu — LinkedIn | Guide CTA |
|----|--------|----------------|----------------|-----------|
| 0 | Workflow | One Project Setup → three modules | Why screening before survey | screening-vs-survey |
| 1 | Terrain before LiDAR | KMZ to LandXML same day | TopoIQ before LiDAR budget | landxml-dxf-solar |
| 2 | Honest DEM | GLO-30 ~30 m native — say it | 5 m grid is layout output, not sensor | glo30-and-5m-grid |
| 3 | Tracker cross-row | Mean slope lies on rolling sites | Cross-row p95 for SAT clearance | mean-slope-vs-cross-row |
| 4 | CAD handoff | SITE_BOUNDARY in DXF + LandXML | US Survey Feet for US projects | landxml-dxf-solar |
| 5 | SiteIQ screening | Portfolio go/no-go without bankability | Flood flag ≠ FEMA — checklist item | siteiq-screening |
| 6 | YieldIQ config | SAT vs fixed at same GCR | PR and CF for early config choice | yieldiq-yield |
| 7 | Screening vs survey | When LiDAR is worth it | What screening cannot decide | screening-vs-survey |
| 8 | Regional DE | DACH screening workflow | EEG/regulatory as pointer not advice | siteiq-screening |
| 9 | Regional ES/IN | High-resource sites still need terrain | Yield comparison before PVsyst | yieldiq-yield |
| 10 | Case style | Problem → TopoIQ → LiDAR scoped | Problem → YieldIQ → config chosen | topoiq-metrics |
| 11 | Platform | From site to system — tagline deep dive | Knowledge Centre + Pro manual | index |

## Format rotation (Thu alternates)

Even ISO weeks: **LinkedIn technical**  
Odd ISO weeks: **LinkedIn + optional email snippet** (bot generates email variant on Thu odd weeks)

## Hashtag pool (pick 2–3)

`#GroundMountSolar` `#UtilityScale` `#SolarEPC` `#AgriPV` `#SolarDevelopment` `#RenewableEnergy` `#CivilEngineering`

## Market rotation for examples

`week_index % 4` → 0=DE, 1=ES, 2=IN, 3=GCC/US (use generic “utility-scale” if no local detail)
