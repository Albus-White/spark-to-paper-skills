from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any, Mapping, Sequence


SLIDE_TEMPLATE_LIBRARY_SCHEMA = "drawai.slide_template_library.v1"


def _card(
    *,
    id: str,
    name: str,
    category: str,
    scenario_tags: Sequence[str],
    visual_tags: Sequence[str],
    prompt_recipe: str,
    visual_keywords: Sequence[str],
    palette: Sequence[str],
    layout_archetypes: Sequence[str],
    text_density: str,
    source_policy: str,
    ip_safety: str = "",
    tests: Sequence[str] = (),
    reference_images: Sequence[Mapping[str, Any]] = (),
    sample_outputs: Sequence[str] = (),
    provenance: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    return {
        "schema": SLIDE_TEMPLATE_LIBRARY_SCHEMA,
        "id": id,
        "name": name,
        "category": category,
        "scenario_tags": list(scenario_tags),
        "visual_tags": list(visual_tags),
        "prompt_recipe": prompt_recipe,
        "visual_keywords": list(visual_keywords),
        "palette": list(palette),
        "layout_archetypes": list(layout_archetypes),
        "reference_images": [dict(item) for item in reference_images],
        "sample_outputs": list(sample_outputs),
        "tests": list(tests),
        "provenance": [dict(item) for item in provenance],
    }


TEMPLATE_CARD_LIBRARY: dict[str, dict[str, Any]] = {
    "modern_newspaper": _card(
        id="modern_newspaper",
        name="Modern Newspaper",
        category="editorial_media",
        scenario_tags=["briefing", "report", "news_explainer", "exec_summary"],
        visual_tags=["newspaper", "editorial", "serif", "columns"],
        prompt_recipe=(
            "Build the slide like a modern newspaper front page: a strong headline, compact deck, "
            "two or three disciplined columns, captioned evidence blocks, and a source note area."
        ),
        visual_keywords=["modern newspaper", "editorial columns", "serif headline", "caption strips"],
        palette=["warm white", "ink black", "muted red accent", "pale gray rules"],
        layout_archetypes=["front-page headline", "two-column analysis", "quote + evidence rail"],
        text_density="high",
        source_policy="Best when sources or notes exist; without sources, keep claims generic and label analysis as conceptual.",
        tests=["headline readable", "columns aligned", "no invented citations"],
    ),
    "sharp_minimal": _card(
        id="sharp_minimal",
        name="Sharp-edged Minimalism",
        category="business_technical",
        scenario_tags=["strategy", "product", "technical_overview", "board_summary"],
        visual_tags=["minimal", "sharp_edges", "negative_space", "precision"],
        prompt_recipe=(
            "Use a precise minimal slide system with hard edges, sparse but useful copy, "
            "large typographic hierarchy, and one crisp diagram or comparison structure."
        ),
        visual_keywords=["sharp-edged minimalism", "thin rules", "precise spacing", "hard-edged panels"],
        palette=["white", "charcoal", "electric blue accent"],
        layout_archetypes=["single conclusion + diagram", "three proof blocks", "minimal architecture map"],
        text_density="medium",
        source_policy="Use for prompt-only topics if the slide stays conceptual and avoids unsupported metrics.",
        tests=["not empty layout", "strong hierarchy", "3-5 useful Chinese bullets when language=zh"],
    ),
    "yellow_black_editorial": _card(
        id="yellow_black_editorial",
        name="Yellow x Black Editorial",
        category="editorial_media",
        scenario_tags=["opinion", "trend", "warning", "data_story"],
        visual_tags=["yellow_black", "high_contrast", "poster", "editorial"],
        prompt_recipe=(
            "Create a high-contrast editorial poster-slide with yellow and black tension, "
            "a bold conclusion, modular evidence bands, and restrained warning-style emphasis."
        ),
        visual_keywords=["yellow black editorial", "bold poster typography", "rule-based grid"],
        palette=["signal yellow", "black", "off-white", "small red accent"],
        layout_archetypes=["headline poster", "risk ladder", "callout matrix"],
        text_density="medium-high",
        source_policy="Do not imply verified risk levels or market facts unless provided.",
        tests=["contrast safe", "text not buried in yellow", "no fake rankings"],
    ),
    "manga_safe_learning": _card(
        id="manga_safe_learning",
        name="Manga-safe Learning",
        category="ip_safe_cartoon",
        scenario_tags=["course", "education", "children_learning", "explainer"],
        visual_tags=["manga_safe", "comic_panels", "friendly", "original_characters"],
        prompt_recipe=(
            "Use original classroom comic panels for learning: a friendly guide character, "
            "speech-bubble summaries, simple step cards, and clearly readable teaching text."
        ),
        visual_keywords=["original manga-inspired classroom", "comic panels", "friendly learning mascot"],
        palette=["soft blue", "cream", "light red accent", "ink outline"],
        layout_archetypes=["four-panel lesson", "teacher + board", "step-by-step comic explainer"],
        text_density="medium",
        source_policy="Use for concept teaching; examples are illustrative unless the user supplies source material.",
        ip_safety=(
            "No copyrighted manga/anime characters, no exact likeness, no franchise symbols, "
            "no copied costume, no trademarked props, no Doraemon-like bell, pocket, face ratio, or silhouette."
        ),
        tests=["original character", "no protected character likeness", "visible teaching text"],
    ),
    "studio_premium_mockup": _card(
        id="studio_premium_mockup",
        name="Studio Premium Mockup",
        category="product_marketing",
        scenario_tags=["product_launch", "pitch", "feature_overview", "brand_template"],
        visual_tags=["studio", "premium", "mockup", "keynote"],
        prompt_recipe=(
            "Frame the topic as a premium studio product mockup: a hero object or abstract product surface, "
            "feature cards, refined lighting, and concise launch-copy hierarchy."
        ),
        visual_keywords=["premium studio mockup", "soft controlled lighting", "product keynote"],
        palette=["warm gray", "black", "white", "one vivid accent"],
        layout_archetypes=["hero product + feature row", "mockup wall", "before/after feature reveal"],
        text_density="medium",
        source_policy="Avoid fake UI screens, logos, and product claims unless supplied.",
        tests=["premium finish", "no fake brand marks", "feature copy readable"],
    ),
    "retro_pop_art": _card(
        id="retro_pop_art",
        name="Retro Pop Art",
        category="trend_visual",
        scenario_tags=["campaign", "creative_brief", "concept_intro", "education"],
        visual_tags=["retro", "pop_art", "halftone", "bold_color"],
        prompt_recipe=(
            "Use retro pop-art energy with halftone texture, bold color blocking, kinetic labels, "
            "and a clear slide hierarchy rather than a decorative poster only."
        ),
        visual_keywords=["retro pop art", "halftone", "comic burst", "bold flat color"],
        palette=["red", "cyan", "yellow", "black", "white"],
        layout_archetypes=["poster headline + three bursts", "comic data callouts", "campaign storyboard"],
        text_density="medium",
        source_policy="Good for attention and education; factual claims still require supplied sources.",
        tests=["not cluttered", "main title readable", "comic texture behind text controlled"],
    ),
    "minimalist_clean": _card(
        id="minimalist_clean",
        name="Minimalist Clean",
        category="business_technical",
        scenario_tags=["business", "technical_overview", "exec_summary", "product"],
        visual_tags=["clean", "minimal", "white_space", "saas"],
        prompt_recipe=(
            "Create a clean modern PPT page with a concise takeaway, tidy content cards, "
            "one schematic diagram, and disciplined whitespace."
        ),
        visual_keywords=["minimalist clean", "white space", "modern SaaS", "simple cards"],
        palette=["white", "slate", "blue", "soft green"],
        layout_archetypes=["takeaway + 3 cards", "center workflow", "summary dashboard"],
        text_density="medium-high",
        source_policy="Works for prompt-only or source-grounded topics; omit unsupplied numbers.",
        tests=["Chinese dominant when language=zh", "not textless", "cards aligned"],
    ),
    "cyberpunk_neon": _card(
        id="cyberpunk_neon",
        name="Cyberpunk Neon",
        category="tech_ai_product",
        scenario_tags=["infrastructure", "cybersecurity", "ai_system", "developer_platform"],
        visual_tags=["cyberpunk", "neon", "dark", "network"],
        prompt_recipe=(
            "Use a dark neon infrastructure slide with glowing but readable system modules, "
            "control-plane topology, risk callouts, and high-contrast labels."
        ),
        visual_keywords=["cyberpunk neon", "dark infrastructure", "network topology", "glowing panels"],
        palette=["black", "deep violet", "cyan", "magenta", "acid green accent"],
        layout_archetypes=["control-plane map", "threat/risk dashboard", "layered system stack"],
        text_density="medium-high",
        source_policy="Never invent logs, IP addresses, incidents, benchmark scores, or live telemetry.",
        tests=["glow not over text", "no pseudo-terminal gibberish", "system labels readable"],
    ),
    "neo_brutalism": _card(
        id="neo_brutalism",
        name="Neo-Brutalism",
        category="trend_visual",
        scenario_tags=["bold_opinion", "workshop", "startup_pitch", "challenge"],
        visual_tags=["neo_brutalist", "blocky", "raw", "high_contrast"],
        prompt_recipe=(
            "Create a neo-brutalist slide with heavy borders, offset blocks, direct labels, "
            "and intentionally raw contrast while preserving PPT readability."
        ),
        visual_keywords=["neo-brutalism", "thick black borders", "offset blocks", "raw typography"],
        palette=["white", "black", "hot pink", "acid green", "electric blue"],
        layout_archetypes=["challenge wall", "blocky checklist", "opinion + counterpoint"],
        text_density="medium",
        source_policy="Use for conceptual framing; avoid pretending visual emphasis is factual evidence.",
        tests=["brutalist but organized", "no overlapping text", "not one-note decoration"],
    ),
    "acid_y2k": _card(
        id="acid_y2k",
        name="Acid Graphics Y2K",
        category="trend_visual",
        scenario_tags=["youth_campaign", "creative_recap", "trend_report", "future_culture"],
        visual_tags=["acid", "y2k", "chrome", "experimental"],
        prompt_recipe=(
            "Use acid Y2K graphics with chrome accents, expressive shapes, sticker-like modules, "
            "and one controlled content structure so the slide remains understandable."
        ),
        visual_keywords=["acid graphics", "Y2K chrome", "liquid shapes", "sticker modules"],
        palette=["lime", "silver", "purple", "black", "white"],
        layout_archetypes=["trend board", "sticker matrix", "future-culture map"],
        text_density="low-medium",
        source_policy="Best for mood and campaign decks; factual content must be short and source-safe.",
        tests=["text remains legible", "effects do not cover copy", "no random English filler"],
    ),
    "swiss_international": _card(
        id="swiss_international",
        name="Swiss International",
        category="business_technical",
        scenario_tags=["report", "research", "strategy", "technical_overview"],
        visual_tags=["swiss", "grid", "modernist", "typography"],
        prompt_recipe=(
            "Design the slide as a Swiss International grid: strict columns, asymmetric but rational layout, "
            "large title, numbered sections, and crisp diagram or evidence modules."
        ),
        visual_keywords=["Swiss International", "modular grid", "modernist typography", "rational alignment"],
        palette=["white", "black", "red accent", "cool gray"],
        layout_archetypes=["numbered grid sections", "large title + evidence columns", "timeline grid"],
        text_density="medium-high",
        source_policy="Strong default for serious reports; keep unsourced data abstract.",
        tests=["grid alignment visible", "typography hierarchy", "Chinese copy remains dominant"],
    ),
    "dark_editorial": _card(
        id="dark_editorial",
        name="Dark Editorial",
        category="editorial_media",
        scenario_tags=["thought_leadership", "research_intro", "premium_report", "tech_story"],
        visual_tags=["dark", "editorial", "cinematic", "magazine"],
        prompt_recipe=(
            "Create a dark editorial spread with one cinematic visual metaphor, high-contrast text blocks, "
            "a refined caption rail, and restrained premium atmosphere."
        ),
        visual_keywords=["dark editorial", "cinematic magazine spread", "premium caption rail"],
        palette=["near black", "warm white", "muted gold", "deep blue"],
        layout_archetypes=["feature spread", "chapter opener", "visual metaphor + sidebar"],
        text_density="medium",
        source_policy="Use metaphor for attention, not as evidence; concrete claims require sources.",
        tests=["dark contrast high", "metaphor supports topic", "no watermark-like microtext"],
    ),
    "design_blueprint": _card(
        id="design_blueprint",
        name="Design Blueprint",
        category="tech_ai_product",
        scenario_tags=["architecture", "process", "systems", "implementation_plan"],
        visual_tags=["blueprint", "diagram", "technical", "linework"],
        prompt_recipe=(
            "Use a design-blueprint slide language with measured linework, labelled modules, "
            "annotation pins, and implementation-step structure."
        ),
        visual_keywords=["technical blueprint", "grid paper", "annotation pins", "measured linework"],
        palette=["blueprint blue", "white", "cyan accent", "graph paper gray"],
        layout_archetypes=["architecture blueprint", "implementation sequence", "system annotation map"],
        text_density="medium-high",
        source_policy="Architecture can be schematic; named systems, APIs, and metrics must come from the user.",
        tests=["diagram labels readable", "no fake API names", "linework not too dense"],
    ),
    "aurora_ui": _card(
        id="aurora_ui",
        name="Aurora UI",
        category="tech_ai_product",
        scenario_tags=["ai_product", "workflow", "platform", "dashboard"],
        visual_tags=["aurora", "ui", "gradient", "soft_depth"],
        prompt_recipe=(
            "Use a polished Aurora UI slide with soft luminous gradients, layered product panels, "
            "workflow cards, and a clear Chinese explanatory headline."
        ),
        visual_keywords=["Aurora UI", "soft luminous gradient", "layered interface panels", "AI product"],
        palette=["deep navy", "cyan", "violet", "mint", "white"],
        layout_archetypes=["workflow UI panels", "platform overview", "capability dashboard"],
        text_density="medium",
        source_policy="Interface panels should be abstract unless the user supplies actual product screenshots.",
        tests=["not fake app screenshot", "Chinese title visible", "gradient does not obscure text"],
    ),
    "light_glassmorphism": _card(
        id="light_glassmorphism",
        name="Light Glassmorphism",
        category="tech_ai_product",
        scenario_tags=["dashboard", "product_overview", "brand_template", "metrics"],
        visual_tags=["glassmorphism", "light", "frosted", "cards"],
        prompt_recipe=(
            "Create a light glassmorphism slide with translucent panels over a subtle depth field, "
            "clean module cards, and enough contrast for OCR-readable slide text."
        ),
        visual_keywords=["light glassmorphism", "frosted panels", "translucent cards", "soft depth"],
        palette=["white", "ice blue", "soft purple", "graphite text"],
        layout_archetypes=["glass dashboard", "layered card system", "reference-style adaptation"],
        text_density="medium",
        source_policy="Good for reference-image style transfer; do not copy logos, UI screens, or proprietary marks.",
        tests=["panel contrast", "no copied reference content", "text readable through glass"],
    ),
    "frutiger_aero": _card(
        id="frutiger_aero",
        name="Frutiger Aero",
        category="trend_visual",
        scenario_tags=["education", "future_vision", "green_tech", "consumer_product"],
        visual_tags=["frutiger_aero", "glossy", "optimistic", "nature_tech"],
        prompt_recipe=(
            "Use Frutiger Aero cues with glossy translucent surfaces, fresh nature-tech optimism, "
            "clean bubbles, and simple explanatory modules."
        ),
        visual_keywords=["Frutiger Aero", "glossy bubbles", "fresh gradients", "nature technology"],
        palette=["sky blue", "leaf green", "white", "silver"],
        layout_archetypes=["optimistic explainer", "eco-tech dashboard", "learning flow"],
        text_density="low-medium",
        source_policy="Keep it conceptual unless environmental or product claims are supplied.",
        tests=["not outdated clutter", "readable Chinese labels", "no fake eco claims"],
    ),
    "course_clay": _card(
        id="course_clay",
        name="Course Clay",
        category="education_courseware",
        scenario_tags=["course", "training", "onboarding", "teaching"],
        visual_tags=["claymorphism", "friendly", "3d_icons", "learning"],
        prompt_recipe=(
            "Build a friendly courseware slide with soft clay-like 3D icons, a lesson objective, "
            "step cards, and a clear review/checkpoint area."
        ),
        visual_keywords=["soft clay courseware", "friendly 3D icons", "learning cards"],
        palette=["warm white", "pastel blue", "pastel green", "coral accent"],
        layout_archetypes=["lesson objective + steps", "concept/example/checkpoint", "learning path"],
        text_density="medium",
        source_policy="Examples should be generic unless supplied by the user.",
        tests=["teaches one idea", "low cognitive load", "checkpoint visible"],
    ),
    "corporate_strategy_cinematic": _card(
        id="corporate_strategy_cinematic",
        name="Corporate Strategy Cinematic",
        category="business_strategy",
        scenario_tags=["corporate_report", "strategy", "exec_summary", "transformation"],
        visual_tags=["cinematic", "consulting", "premium", "boardroom"],
        prompt_recipe=(
            "Create a premium corporate strategy slide with a board-level headline, "
            "decision logic, phased roadmap, and restrained cinematic depth."
        ),
        visual_keywords=["corporate strategy cinematic", "executive briefing", "premium boardroom"],
        palette=["deep navy", "white", "steel gray", "gold accent"],
        layout_archetypes=["executive takeaway + pillars", "transformation roadmap", "decision matrix"],
        text_density="high",
        source_policy="No invented market size, ROI, competitor rank, dates, or financial metrics.",
        tests=["board-level conclusion", "qualitative if no data", "decision structure visible"],
    ),
    "weekly_kanban": _card(
        id="weekly_kanban",
        name="Weekly Kanban",
        category="operations_report",
        scenario_tags=["weekly_report", "retrospective", "project_status", "team_update"],
        visual_tags=["kanban", "operations", "status", "cards"],
        prompt_recipe=(
            "Use a weekly-review Kanban structure with status lanes, blockers, decisions, "
            "next-week priorities, and compact operational copy."
        ),
        visual_keywords=["weekly kanban", "status lanes", "progress cards", "retrospective"],
        palette=["white", "slate", "blue", "amber", "green"],
        layout_archetypes=["done/doing/blocked/next", "weekly scorecard", "retro + action list"],
        text_density="high",
        source_policy="Use qualitative status unless the user supplies actual metrics or task lists.",
        tests=["lanes legible", "not a fake Jira screenshot", "next actions visible"],
    ),
    "sales_architectural": _card(
        id="sales_architectural",
        name="Sales Architectural",
        category="sales_business",
        scenario_tags=["sales", "business_development", "solution_pitch", "customer_value"],
        visual_tags=["architectural", "sales", "solution_map", "premium"],
        prompt_recipe=(
            "Create a sales solution slide like an architectural model: customer pain points, "
            "solution modules, value path, and implementation phases."
        ),
        visual_keywords=["sales architecture", "solution map", "architectural blocks", "value path"],
        palette=["white", "warm gray", "navy", "orange accent"],
        layout_archetypes=["customer pain -> solution -> value", "module building blocks", "sales roadmap"],
        text_density="medium-high",
        source_policy="Do not promise revenue lift, savings, or customer proof without supplied data.",
        tests=["value path clear", "no unsupported numbers", "solution blocks separable"],
    ),
}


SOURCE_AAAAAAAJ_SLIDES = {
    "source": "AAAAAAAJ/slides PROMPTS.md",
    "url": "https://github.com/AAAAAAAJ/slides/blob/main/PROMPTS.md",
    "use": "visual style seed; adapted into DrawAI TemplateCard fields",
}

SOURCE_NOTEBOOKLM_PROMPTS = {
    "source": "awesome-notebookLM-prompts",
    "url": "https://github.com/serenakeyitan/awesome-notebookLM-prompts",
    "use": "NotebookLM/Kael slide style collection; adapted into DrawAI TemplateCard fields",
}

SOURCE_PPT_MASTER = {
    "source": "ppt-master examples",
    "url": "https://github.com/hugohe3/ppt-master",
    "use": "example deck visual systems and spec/template-fill mindset; adapted for image-stage gallery",
}

SOURCE_NANO_BANANA_PPT = {
    "source": "nano-banana-ppt scene prompt collection",
    "url": "https://github.com/yaojingang/yao-open-prompts/blob/main/prompts/06-ai-content/nano-banana-ppt.md",
    "use": "high-frequency PPT scenarios and style-consistency rule; adapted into scenario cards",
}

SOURCE_HTML_TEMPLATE_FAMILY = {
    "source": "frontend-slides / beautiful-html-templates / html-ppt-skill family",
    "url": "https://github.com/search?q=beautiful-html-templates+html-ppt-skill+frontend-slides&type=repositories",
    "use": "HTML slide template/gallery idea, page-type families, theme-library coverage",
}


_INITIAL_CARD_PROVENANCE: dict[str, list[dict[str, Any]]] = {
    "modern_newspaper": [SOURCE_NOTEBOOKLM_PROMPTS],
    "sharp_minimal": [SOURCE_NOTEBOOKLM_PROMPTS, SOURCE_AAAAAAAJ_SLIDES],
    "yellow_black_editorial": [SOURCE_NOTEBOOKLM_PROMPTS],
    "manga_safe_learning": [SOURCE_NOTEBOOKLM_PROMPTS],
    "studio_premium_mockup": [SOURCE_NOTEBOOKLM_PROMPTS],
    "retro_pop_art": [SOURCE_AAAAAAAJ_SLIDES],
    "minimalist_clean": [SOURCE_AAAAAAAJ_SLIDES],
    "cyberpunk_neon": [SOURCE_AAAAAAAJ_SLIDES],
    "neo_brutalism": [SOURCE_AAAAAAAJ_SLIDES],
    "acid_y2k": [SOURCE_AAAAAAAJ_SLIDES],
    "swiss_international": [SOURCE_AAAAAAAJ_SLIDES],
    "dark_editorial": [SOURCE_AAAAAAAJ_SLIDES],
    "design_blueprint": [SOURCE_AAAAAAAJ_SLIDES],
    "aurora_ui": [SOURCE_AAAAAAAJ_SLIDES],
    "light_glassmorphism": [SOURCE_AAAAAAAJ_SLIDES],
    "frutiger_aero": [SOURCE_AAAAAAAJ_SLIDES],
    "course_clay": [SOURCE_NANO_BANANA_PPT],
    "corporate_strategy_cinematic": [SOURCE_NANO_BANANA_PPT, SOURCE_PPT_MASTER],
    "weekly_kanban": [SOURCE_NANO_BANANA_PPT],
    "sales_architectural": [SOURCE_NANO_BANANA_PPT],
}

for _card_id, _provenance in _INITIAL_CARD_PROVENANCE.items():
    if _card_id in TEMPLATE_CARD_LIBRARY and not TEMPLATE_CARD_LIBRARY[_card_id].get("provenance"):
        TEMPLATE_CARD_LIBRARY[_card_id]["provenance"] = [dict(item) for item in _provenance]


TEMPLATE_CARD_LIBRARY.update(
    {
        # AAAAAAAJ/slides: finish the 19-style coverage beyond the first seed set.
        "modern_minimal_pop": _card(
            id="modern_minimal_pop",
            name="Modern Minimal Pop",
            category="trend_visual",
            scenario_tags=["campaign", "social_product", "creative_intro", "education"],
            visual_tags=["pastel", "minimal_pop", "swiss_influence", "social_media"],
            prompt_recipe="Use pastel minimal-pop composition: clean Swiss-influenced structure, star bursts, tilted color blocks, and concise slide copy.",
            visual_keywords=["modern minimal pop", "pastel blocks", "star bursts", "Instagram-like clean composition"],
            palette=["mint", "cream", "coral", "soft purple", "black"],
            layout_archetypes=["pastel title board", "three metric blocks", "tilted feature cards"],
            text_density="medium",
            source_policy="Suitable for concept and campaign slides; all numeric claims must be supplied.",
            tests=["pastel but not washed out", "title readable", "not just decoration"],
            provenance=[SOURCE_AAAAAAAJ_SLIDES],
        ),
        "neo_brutalist_ui": _card(
            id="neo_brutalist_ui",
            name="Neo-Brutalist UI",
            category="trend_visual",
            scenario_tags=["dashboard", "startup_pitch", "product_ops", "youth_business"],
            visual_tags=["neo_brutalist", "ui", "thick_borders", "dashboard"],
            prompt_recipe="Build a card-based neo-brutalist UI dashboard with thick black outlines, hard shadows, pastel panels, and clear business labels.",
            visual_keywords=["neo-brutalist UI", "dashboard interface", "thick outlines", "hard shadows"],
            palette=["cream", "black", "mint", "yellow", "lavender"],
            layout_archetypes=["dashboard cards", "metric grid", "product operating panel"],
            text_density="medium-high",
            source_policy="Use qualitative UI modules unless real data or product screenshots are supplied.",
            tests=["dashboard structure clear", "no fake app UI", "borders do not crowd text"],
            provenance=[SOURCE_AAAAAAAJ_SLIDES],
        ),
        "y2k_pixel_retro": _card(
            id="y2k_pixel_retro",
            name="Y2K Pixel Retro",
            category="trend_visual",
            scenario_tags=["developer_culture", "history", "gamified_learning", "creative_report"],
            visual_tags=["pixel", "y2k", "retro_computing", "crt"],
            prompt_recipe="Use a 1990s/Y2K pixel-retro slide with CRT/computer motifs, pixel icons, bright accents, and readable modern PPT hierarchy.",
            visual_keywords=["Y2K pixel retro", "CRT monitor", "pixel icons", "vintage computer"],
            palette=["dark charcoal", "gold", "orange", "deep green", "cream"],
            layout_archetypes=["retro computer dashboard", "pixel timeline", "developer manifesto board"],
            text_density="low-medium",
            source_policy="Keep retro UI generic; no fake terminal logs, product screenshots, or specific historical claims without sources.",
            tests=["pixel styling remains decorative", "Chinese text readable", "no pseudo-code filler"],
            provenance=[SOURCE_AAAAAAAJ_SLIDES],
        ),
        "bento_grid_showcase": _card(
            id="bento_grid_showcase",
            name="Bento Grid Showcase",
            category="business_technical",
            scenario_tags=["capability_map", "product_overview", "feature_summary", "ai_platform"],
            visual_tags=["bento", "modular_grid", "product_showcase", "apple_like"],
            prompt_recipe="Use a tightly aligned bento grid filling the 16:9 frame, with one hero block, 3-5 supporting cards, and crisp information hierarchy.",
            visual_keywords=["Bento Grid", "modular rounded cards", "hero block", "premium product showcase"],
            palette=["off-white", "graphite", "cobalt blue", "mint", "soft orange"],
            layout_archetypes=["hero card + metric cards", "capability map", "feature showcase grid"],
            text_density="medium",
            source_policy="Use abstract screenshot/icon modules unless real product assets are supplied.",
            tests=["grid alignment", "one clear hero block", "not a pile of unrelated cards"],
            provenance=[SOURCE_AAAAAAAJ_SLIDES, SOURCE_HTML_TEMPLATE_FAMILY],
        ),
        "scrapbook_diy": _card(
            id="scrapbook_diy",
            name="Scrapbook DIY",
            category="trend_visual",
            scenario_tags=["workshop", "creative_recap", "community", "campaign"],
            visual_tags=["scrapbook", "paper", "stickers", "handmade"],
            prompt_recipe="Use a handmade scrapbook board: torn paper cards, tape corners, sticker badges, doodle arrows, and an intentional but readable anti-grid layout.",
            visual_keywords=["scrapbook DIY", "torn paper", "tape corners", "sticker badges"],
            palette=["off-white", "tomato orange", "butter yellow", "sky blue", "hot pink"],
            layout_archetypes=["collage recap", "workshop board", "campaign moodboard"],
            text_density="medium",
            source_policy="Good for qualitative summaries and community notes; avoid presenting unsupported numbers as real.",
            tests=["messy but readable", "paper texture not behind small text", "clear main title"],
            provenance=[SOURCE_AAAAAAAJ_SLIDES],
        ),
        "dark_glassmorphism": _card(
            id="dark_glassmorphism",
            name="Dark Glassmorphism",
            category="tech_ai_product",
            scenario_tags=["ai_control_plane", "dashboard", "security", "enterprise_saas"],
            visual_tags=["dark_glass", "frosted", "aurora", "control_plane"],
            prompt_recipe="Create a dark glassmorphism control-plane slide with smoked frosted panels, luminous borders, and high-contrast enterprise labels.",
            visual_keywords=["dark glassmorphism", "smoked frosted glass", "AI control-plane", "luminous borders"],
            palette=["obsidian", "cyan", "violet", "white", "deep navy"],
            layout_archetypes=["control-plane dashboard", "KPI panel stack", "risk/ops overview"],
            text_density="medium-high",
            source_policy="Do not invent live telemetry, KPI numbers, logs, or security incidents.",
            tests=["dark contrast high", "glass does not obscure text", "no fake terminal content"],
            provenance=[SOURCE_AAAAAAAJ_SLIDES],
        ),
        "classic_deep_skeuomorphism": _card(
            id="classic_deep_skeuomorphism",
            name="Classic Deep Skeuomorphism",
            category="trend_visual",
            scenario_tags=["retro_tech", "product_history", "nostalgia", "premium_demo"],
            visual_tags=["skeuomorphic", "aqua", "beveled", "retro_app"],
            prompt_recipe="Use deep skeuomorphic materials: glossy controls, beveled panels, brushed metal, stitched or leather-like header, while preserving modern slide readability.",
            visual_keywords=["deep skeuomorphism", "Mac OS X Aqua", "beveled controls", "glossy dashboard"],
            palette=["warm parchment", "brushed aluminum", "dark leather", "aqua blue", "white highlights"],
            layout_archetypes=["retro app dashboard", "product history panel", "tactile module cards"],
            text_density="medium",
            source_policy="Use as retro visual metaphor; no fake OS/app UI unless provided.",
            tests=["material depth controlled", "not cluttered", "labels readable"],
            provenance=[SOURCE_AAAAAAAJ_SLIDES],
        ),

        # NotebookLM / Kael prompt collection styles.
        "black_orange_agency": _card(
            id="black_orange_agency",
            name="Black x Orange Creative Agency",
            category="editorial_media",
            scenario_tags=["agency_pitch", "brand_story", "campaign", "product_marketing"],
            visual_tags=["black_orange", "creative_agency", "photo_typography", "minimal"],
            prompt_recipe="Use a creative-agency layout with black text, blood-orange accents, dynamic photo crops, and confident typographic placement.",
            visual_keywords=["black orange agency", "dynamic photo crop", "creative agency editorial"],
            palette=["white", "black", "blood orange", "warm gray"],
            layout_archetypes=["photo + typography split", "agency cover", "campaign proof cards"],
            text_density="medium",
            source_policy="Do not invent campaign results, client names, or awards unless supplied.",
            tests=["orange accent controlled", "photo does not obscure text", "agency polish"],
            provenance=[SOURCE_NOTEBOOKLM_PROMPTS],
        ),
        "seminar_minimal_photo": _card(
            id="seminar_minimal_photo",
            name="Seminar Minimal Photo",
            category="academic_teaching",
            scenario_tags=["seminar", "talk", "paper_briefing", "minimal_text"],
            visual_tags=["minimal_photo", "red_accent", "seminar", "high_sensibility"],
            prompt_recipe="Use a seminar-ready minimal slide: white background, black text, red accent, one high-quality photo or abstract figure, and minimal but meaningful text.",
            visual_keywords=["seminar minimal", "red accent", "high-quality photo", "minimal text"],
            palette=["white", "black", "red", "light gray"],
            layout_archetypes=["minimal cover", "photo + one key point", "seminar transition slide"],
            text_density="low-medium",
            source_policy="Good for talks; source-grounded claims should be in short labels or captions.",
            tests=["not empty", "one clear message", "photo is source-safe or generic"],
            provenance=[SOURCE_NOTEBOOKLM_PROMPTS],
        ),
        "mature_cute_magazine": _card(
            id="mature_cute_magazine",
            name="Mature-cute Magazine",
            category="editorial_media",
            scenario_tags=["lifestyle_report", "consumer_insight", "brand_story", "education"],
            visual_tags=["magazine", "dusty_pink", "cutout_photo", "speech_bubbles"],
            prompt_recipe="Use a mature-cute magazine editorial layout with a large cutout subject, asymmetrical speech bubbles, numbered small sections, and crop-mark details.",
            visual_keywords=["mature cute magazine", "dusty pink", "cutout photo", "speech bubbles", "trim marks"],
            palette=["dusty pink", "charcoal", "white", "muted rose"],
            layout_archetypes=["center cutout + side notes", "numbered editorial spread", "vertical copy strip"],
            text_density="medium",
            source_policy="Avoid lifestyle claims or demographic facts unless supplied.",
            tests=["polished not childish", "speech bubbles readable", "no overdecorated gradients"],
            provenance=[SOURCE_NOTEBOOKLM_PROMPTS],
        ),
        "pink_street_pop": _card(
            id="pink_street_pop",
            name="Pink Street Pop",
            category="trend_visual",
            scenario_tags=["youth_campaign", "community", "consumer_marketing", "creative_class"],
            visual_tags=["pink", "street", "deformed_illustration", "flat"],
            prompt_recipe="Use pink street-pop energy with flat thick-line illustrations, soft squishy cutouts, and loose but readable layout rhythm.",
            visual_keywords=["pink street style", "thick-line pop illustration", "soft squishy shapes"],
            palette=["pink", "white", "black", "coral", "light blue"],
            layout_archetypes=["street poster", "illustrated callout board", "campaign recap"],
            text_density="medium",
            source_policy="Suitable for campaign concepts; avoid fake social metrics.",
            tests=["street energy", "not childish", "readable text hierarchy"],
            provenance=[SOURCE_NOTEBOOKLM_PROMPTS],
        ),
        "mincho_handwritten_mix": _card(
            id="mincho_handwritten_mix",
            name="Mincho x Handwritten Mix",
            category="editorial_media",
            scenario_tags=["editorial", "culture", "fashion", "brand_story"],
            visual_tags=["mincho", "handwritten", "yellow_black", "fashion"],
            prompt_recipe="Mix large modern serif/Mincho-like typography with handwritten notes and fashion-editorial sticker accents.",
            visual_keywords=["Mincho handwritten mix", "modern serif", "fashion editorial", "handwriting stickers"],
            palette=["yellow", "black", "white", "small red accent"],
            layout_archetypes=["serif poster", "fashion note spread", "headline + sticker callouts"],
            text_density="medium",
            source_policy="Use for style and opinion; factual statements need source context.",
            tests=["serif headline readable", "handwriting not gibberish", "stickers secondary"],
            provenance=[SOURCE_NOTEBOOKLM_PROMPTS],
        ),
        "royal_blue_red_watercolor": _card(
            id="royal_blue_red_watercolor",
            name="Royal Blue x Red Watercolor",
            category="artistic_avant_garde",
            scenario_tags=["concept_intro", "culture", "strategy_theme", "premium_report"],
            visual_tags=["watercolor", "royal_blue", "red", "artistic"],
            prompt_recipe="Use royal blue and red watercolor tension with painterly fields, refined whitespace, and a clear slide structure for the message.",
            visual_keywords=["royal blue red watercolor", "wet watercolor", "artistic presentation"],
            palette=["royal blue", "deep red", "white", "ink black"],
            layout_archetypes=["artistic cover", "concept contrast", "premium section divider"],
            text_density="low-medium",
            source_policy="Best for thematic framing; avoid making art texture stand in for evidence.",
            tests=["artistic but readable", "strong contrast", "not muddy"],
            provenance=[SOURCE_NOTEBOOKLM_PROMPTS],
        ),
        "sculpture_vaporwave_pop": _card(
            id="sculpture_vaporwave_pop",
            name="Classical Sculpture x Vaporwave Pop",
            category="artistic_avant_garde",
            scenario_tags=["creative_intro", "culture", "trend_report", "brand_campaign"],
            visual_tags=["classical_sculpture", "vaporwave", "neon", "surreal_pop"],
            prompt_recipe="Use a surreal classical-sculpture remix with vivid solid colors, modern objects, clean cutouts, and high-contrast headline placement.",
            visual_keywords=["classical sculpture pop", "vaporwave", "neon surrealism", "clean cutouts"],
            palette=["cyan", "magenta", "yellow", "lime", "white sculpture"],
            layout_archetypes=["statue cover", "old vs new comparison", "surreal item list"],
            text_density="low-medium",
            source_policy="Use public-domain/generic classical motifs; avoid real brand logos or unsupported cultural claims.",
            tests=["surreal but coherent", "strong title contrast", "no trademarked products"],
            provenance=[SOURCE_NOTEBOOKLM_PROMPTS],
        ),
        "tech_art_neon_constructivist": _card(
            id="tech_art_neon_constructivist",
            name="Tech Art Neon Constructivist",
            category="artistic_avant_garde",
            scenario_tags=["ai_system", "architecture", "research_intro", "future_workflow"],
            visual_tags=["constructivism", "neon_yellow", "collage", "architectural_grid"],
            prompt_recipe="Use a constructivist tech-art slide: warm gray paper, ultra-thin grid, monochrome cutouts, neon yellow geometry, and annotated intelligence architecture.",
            visual_keywords=["constructivist tech art", "neon yellow geometry", "architectural draft lines", "monochrome cutouts"],
            palette=["warm gray", "charcoal", "neon yellow", "white"],
            layout_archetypes=["triple collage", "technical drawing", "geometric connection flow", "radar chart art"],
            text_density="medium-high",
            source_policy="Keep charts schematic unless data is supplied; no fake technical evidence.",
            tests=["limited palette", "annotations readable", "neon shapes purposeful"],
            provenance=[SOURCE_NOTEBOOKLM_PROMPTS],
        ),
        "digital_neo_pop": _card(
            id="digital_neo_pop",
            name="Digital Neo Pop",
            category="trend_visual",
            scenario_tags=["social_product", "education", "community", "data_story"],
            visual_tags=["digital_pop", "organic_shapes", "sns", "academic_pop"],
            prompt_recipe="Use digital neo-pop with organic blobs, bright pop colors, SNS-style icons, and a high-information but friendly slide rhythm.",
            visual_keywords=["Digital Neo Pop", "organic blobs", "SNS chat style", "colorful step flow"],
            palette=["white", "vivid pink", "cyan", "purple", "black"],
            layout_archetypes=["organic timeline", "SNS chat explainer", "colorful step flow", "sticker grid"],
            text_density="medium-high",
            source_policy="Use for friendly explainers; keep statistics source-grounded.",
            tests=["friendly but not noisy", "black outlines anchor text", "no random stickers"],
            provenance=[SOURCE_NOTEBOOKLM_PROMPTS],
        ),
        "anti_gravity_artifact": _card(
            id="anti_gravity_artifact",
            name="Anti-Gravity Artifact",
            category="tech_ai_product",
            scenario_tags=["agent_workflow", "future_system", "product_narrative", "research_product"],
            visual_tags=["anti_gravity", "white_space", "artifact", "deepmind_like"],
            prompt_recipe="Use calm anti-gravity artifact aesthetics: pure white space, soft blue-cyan-violet gradient accents, thin icons, and precise system-in-motion layouts.",
            visual_keywords=["Anti-Gravity Artifact", "living artifact", "soft gradient accents", "calm AI infrastructure"],
            palette=["white", "black", "calm blue", "cyan", "violet"],
            layout_archetypes=["thought to structure", "interface as proof", "capability cards"],
            text_density="medium",
            source_policy="Interface/screenshots must be abstract unless supplied; no hype or unsupported product claims.",
            tests=["calm not empty", "one idea per slide", "meaningful motion cues"],
            provenance=[SOURCE_NOTEBOOKLM_PROMPTS],
        ),
        "deformed_flat_persona": _card(
            id="deformed_flat_persona",
            name="Deformed Flat Persona",
            category="illustration",
            scenario_tags=["persona", "education", "consumer_insight", "scenario_story"],
            visual_tags=["flat", "deformed_persona", "thick_outline", "soft_colors"],
            prompt_recipe="Use flat deformed-persona illustration with thick outlines, up to three gentle colors, and a simple story/callout structure.",
            visual_keywords=["deformed flat persona", "thick outline", "soft flat colors"],
            palette=["soft mixed white tones", "one solid background color", "two accents"],
            layout_archetypes=["persona scenario", "problem story", "journey snapshot"],
            text_density="medium",
            source_policy="Personas should be fictional unless the user provides research evidence.",
            tests=["persona original", "up to three colors", "story labels readable"],
            provenance=[SOURCE_NOTEBOOKLM_PROMPTS],
        ),
        "sports_athletic_energy": _card(
            id="sports_athletic_energy",
            name="Sports Athletic Energy",
            category="high_energy",
            scenario_tags=["competition", "sales_drive", "team_motivation", "campaign"],
            visual_tags=["sports", "diagonal", "speed", "scoreboard"],
            prompt_recipe="Use sports/athletic energy with diagonal cuts, bold italic typography, speed-meter or scoreboard metaphors, and strong motion.",
            visual_keywords=["sports athletic energy", "diagonal cuts", "speed meter", "scoreboard"],
            palette=["asphalt black", "white", "bolt lime", "neon orange"],
            layout_archetypes=["action cut", "VS layout", "speed meter", "highlight stripe"],
            text_density="medium",
            source_policy="Scores and achievements must be supplied or clearly conceptual.",
            tests=["fast but readable", "no fake athlete/photo claims", "diagonal structure clear"],
            provenance=[SOURCE_NOTEBOOKLM_PROMPTS],
        ),
        "neo_retro_dev_deck": _card(
            id="neo_retro_dev_deck",
            name="Neo-Retro Dev Deck",
            category="tech_ai_product",
            scenario_tags=["developer", "ai_tools", "architecture", "manifesto"],
            visual_tags=["neo_retro", "pixel_infographic", "developer", "grid_paper"],
            prompt_recipe="Use a neo-retro developer deck style: cream grid-paper background, thick outlined modular blocks, pixel icons, and short opinionated builder copy.",
            visual_keywords=["Neo-Retro Dev Deck", "pixel infographic editorial", "grid paper", "developer blocks"],
            palette=["cream", "black", "hot pink", "bright yellow", "cyan"],
            layout_archetypes=["system architecture stack", "evolution timeline", "manifesto slide"],
            text_density="medium",
            source_policy="No fake code/logs; keep technical claims user-supplied or conceptual.",
            tests=["cohesive dev deck", "short declarative copy", "pixel icons decorative"],
            provenance=[SOURCE_NOTEBOOKLM_PROMPTS],
        ),

        # PPT-master example deck styles.
        "editorial_magazine_architecture": _card(
            id="editorial_magazine_architecture",
            name="Editorial Magazine Architecture",
            category="editorial_media",
            scenario_tags=["architecture", "culture_report", "portfolio", "premium_editorial"],
            visual_tags=["editorial_magazine", "architecture_photo", "calm_grid"],
            prompt_recipe="Use calm architectural editorial design: strong photography or photo-like blocks, restrained type, spacious grid, and magazine pacing.",
            visual_keywords=["Editorial Magazine", "architecture photography", "calm typographic grid"],
            palette=["white", "stone gray", "black", "muted accent"],
            layout_archetypes=["feature opener", "photo essay spread", "captioned grid"],
            text_density="medium",
            source_policy="Architecture/place facts require sources; otherwise use generic editorial framing.",
            tests=["magazine feel", "image does not dominate text", "captions readable"],
            provenance=[SOURCE_PPT_MASTER],
        ),
        "bloomberg_dark_dashboard": _card(
            id="bloomberg_dark_dashboard",
            name="Bloomberg Dark Dashboard",
            category="data_media",
            scenario_tags=["finance", "data_dashboard", "market_report", "risk_monitoring"],
            visual_tags=["bloomberg", "dark_dashboard", "terminal", "charts"],
            prompt_recipe="Use a dark chart-driven financial dashboard with compact panels, strong numbers only from supplied data, and dense market-report hierarchy.",
            visual_keywords=["Bloomberg-style dark dashboard", "terminal panels", "chart-driven"],
            palette=["black", "amber", "cyan", "green", "white"],
            layout_archetypes=["multi-panel dashboard", "risk board", "market chart grid"],
            text_density="high",
            source_policy="Every number, market movement, ticker, and date must be supplied.",
            tests=["no fake market data", "dense but legible", "charts dominate"],
            provenance=[SOURCE_PPT_MASTER],
        ),
        "glassmorphism_saas": _card(
            id="glassmorphism_saas",
            name="Glassmorphism SaaS",
            category="tech_ai_product",
            scenario_tags=["saas", "ai_agent", "engineering_demo", "product_story"],
            visual_tags=["glassmorphism", "saas", "translucent_layers", "gradient_depth"],
            prompt_recipe="Use translucent SaaS glass layers, gradient depth, product UI-like modules, and crisp feature callouts without copying real UI.",
            visual_keywords=["Glassmorphism SaaS", "translucent layers", "gradient depth", "product UI"],
            palette=["deep navy", "cyan", "violet", "white", "mint"],
            layout_archetypes=["SaaS dashboard hero", "agent workflow UI", "feature panel stack"],
            text_density="medium",
            source_policy="Product UI is abstract unless source screenshots are provided.",
            tests=["premium SaaS finish", "not fake screenshot", "glass contrast"],
            provenance=[SOURCE_PPT_MASTER],
        ),
        "memphis_pop_festival": _card(
            id="memphis_pop_festival",
            name="Memphis Pop Festival",
            category="trend_visual",
            scenario_tags=["event", "education", "consumer_campaign", "creative_pitch"],
            visual_tags=["memphis", "pop", "geometric_patterns", "playful"],
            prompt_recipe="Use Memphis Pop energy with bold primary shapes, geometric patterns, playful rhythm, and a clear PPT message structure.",
            visual_keywords=["Memphis Pop", "bold primaries", "geometric patterns", "playful energy"],
            palette=["yellow", "cyan", "magenta", "black", "white"],
            layout_archetypes=["event poster slide", "playful concept map", "geometric process"],
            text_density="low-medium",
            source_policy="Use for creative education/events; factual claims need supplied source.",
            tests=["playful not chaotic", "title readable", "patterns secondary"],
            provenance=[SOURCE_PPT_MASTER, SOURCE_NANO_BANANA_PPT],
        ),
        "risograph_zine": _card(
            id="risograph_zine",
            name="Risograph Zine",
            category="editorial_media",
            scenario_tags=["culture", "community", "indie_guide", "creative_report"],
            visual_tags=["risograph", "zine", "duotone_print", "handmade"],
            prompt_recipe="Use risograph zine style: duotone print texture, hand-made editorial rhythm, rough paper, and compact guide-like sections.",
            visual_keywords=["Risograph Zine", "duotone print", "hand-made zine", "paper texture"],
            palette=["cream paper", "duotone red", "blue ink", "black"],
            layout_archetypes=["zine guide", "community map", "indie feature spread"],
            text_density="medium",
            source_policy="Locations, listings, and recommendations require supplied data.",
            tests=["print texture controlled", "guide sections readable", "no fake listings"],
            provenance=[SOURCE_PPT_MASTER],
        ),

        # nano-banana-ppt high-frequency scenarios.
        "creative_class_clay": _card(
            id="creative_class_clay",
            name="Creative Class Clay",
            category="education_courseware",
            scenario_tags=["course", "creative_class", "education", "lesson"],
            visual_tags=["3d_clay", "pastel", "knowledge_blocks", "studio_lighting"],
            prompt_recipe="Use 3D clay knowledge blocks, soft pastel palette, floating elements, and a playful but professional lesson structure.",
            visual_keywords=["3D Claymorphism", "knowledge blocks", "soft studio lighting"],
            palette=["mint", "coral", "soft yellow", "cream"],
            layout_archetypes=["lesson cover", "knowledge block map", "step-by-step learning"],
            text_density="medium",
            source_policy="Examples are illustrative unless supplied; keep teaching text useful and concise.",
            tests=["not childish", "knowledge structure clear", "Chinese lesson title visible"],
            provenance=[SOURCE_NANO_BANANA_PPT],
        ),
        "tech_knowledge_isometric_lab": _card(
            id="tech_knowledge_isometric_lab",
            name="Tech Knowledge Isometric Lab",
            category="academic_teaching",
            scenario_tags=["tech_share", "course", "hardcore_knowledge", "lab_explainer"],
            visual_tags=["isometric_lab", "exploded_view", "infographic", "high_tech"],
            prompt_recipe="Use a clean isometric futuristic-lab metaphor with exploded-view diagrams, vector lines, and organized bullet zones.",
            visual_keywords=["isometric futuristic laboratory", "exploded view diagrams", "high-tech minimalist"],
            palette=["white", "blue", "glass", "metal gray"],
            layout_archetypes=["isometric lab overview", "exploded concept diagram", "technical bullet board"],
            text_density="medium-high",
            source_policy="Scientific/technical facts require supplied source or should remain conceptual.",
            tests=["diagram not too busy", "bullet zones clear", "no fake apparatus labels"],
            provenance=[SOURCE_NANO_BANANA_PPT],
        ),
        "annual_strategy_cinematic": _card(
            id="annual_strategy_cinematic",
            name="Annual Strategy Cinematic",
            category="business_strategy",
            scenario_tags=["annual_strategy", "company_report", "vision", "pitch"],
            visual_tags=["cinematic", "city_skyline", "corporate", "premium"],
            prompt_recipe="Use cinematic corporate strategy mood with large-scale vision, dawn/city or abstract horizon metaphor, and board-level typography.",
            visual_keywords=["corporate strategy", "cinematic widescreen", "vision slide"],
            palette=["teal", "orange", "navy", "white"],
            layout_archetypes=["vision cover", "strategic pillars", "future roadmap"],
            text_density="medium",
            source_policy="Strategy claims and dates must come from user-provided material.",
            tests=["premium business mood", "not stock-photo-only", "clear strategy message"],
            provenance=[SOURCE_NANO_BANANA_PPT],
        ),
        "company_profile_swiss": _card(
            id="company_profile_swiss",
            name="Company Profile Swiss",
            category="business_strategy",
            scenario_tags=["company_profile", "corporate_report", "brand_intro"],
            visual_tags=["swiss", "architecture_photo", "red_blocks", "authoritative"],
            prompt_recipe="Use Swiss company-profile design with black-and-white architecture/photo blocks, red geometric accents, and strict asymmetrical balance.",
            visual_keywords=["Swiss company profile", "black white photography", "red geometric blocks"],
            palette=["white", "black", "red", "gray"],
            layout_archetypes=["company overview", "profile facts grid", "brand timeline"],
            text_density="high",
            source_policy="Company facts, dates, clients, and revenue require supplied sources.",
            tests=["authoritative profile", "no fake company facts", "grid strict"],
            provenance=[SOURCE_NANO_BANANA_PPT],
        ),
        "fintech_glass_data": _card(
            id="fintech_glass_data",
            name="Fintech Glass Data",
            category="data_media",
            scenario_tags=["financial_performance", "analytics", "fintech", "dashboard"],
            visual_tags=["glassmorphism", "fintech", "dark_data", "growth_chart"],
            prompt_recipe="Use high-end fintech data visualization: dark minimal background, glowing thin chart lines, glass KPI cards, and supplied metrics only.",
            visual_keywords=["fintech data visualization", "glowing chart lines", "glass KPI cards"],
            palette=["deep blue", "gold", "black", "white"],
            layout_archetypes=["financial KPI board", "growth chart + metric cards", "performance dashboard"],
            text_density="high",
            source_policy="Financial numbers, axes, periods, and comparisons must be supplied.",
            tests=["no fake finance data", "chart labels readable", "metrics from data_sources only"],
            provenance=[SOURCE_NANO_BANANA_PPT],
        ),
        "market_analysis_3d_infographic": _card(
            id="market_analysis_3d_infographic",
            name="Market Analysis 3D Infographic",
            category="data_media",
            scenario_tags=["market_analysis", "competitor_compare", "share_report"],
            visual_tags=["3d_infographic", "floating_charts", "pastel_data", "business_intelligence"],
            prompt_recipe="Use ultra-clean 3D infographic objects for market analysis: floating pie/bar charts, frosted/plastic materials, and distinct separation.",
            visual_keywords=["3D infographic", "floating pie charts", "business intelligence"],
            palette=["white", "pastel gradient", "soft gray", "blue"],
            layout_archetypes=["market share chart", "competitor comparison", "BI overview"],
            text_density="medium-high",
            source_policy="Market share, competitor data, and rankings must be supplied.",
            tests=["3D does not distort data", "no fake competitor numbers", "clean separation"],
            provenance=[SOURCE_NANO_BANANA_PPT],
        ),
        "personal_review_paper_cutout": _card(
            id="personal_review_paper_cutout",
            name="Personal Review Paper Cutout",
            category="operations_report",
            scenario_tags=["personal_review", "weekly_report", "retrospective", "timeline"],
            visual_tags=["paper_cutout", "calm", "timeline", "blue_layers"],
            prompt_recipe="Use layered paper-cutout paths or timelines with soft shadows, calm blue paper, simple icons, and review-focused copy.",
            visual_keywords=["paper cutout", "blue layered path", "soft ambient shadows"],
            palette=["soft blue", "white", "paper gray", "navy"],
            layout_archetypes=["personal timeline", "milestone path", "review checklist"],
            text_density="medium",
            source_policy="Personal metrics/tasks must be supplied; otherwise keep milestones generic.",
            tests=["calm review mood", "timeline readable", "paper texture not noisy"],
            provenance=[SOURCE_NANO_BANANA_PPT],
        ),
        "project_progress_kanban": _card(
            id="project_progress_kanban",
            name="Project Progress Kanban",
            category="operations_report",
            scenario_tags=["project_progress", "weekly_report", "status_update", "team_sync"],
            visual_tags=["kanban", "figma_style", "traffic_light_status", "minimal_zen"],
            prompt_recipe="Use a project-progress Kanban slide with clean lanes, traffic-light status dots, blockers, decisions, and next actions.",
            visual_keywords=["project progress Kanban", "status lanes", "traffic light dots", "Figma-style cards"],
            palette=["soft gray", "white", "green", "yellow", "red", "slate"],
            layout_archetypes=["done/doing/blocked/next", "status board", "weekly sync dashboard"],
            text_density="high",
            source_policy="Task names, owners, and progress values must be supplied or kept generic.",
            tests=["lanes readable", "status color semantics clear", "no fake project metrics"],
            provenance=[SOURCE_NANO_BANANA_PPT],
        ),
        "b2b_solution_architectural": _card(
            id="b2b_solution_architectural",
            name="B2B Solution Architectural",
            category="sales_business",
            scenario_tags=["b2b_solution", "business_proposal", "sales", "customer_value"],
            visual_tags=["architectural_minimalism", "concrete_texture", "gold_accent", "trust"],
            prompt_recipe="Use architectural minimalism for a B2B proposal: stable structure, focused light, solution modules, value path, and trust-building typography.",
            visual_keywords=["B2B solution", "architectural minimalism", "concrete texture", "gold foil accent"],
            palette=["concrete gray", "white", "charcoal", "gold"],
            layout_archetypes=["pain-solution-value", "solution architecture", "implementation trust path"],
            text_density="medium-high",
            source_policy="Do not promise ROI, customer proof, savings, or timelines unless supplied.",
            tests=["trustworthy not luxury-only", "solution modules clear", "no unsupported ROI"],
            provenance=[SOURCE_NANO_BANANA_PPT],
        ),
        "consumer_marketing_neobrutal": _card(
            id="consumer_marketing_neobrutal",
            name="Consumer Marketing Neo-Brutal",
            category="sales_business",
            scenario_tags=["consumer_marketing", "ecommerce", "campaign", "sales"],
            visual_tags=["neo_brutalism", "collage", "lifestyle", "high_impact"],
            prompt_recipe="Use high-impact consumer marketing neo-brutalism: vibrant colliding colors, thick borders, large typography, and lifestyle collage placeholders.",
            visual_keywords=["consumer marketing", "neo-brutalism", "lifestyle collage", "bold borders"],
            palette=["electric blue", "lime green", "black", "white"],
            layout_archetypes=["campaign cover", "channel strategy", "offer ladder"],
            text_density="medium",
            source_policy="Campaign performance, customer claims, and ecommerce data require supplied sources.",
            tests=["high impact but readable", "no fake campaign stats", "collage supports message"],
            provenance=[SOURCE_NANO_BANANA_PPT],
        ),

        # HTML/template-library inspired page families for gallery generation.
        "title_hero_split": _card(
            id="title_hero_split",
            name="Title Hero Split",
            category="html_template_family",
            scenario_tags=["cover", "product", "report", "pitch"],
            visual_tags=["hero", "split_layout", "template_family"],
            prompt_recipe="Use a reusable title-hero split layout: one dominant title area, one visual/evidence area, and a compact subtitle/takeaway rail.",
            visual_keywords=["hero split layout", "template family", "cover slide"],
            palette=["template dependent"],
            layout_archetypes=["left title right visual", "top title bottom proof", "hero visual + caption rail"],
            text_density="low-medium",
            source_policy="Visual proof must be abstract or supplied; no fake screenshots or metrics.",
            tests=["first-viewport signal", "balanced split", "not marketing landing page"],
            provenance=[SOURCE_HTML_TEMPLATE_FAMILY],
        ),
        "section_divider_catalog": _card(
            id="section_divider_catalog",
            name="Section Divider Catalog",
            category="html_template_family",
            scenario_tags=["divider", "chapter", "deck_navigation"],
            visual_tags=["section_divider", "template_family", "navigation"],
            prompt_recipe="Create a section divider slide with strong chapter number, short title, progress/navigation cue, and style-consistent motif.",
            visual_keywords=["section divider", "chapter opener", "deck navigation"],
            palette=["template dependent"],
            layout_archetypes=["chapter number + title", "progress strip", "motif opener"],
            text_density="low",
            source_policy="Section text should come from user deck outline.",
            tests=["chapter is obvious", "minimal but not blank", "consistent with deck style"],
            provenance=[SOURCE_HTML_TEMPLATE_FAMILY],
        ),
        "comparison_matrix_template": _card(
            id="comparison_matrix_template",
            name="Comparison Matrix Template",
            category="html_template_family",
            scenario_tags=["comparison", "decision", "strategy", "product"],
            visual_tags=["matrix", "table", "template_family"],
            prompt_recipe="Use a clear comparison matrix layout with qualitative rows/columns, concise criteria, and visually separated recommendation.",
            visual_keywords=["comparison matrix", "decision table", "template family"],
            palette=["template dependent"],
            layout_archetypes=["2x2 matrix", "option table", "tradeoff grid"],
            text_density="high",
            source_policy="Scores, rankings, and prices must be supplied; otherwise use qualitative labels.",
            tests=["table readable", "recommendation clear", "no invented rankings"],
            provenance=[SOURCE_HTML_TEMPLATE_FAMILY],
        ),
        "process_timeline_template": _card(
            id="process_timeline_template",
            name="Process Timeline Template",
            category="html_template_family",
            scenario_tags=["process", "timeline", "roadmap", "workflow"],
            visual_tags=["timeline", "process", "template_family"],
            prompt_recipe="Use a reusable process/timeline layout with 3-6 stages, clear arrows or progression marks, and concise stage explanations.",
            visual_keywords=["process timeline", "roadmap", "workflow template"],
            palette=["template dependent"],
            layout_archetypes=["horizontal roadmap", "vertical timeline", "stage ladder"],
            text_density="medium-high",
            source_policy="Dates and milestones require supplied source; otherwise use phase labels.",
            tests=["stage order clear", "arrows meaningful", "no fake dates"],
            provenance=[SOURCE_HTML_TEMPLATE_FAMILY],
        ),
        "data_dashboard_template": _card(
            id="data_dashboard_template",
            name="Data Dashboard Template",
            category="html_template_family",
            scenario_tags=["dashboard", "metrics", "operations", "analytics"],
            visual_tags=["dashboard", "kpi", "template_family"],
            prompt_recipe="Use a reusable data dashboard layout with KPI cards, one main chart region, a secondary chart strip, and source/data note.",
            visual_keywords=["data dashboard", "KPI cards", "main chart region"],
            palette=["template dependent"],
            layout_archetypes=["KPI row + chart", "operations dashboard", "metric tiles"],
            text_density="high",
            source_policy="Every displayed metric must come from data_sources.",
            tests=["metrics match data", "chart readable", "source note visible when supplied"],
            provenance=[SOURCE_HTML_TEMPLATE_FAMILY],
        ),
    }
)


_CATEGORY_BOOSTS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("AI", "agent", "workflow", "platform", "product", "system", "infrastructure", "knowledge", "知识库", "工作流", "智能体", "平台", "系统", "落地"), ("tech_ai_product", "business_technical", "business_strategy")),
    (("business", "strategy", "corporate", "board", "market", "企业", "公司", "战略", "管理层", "汇报", "董事会"), ("business_strategy", "business_technical", "sales_business")),
    (("course", "teaching", "training", "education", "课程", "教学", "培训", "学习", "课堂"), ("education_courseware", "ip_safe_cartoon")),
    (("data", "metric", "dashboard", "analysis", "report", "数据", "指标", "图表", "分析", "报告"), ("editorial_media", "operations_report", "tech_ai_product")),
    (("weekly", "kanban", "status", "retro", "周报", "复盘", "进展", "状态"), ("operations_report",)),
    (("sales", "customer", "pitch", "销售", "客户", "路演", "方案"), ("sales_business", "product_marketing")),
    (("manga", "anime", "cartoon", "robot", "Doraemon", "哆啦", "机器猫", "漫画", "卡通", "机器人"), ("ip_safe_cartoon",)),
)


