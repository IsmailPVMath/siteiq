"""Brand constants and shared copy rules for PVMath marketing."""

from __future__ import annotations

from pvmath_brand import COMPANY_NAME, PRODUCT_NAME, TAGLINE

BRAND = {
    "name": COMPANY_NAME,
    "tagline": TAGLINE,
    "platform": PRODUCT_NAME,
    "product_name": PRODUCT_NAME,
    "founder": "Ismail Pasha",
    "app_url": "https://siteiq.pvmath.com",
    "website": "https://pvmath.com",
    "guides": "https://pvmath.com/guides/",
    "contact": "contact@pvmath.com",
}

BANNED_WORDS = (
    "revolutionary", "game-changing", "disruptive", "cutting-edge",
    "world-class", "unlock", "empower", "synergy",
)

AUDIENCES = {
    "epc": "Solar EPC companies",
    "developer": "Solar project developers",
    "land": "Land acquisition teams",
    "consultancy": "Engineering consultancies",
    "investor": "Investors evaluating solar opportunities",
    "utility": "Utility-scale solar professionals",
}

HASHTAG_POOLS = {
    "general": ["#GroundMountSolar", "#UtilityScale", "#SolarEPC", "#SolarDevelopment"],
    "terrain": ["#CivilEngineering", "#TerrainAnalysis", "#SolarEPC"],
    "yield": ["#SolarEnergy", "#RenewableEnergy", "#PVGIS"],
    "founder": ["#BuildInPublic", "#SolarEngineering", "#CleanTech"],
}

DISCLAIMER_SCREENING = (
    "Screening-grade only — confirm with survey and bankable studies before FEED."
)

TOPICS_RUN = (
    {
        "slug": "siteiq-solar-site-screening",
        "title": "SiteIQ solar site screening",
        "module": "SiteIQ",
        "audience": "developer",
        "category": "Product updates",
        "hashtags": HASHTAG_POOLS["general"],
    },
    {
        "slug": "topoiq-terrain-slope-analysis",
        "title": "TopoIQ terrain and slope analysis",
        "module": "TopoIQ",
        "audience": "epc",
        "category": "Terrain and GIS topics",
        "hashtags": HASHTAG_POOLS["terrain"],
    },
    {
        "slug": "yieldiq-preliminary-yield",
        "title": "YieldIQ preliminary yield assessment",
        "module": "YieldIQ",
        "audience": "consultancy",
        "category": "Yield analysis topics",
        "hashtags": HASHTAG_POOLS["yield"],
    },
    {
        "slug": "utility-scale-development-problems",
        "title": "Utility-scale solar development problems",
        "module": "Platform",
        "audience": "utility",
        "category": "Customer pain points",
        "hashtags": HASHTAG_POOLS["general"],
    },
    {
        "slug": "founder-build-in-public",
        "title": "PVMath founder build-in-public update",
        "module": "Platform",
        "audience": "developer",
        "category": "Founder journey",
        "hashtags": HASHTAG_POOLS["founder"],
    },
)
