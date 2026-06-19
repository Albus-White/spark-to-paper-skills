# ts-paper-figure — image-model config. Copy to figure_config.sh, fill in, then:  source figure_config.sh
#
# You configure ONLY the external IMAGE model here. The planning + vision critique are done by
# Claude itself (in-session) and need no config.

# --- required: the external image model (Claude cannot draw pixels) ---
export TS_FIG_MODEL=""        # image model name, e.g. gpt-image-2, gemini-3.1-flash-image-preview
export TS_FIG_API_KEY=""      # image API key
export TS_FIG_BASE_URL=""     # OpenAI-compatible base URL, e.g. https://sogenport.com/v1

# --- optional (quality knobs — defaults shown) ---
export TS_FIG_API_STYLE="images"   # "images" (OpenAI /images/generations) or "chat"
                                   # (/chat/completions with image output — for nano-banana-style gateways)
export TS_FIG_SIZE="1536x1024"     # landscape; bigger than 1024x1024 → less crude (the product's default)
export TS_FIG_QUALITY="high"       # gpt-image-* quality knob