_ID_HINT_BOOSTS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("newspaper", "news", "报纸", "新闻"), ("modern_newspaper",)),
    (("yellow", "black", "warning", "黄色", "黑色", "预警"), ("yellow_black_editorial",)),
    (("swiss", "grid", "瑞士", "网格"), ("swiss_international",)),
    (("blueprint", "architecture", "架构", "蓝图"), ("design_blueprint", "sales_architectural")),
    (("cyber", "security", "infra", "安全", "基础设施"), ("cyberpunk_neon",)),
    (("glass", "reference", "参考图", "玻璃", "毛玻璃"), ("light_glassmorphism",)),
    (("course", "lesson", "课程", "课件"), ("course_clay",)),
    (("weekly", "kanban", "周报", "看板"), ("weekly_kanban",)),
    (("sales", "customer", "销售", "客户"), ("sales_architectural",)),
)


def list_template_cards() -> list[dict[str, Any]]:
    """Return JSON-serializable template/style cards for the prompt effect library."""

    return [deepcopy(card) for card in TEMPLATE_CARD_LIBRARY.values()]


def get_template_card(card_id: str) -> dict[str, Any]:
    """Return one template/style card by stable id or display name."""

    return _get_template_card(card_id)


def recommend_template_cards(user_input: str, limit: int = 6) -> list[dict[str, Any]]:
    """Recommend template cards using lightweight keyword and category routing."""

    query = _normalize_query(user_input)
    limit = max(1, int(limit or 1))
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for index, card in enumerate(TEMPLATE_CARD_LIBRARY.values()):
        score = _score_card(card, query)
        scored.append((score, -index, card))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [deepcopy(card) for score, _, card in scored[:limit] if score > 0] or list_template_cards()[:limit]


