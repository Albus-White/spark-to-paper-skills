/* ============================================================================
   Reading-AI transport — wires SB.ai to the server /api/ai SSE proxy.
   Loading this file upgrades the reader's summary / explain / translate / ask
   from the built-in placeholder stream to the real (DeepSeek / OpenAI-compatible)
   model configured in Settings → Reading assistant.

   Restrained by construction: exactly one request in flight (a newer gesture
   aborts the older one), and an unreachable endpoint degrades to one honest line
   instead of hanging. Text leaves the page ONLY here, ONLY when the user acted.
   ============================================================================ */
(function () {
  "use strict";
  var SB = window.SB;
  if (!SB) return;

  // item 17 — inflight is now keyed by CHANNEL, not a single global slot. A newer gesture on
  // the SAME channel still aborts the older one (the restraint the header describes), but the
  // long-running AI summary ("summary" channel) and a selection Explain/Ask/Translate
  // ("selection" channel) no longer abort each other — so starting a selection mid-summary can't
  // strand the summary card at "AI Summary …". Requests with no channel share "default".
  var inflight = {};

  SB.aiTransport = function (req, onChunk) {
    var ch = (req && req.channel) || "default";
    if (inflight[ch]) { try { inflight[ch].abort(); } catch (e) {} }   // newest-in-channel wins; other channels untouched
    var ctrl = window.AbortController ? new AbortController() : null;
    inflight[ch] = ctrl;
    var full = "";
    function clearIf() { if (inflight[ch] === ctrl) inflight[ch] = null; }   // don't clear a newer request that already replaced us

    // R5 — carry the UI language into the request so the server can answer in it
    // ('Answer in English.' / '用中文回答'); default from the shell state if a caller
    // reached the transport without going through SB.ai.
    var body = {};
    for (var k in req) if (Object.prototype.hasOwnProperty.call(req, k)) body[k] = req[k];
    delete body.channel;                                 // UI-only routing; not part of the model request
    if (!body.ui_lang && SB.state) body.ui_lang = SB.state.lang;

    fetch("/api/ai", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: ctrl && ctrl.signal,
    })
      .then(function (r) {
        if (!r.ok || !r.body) throw new Error("ai http " + r.status);
        var reader = r.body.getReader(), dec = new TextDecoder(), buf = "";
        (function pump() {
          reader.read().then(function (res) {
            if (res.done) { clearIf(); onChunk("", true, full); return; }
            buf += dec.decode(res.value, { stream: true });
            var frames = buf.split("\n\n");
            buf = frames.pop();                       // keep the trailing partial frame
            for (var i = 0; i < frames.length; i++) {
              var line = frames[i].replace(/^data:\s?/, "");
              if (line === "[DONE]") continue;
              try {
                var d = JSON.parse(line);
                if (d && typeof d.t === "string") { full += d.t; onChunk(d.t, false, full); }
              } catch (e) { /* keepalive / comment frame */ }
            }
            pump();
          }).catch(function () { clearIf(); onChunk("", true, full); });
        })();
      })
      .catch(function (e) {
        clearIf();
        if (ctrl && e && e.name === "AbortError") return;    // superseded — stay silent
        var msg = (SB.state && SB.state.lang === "en")
          ? "(Reading assistant unavailable — set it up in Settings → Reading assistant.)"
          : "（阅读助手暂不可用 —— 在「设置 → 阅读助手」里配置好模型即可。文本只在你点按后才会发送。）";
        onChunk(msg, true, msg);
      });
  };
})();
