(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const LEVEL_COLORS = ["#ED7D31", "#1E6B1E", "#7030A0", "#C00000"];
  const FMT_NAME = { xlsx: "Excel", png: "PNG", jpg: "JPG", pdf: "PDF" };

  const S = {
    token: null,
    name: "",
    points: 0,
    metrics: [],
    metric: "",
    channels: [],
    checked: new Set(),
    active: null,
    levels: [], 
    fmt: "xlsx",
    da: 0,
    db: 1,
    deltaOn: true,
    mode: "sep",
    cmp: [], 
    downloadUrl: null,
  };

 
  function el(tag, attrs = {}, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v);
    }
    kids.forEach((c) => e.append(c));
    return e;
  }
  async function api(path, body, isForm) {
    const r = await fetch(
      path,
      isForm
        ? { method: "POST", body }
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          },
    );
    if (!r.ok) {
      let msg = "Algo deu errado.";
      try {
        msg = (await r.json()).error || msg;
      } catch (_) {}
      throw new Error(msg);
    }
    return r;
  }
  function show(stage) {
    $("#stage-home").hidden = stage !== "home";
    $("#stage-work").hidden = stage !== "work";
    $("#stage-done").hidden = stage !== "done";
    window.scrollTo(0, 0);
  }
  const debounce = (fn, ms) => {
    let t;
    return (...a) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...a), ms);
    };
  };
  const num = (v) => parseFloat(String(v).replace(",", "."));


  const drop = $("#drop"),
    fileInput = $("#file");
  $("#pick").addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => fileInput.files[0] && upload(fileInput.files[0]));
  ["dragenter", "dragover"].forEach((ev) =>
    drop.addEventListener(ev, (e) => {
      e.preventDefault();
      drop.classList.add("over");
    }),
  );
  ["dragleave", "drop"].forEach((ev) =>
    drop.addEventListener(ev, (e) => {
      e.preventDefault();
      drop.classList.remove("over");
    }),
  );
  drop.addEventListener("drop", (e) => {
    const f = e.dataTransfer.files[0];
    if (f) upload(f);
  });
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => e.preventDefault());

  async function upload(file) {
    $("#home-err").textContent = "";
    const btn = $("#pick");
    const old = btn.lastChild.textContent;
    btn.disabled = true;
    btn.lastChild.textContent = " Lendo o arquivo…";
    try {
      const fd = new FormData();
      fd.append("csv", file);
      const j = await (await api("/api/upload", fd, true)).json();
      Object.assign(S, {
        token: j.token,
        name: j.name || file.name,
        points: j.points,
        metrics: j.metrics,
        metric: j.metric,
        channels: j.channels,
        checked: new Set(j.channels),
        active: j.channels[0],
        levels: [],
        da: 0,
        db: 1,
        mode: "sep",
        cmp: [],
      });
      buildWork();
      show("work");
      await autoDetect(true);
    } catch (e) {
      $("#home-err").textContent = e.message;
    } finally {
      btn.disabled = false;
      btn.lastChild.textContent = old;
      fileInput.value = "";
    }
  }

  
  function buildWork() {
    $("#filechip").textContent = `📄 ${S.name} · ${S.points} pontos`;
    const m = $("#metric");
    m.replaceChildren();
    S.metrics.forEach((x) => m.append(el("option", { value: x, text: x })));
    m.value = S.metric;
    renderChannels();
    renderTabs();
    renderLevels();
    renderMode();
    renderFmt();
  }

  function renderChannels() {
    const box = $("#chs");
    box.replaceChildren();
    S.channels.forEach((c) => {
      const cb = el("input", { type: "checkbox" });
      cb.checked = S.checked.has(c);
      cb.addEventListener("change", () => {
        cb.checked ? S.checked.add(c) : S.checked.delete(c);
      });
      box.append(el("label", { class: "chk" }, cb, el("span", { text: c })));
    });
  }
  
  const MAXCMP = 4;
  function renderMode() {
    const cmp = S.mode === "cmp";
    document.querySelectorAll(".mode").forEach((b) => {
      const on = b.dataset.m === S.mode;
      b.classList.toggle("on", on);
      b.setAttribute("aria-checked", String(on));
    });
    $("#sec-cmp").hidden = !cmp;
    $("#sec-chs").hidden = cmp;
    $("#tabs").hidden = cmp;
    if (cmp) {
      S.cmp = S.cmp.filter((x) => S.channels.includes(x.ch));
      if (!S.cmp.length) S.cmp = S.channels.slice(0, 2).map((c) => ({ ch: c, name: c }));
      renderCmp();
    }
    renderFmt();
  }
  function renderCmp() {
    const box = $("#cmplist");
    box.replaceChildren();
    S.channels.forEach((c) => {
      const cur = S.cmp.find((x) => x.ch === c);
      const cb = el("input", { type: "checkbox" });
      cb.checked = !!cur;
      cb.addEventListener("change", () => {
        if (cb.checked) {
          if (S.cmp.length >= MAXCMP) {
            cb.checked = false;
            $("#work-err").textContent = `Compare no máximo ${MAXCMP} canais.`;
            return;
          }
          S.cmp.push({ ch: c, name: c });
        } else S.cmp = S.cmp.filter((x) => x.ch !== c);
        $("#work-err").textContent = "";
        renderCmp();
        preview();
      });
      const row = el(
        "div",
        { class: "cmprow" },
        el("label", { class: "chk" }, cb, el("span", { text: c })),
      );
      if (cur) {
        const t = el("input", {
          type: "text",
          value: cur.name,
          maxlength: "60",
          "aria-label": `Nome de ${c} na legenda`,
        });
        t.addEventListener("input", () => {
          cur.name = t.value;
          preview();
        });
        row.append(t);
      }
      box.append(row);
    });
  }
  function comparePayload() {
    return { channels: S.cmp.map((x) => x.ch), names: S.cmp.map((x) => x.name) };
  }
  $("#modes").addEventListener("click", (e) => {
    const b = e.target.closest(".mode");
    if (!b) return;
    S.mode = b.dataset.m;
    $("#work-err").textContent = "";
    renderMode();
    preview();
  });

  function renderTabs() {
    const box = $("#tabs");
    box.replaceChildren();
    S.channels.forEach((c) => {
      const b = el("button", {
        class: "tab",
        type: "button",
        role: "tab",
        "aria-selected": String(c === S.active),
        text: c,
      });
      b.addEventListener("click", () => {
        S.active = c;
        renderTabs();
        preview();
      });
      box.append(b);
    });
  }

  function validLevels() {
    return S.levels.filter(
      (l) => l.start !== "" && l.end !== "" && !isNaN(num(l.start)) && !isNaN(num(l.end)),
    );
  }
  function levelsPayload() {
    return validLevels().map((l) => ({ label: l.label, start: num(l.start), end: num(l.end) }));
  }

  function renderLevels() {
    const box = $("#levels");
    box.replaceChildren();
    if (S.levels.length) {
      box.append(
        el(
          "div",
          { class: "lvhead" },
          el("span"),
          el("span", { text: "Nome" }),
          el("span", { text: "Início (min)" }),
          el("span", { text: "Fim (min)" }),
          el("span"),
        ),
      );
    } else {
      box.append(
        el("p", {
          class: "note",
          text: "Nenhum nível. Clique em “Detectar automaticamente” ou adicione um.",
        }),
      );
    }
    S.levels.forEach((l, i) => {
      const name = el("input", {
        type: "text",
        value: l.label,
        maxlength: "40",
        "aria-label": "Nome do nível",
      });
      const a = el("input", {
        type: "number",
        step: "0.1",
        value: l.start,
        "aria-label": "Início em minutos",
      });
      const b = el("input", {
        type: "number",
        step: "0.1",
        value: l.end,
        "aria-label": "Fim em minutos",
      });
      name.addEventListener("input", () => {
        l.label = name.value;
        preview();
      });
      name.addEventListener("change", renderDelta);
      a.addEventListener("input", () => {
        l.start = a.value;
        preview();
      });
      b.addEventListener("input", () => {
        l.end = b.value;
        preview();
      });
      const x = el("button", {
        class: "x",
        type: "button",
        "aria-label": "Remover nível",
        text: "×",
      });
      x.addEventListener("click", () => {
        S.levels.splice(i, 1);
        renderLevels();
        preview();
      });
      box.append(
        el(
          "div",
          { class: "lv" },
          el("span", { class: `dot dot-${i % LEVEL_COLORS.length}` }),
          name,
          a,
          b,
          x,
        ),
      );
    });
    renderDelta();
  }

  function renderDelta() {
    const n = validLevels().length;
    $("#deltabox").hidden = n < 2;
    if (n < 2) return;
    S.da = Math.min(S.da, n - 1);
    S.db = Math.min(S.db, n - 1);
    if (S.da === S.db) {
      S.da = 0;
      S.db = n - 1;
    }
    const vl = validLevels();
    for (const [id, key] of [
      ["#da", "da"],
      ["#db", "db"],
    ]) {
      const s = $(id);
      s.replaceChildren();
      vl.forEach((l, i) => s.append(el("option", { value: i, text: l.label || `Nível ${i + 1}` })));
      s.value = S[key];
    }
    $("#deltaon").checked = S.deltaOn;
    $("#deltasel").classList.toggle("off", !S.deltaOn);
  }
  $("#da").addEventListener("change", (e) => {
    S.da = +e.target.value;
  });
  $("#db").addEventListener("change", (e) => {
    S.db = +e.target.value;
  });
  $("#deltaon").addEventListener("change", (e) => {
    S.deltaOn = e.target.checked;
    renderDelta();
  });

  $("#addlevel").addEventListener("click", () => {
    if (S.levels.length >= 8) {
      $("#work-err").textContent = "No máximo 8 níveis.";
      return;
    }
    S.levels.push({ label: `Nível ${S.levels.length + 1}`, start: "", end: "" });
    renderLevels();
    const rows = document.querySelectorAll(".lv");
    rows[rows.length - 1].querySelectorAll("input")[1].focus();
  });
  $("#allch").addEventListener("click", () => {
    S.checked = new Set(S.channels);
    renderChannels();
  });

  $("#metric").addEventListener("change", async (e) => {
    S.metric = e.target.value;
    try {
      const j = await (await api("/api/channels", { token: S.token, metric: S.metric })).json();
      S.channels = j.channels;
      S.checked = new Set(j.channels);
      S.active = j.channels[0];
      S.cmp = [];
      renderChannels();
      renderTabs();
      renderMode();
      await autoDetect(true);
    } catch (err) {
      $("#work-err").textContent = err.message;
    }
  });

 
  async function autoDetect(silent) {
    $("#work-err").textContent = "";
    const btn = $("#detect");
    btn.disabled = true;
    try {
      const j = await (
        await api("/api/detect", { token: S.token, metric: S.metric, channels: [...S.checked] })
      ).json();
      S.levels = j.levels.map((l) => ({
        label: l.label,
        start: String(l.start),
        end: String(l.end),
      }));
      S.da = 0;
      S.db = Math.max(S.levels.length - 1, 0);
      renderLevels();
      if (!S.levels.length && !silent)
        $("#work-err").textContent = "Não achei níveis neste arquivo. Adicione manualmente.";
    } catch (e) {
      $("#work-err").textContent = e.message;
    }
    btn.disabled = false;
    preview();
  }
  $("#detect").addEventListener("click", () => autoDetect(false));

  
  let seq = 0,
    pvUrl = null;
  const preview = debounce(async () => {
    if (!S.token) return;
    const my = ++seq;
    const box = $("#previewbox");
    if (S.mode === "cmp" && S.cmp.length < 2) {
      $("#pvmsg").textContent = "Marque pelo menos 2 canais para comparar.";
      $("#pvmsg").hidden = false;
      $("#pv").hidden = true;
      return;
    }
    $("#pv").hidden = false;
    box.classList.add("loading");
    $("#spin").hidden = false;
    $("#pvmsg").hidden = true;
    try {
      const r = await api(
        "/api/preview",
        Object.assign(
          { token: S.token, metric: S.metric, channel: S.active, levels: levelsPayload() },
          S.mode === "cmp" ? { compare: comparePayload() } : {},
        ),
      );
      const blob = await r.blob();
      if (my !== seq) return;
      if (pvUrl) URL.revokeObjectURL(pvUrl);
      pvUrl = URL.createObjectURL(blob);
      $("#pv").src = pvUrl;
      $("#pv").hidden = false;
    } catch (e) {
      if (my !== seq) return;
      $("#pvmsg").textContent = e.message;
      $("#pvmsg").hidden = false;
    } finally {
      if (my === seq) {
        box.classList.remove("loading");
        $("#spin").hidden = true;
      }
    }
  }, 300);

  
  function renderFmt() {
    document.querySelectorAll(".fmt").forEach((b) => {
      const on = b.dataset.f === S.fmt;
      b.classList.toggle("on", on);
      b.setAttribute("aria-checked", String(on));
    });
    $("#gotxt").textContent = S.fmt === "xlsx" ? "Gerar Excel" : `Gerar gráfico ${FMT_NAME[S.fmt]}`;
    if (S.mode === "cmp") {
      $("#gotxt").textContent =
        S.fmt === "xlsx" ? "Gerar Excel da comparação" : `Gerar comparação ${FMT_NAME[S.fmt]}`;
      $("#fmtnote").textContent =
        S.fmt === "xlsx"
          ? "Excel com a aba Comparação (gráfico único, legendas editáveis), uma aba por canal e o Resumo."
          : `Um único gráfico com os canais escolhidos em ${FMT_NAME[S.fmt]}.`;
      return;
    }
    $("#fmtnote").textContent =
      S.fmt === "xlsx"
        ? "Excel completo: dados, fórmulas e gráfico, uma aba por canal, mais a aba Resumo."
        : `Só o gráfico em ${FMT_NAME[S.fmt]}. ` +
          (S.fmt === "pdf"
            ? "Vários canais: uma página por canal."
            : "Vários canais saem num ZIP, uma imagem por canal.");
  }
  $("#fmts").addEventListener("click", (e) => {
    const b = e.target.closest(".fmt");
    if (!b) return;
    S.fmt = b.dataset.f;
    renderFmt();
  });

 
  $("#go").addEventListener("click", async () => {
    const err = $("#work-err");
    err.textContent = "";
    const cmpMode = S.mode === "cmp";
    const sel = cmpMode ? S.cmp.map((x) => x.ch) : S.channels.filter((c) => S.checked.has(c));
    if (cmpMode && sel.length < 2) {
      err.textContent = "Marque pelo menos 2 canais para comparar.";
      return;
    }
    if (!sel.length) {
      err.textContent = "Marque pelo menos um canal.";
      return;
    }
    const incomplete = S.levels.length !== validLevels().length;
    if (incomplete) {
      err.textContent = "Preencha início e fim de todos os níveis (ou remova os vazios).";
      return;
    }
    const btn = $("#go");
    btn.disabled = true;
    const label = $("#gotxt").textContent;
    $("#gotxt").textContent = "Gerando…";
    try {
      const vl = validLevels();
      const body = {
        token: S.token,
        metric: S.metric,
        channels: sel,
        levels: levelsPayload(),
        format: S.fmt,
        pair:
          S.fmt === "xlsx" && S.deltaOn && vl.length >= 2 && S.da !== S.db ? [S.da, S.db] : null,
      };
      if (cmpMode) body.compare = comparePayload();
      const r = await api("/api/generate", body);
      const cd = r.headers.get("Content-Disposition") || "";
      const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)/i);
      const fname = m ? decodeURIComponent(m[1]) : "sensorgrama";
      const blob = await r.blob();
      if (S.downloadUrl) URL.revokeObjectURL(S.downloadUrl);
      S.downloadUrl = URL.createObjectURL(blob);
      const dl = $("#dl");
      dl.href = S.downloadUrl;
      dl.download = fname;
      $("#donefile").textContent = `${fname} · ${(blob.size / 1024).toFixed(0)} KB`;
      show("done");
      dl.click(); 
    } catch (e) {
      err.textContent = e.message;
    }
    btn.disabled = false;
    $("#gotxt").textContent = label;
  });

  $("#back").addEventListener("click", () => show("work"));
  $("#again").addEventListener("click", () => {
    S.token = null;
    show("home");
  });
  $("#change").addEventListener("click", () => {
    S.token = null;
    show("home");
  });
})();