def build_prompt_from_template_card(
    card_id: str,
    user_topic: str,
    *,
    language: str = "zh",
    reference_image_paths: Sequence[str] | None = None,
) -> str:
    """Build a standalone prompt from one template card.

    This is an adapter for prompt-only experiments and future UI cards. It does
    not mutate the existing slide_image_strategy TEMPLATE_REGISTRY.
    """

    card = _get_template_card(card_id)
    refs = [str(path).strip() for path in (reference_image_paths or ()) if str(path).strip()]
    language_policy = _language_policy(language)
    lines = [
        "DrawAI PPT image template-card prompt.",
        "",
        "Goal:",
        "- Generate one premium 16:9 PPT slide bitmap for the user's topic.",
        "- Use baked_text: the final bitmap must already include readable title, body copy, labels, diagrams, and callouts.",
        "- Do not leave empty layout placeholders or generic Latin filler text.",
        "- Keep factual claims source-safe; do not invent statistics, citations, dates, rankings, logos, UI screens, maps, or named evidence.",
        "",
        f"User topic: {str(user_topic).strip()}",
        "",
        "Template card:",
        _compact_json(
            {
                "id": card["id"],
                "name": card["name"],
                "category": card["category"],
                "scenario_tags": card["scenario_tags"],
                "visual_tags": card["visual_tags"],
            }
        ),
        "",
        "Prompt recipe:",
        f"- {card['prompt_recipe']}",
        "",
        "Visual system:",
        f"- visual_keywords: {', '.join(card['visual_keywords'])}",
        f"- palette: {', '.join(card['palette'])}",
        f"- layout_archetypes: {', '.join(card['layout_archetypes'])}",
        "",
        "Language and visible text:",
        *language_policy,
        "- Minimum useful visible text: a clear title, one takeaway/subtitle, 3-6 concise bullets or callouts, and purposeful section/module labels.",
        "- If exact long text is hard to render, split it into shorter readable Chinese phrases rather than omitting text.",
    ]
    if refs:
        lines.extend(
            [
                "",
                "Image as context:",
                "- Use the supplied images as visual context only.",
                "- Do not copy logos, proprietary characters, exact UI screens, protected artwork, trademarks, or visible text from reference images.",
                "- Preserve the user's topic and content; adapt only composition, mood, color, spacing, and layout rhythm.",
                f"- context_image_paths: {json.dumps(refs, ensure_ascii=False)}",
            ]
        )
    lines.extend(
        [
            "",
            "Quality tests:",
            *_render_list(card["tests"]),
            "- slide reads as one coherent deck page, not a collage of unrelated panels",
            "- high contrast, clear hierarchy, clean margins, no overlapping elements",
            "- no mojibake, pseudo-writing, watermark-like marks, or random captions",
            "",
            'Final response contract: reply only {"generated": true}.',
        ]
    )
    return "\n".join(lines).strip()


def _get_template_card(card_id: str) -> dict[str, Any]:
    normalized = _normalize_id(card_id)
    for key, card in TEMPLATE_CARD_LIBRARY.items():
        if normalized in {_normalize_id(key), _normalize_id(card["id"]), _normalize_id(card["name"])}:
            return deepcopy(card)
    raise KeyError(f"unknown slide template card: {card_id}")


def _score_card(card: Mapping[str, Any], query: str) -> float:
    text = _normalize_query(
        " ".join(
            [
                str(card.get("id", "")),
                str(card.get("name", "")),
                str(card.get("category", "")),
                " ".join(card.get("scenario_tags", [])),
                " ".join(card.get("visual_tags", [])),
                str(card.get("prompt_recipe", "")),
                " ".join(card.get("visual_keywords", [])),
                " ".join(card.get("layout_archetypes", [])),
            ]
        )
    )
    query_tokens = [token for token in re.split(r"\s+", query) if len(token) >= 2]
    score = 0.0
    for token in query_tokens:
        if token in text:
            score += 1.0
    for keywords, categories in _CATEGORY_BOOSTS:
        if any(_normalize_query(keyword) in query for keyword in keywords):
            if str(card.get("category")) in categories:
                score += 4.0
            if set(card.get("scenario_tags", ())).intersection(categories):
                score += 1.0
    for keywords, ids in _ID_HINT_BOOSTS:
        if any(_normalize_query(keyword) in query for keyword in keywords):
            if str(card.get("id")) in ids:
                score += 6.0
    if str(card.get("id")) in {"minimalist_clean", "swiss_international"}:
        score += 0.2
    return score


def _normalize_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _normalize_query(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower().replace("-", " ").replace("_", " "))


def _language_policy(language: str) -> list[str]:
    normalized = str(language or "").strip().lower()
    if normalized in {"zh", "zh-cn", "chinese", "cn"}:
        return [
            "- main_language: Chinese.",
            "- Render main title, subtitle, headings, bullets, callouts, captions, and takeaway text in Chinese.",
            "- Keep English only for proper nouns, product/model names, API names, code identifiers, acronyms, and standard technical terms.",
        ]
    if normalized in {"en", "english"}:
        return ["- main_language: English.", "- Use concise English slide copy and avoid pseudo-writing."]
    return ["- main_language: follow the user's prompt; preserve Chinese if the user topic is Chinese."]


def _render_list(values: Sequence[Any]) -> list[str]:
    return [f"- {value}" for value in values if str(value).strip()]


def _compact_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


__all__ = [
    "SLIDE_TEMPLATE_LIBRARY_SCHEMA",
    "TEMPLATE_CARD_LIBRARY",
    "build_prompt_from_template_card",
    "get_template_card",
    "list_template_cards",
    "recommend_template_cards",
]
