(() => {
  const $ = (id) => document.getElementById(id);
  const form = $("entry");
  if (!form) return;

  const state = { eligible: false, posterOk: false, posterFile: null };
  const A1 = { w: 594, h: 841 };

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function notice(kind, title, items = []) {
    const list = items.length ? `<ul>${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>` : "";
    return `<div class="notice ${kind}">${title ? `<strong>${esc(title)}</strong>` : ""}${list}</div>`;
  }

  function setLocked(id, locked) { $(id).classList.toggle("locked", locked); }
  function markDone(step, done) {
    const el = document.querySelector(`.step-num[data-step="${step}"]`);
    el.classList.toggle("done", done);
    el.textContent = done ? "✓" : step;
  }

  function wordCount() {
    const n = $("abstract").value.trim().split(/\s+/).filter(Boolean).length;
    const c = $("wordCount");
    c.textContent = `${n} / ${PORTAL.wordLimit} words`;
    c.classList.toggle("over", n > PORTAL.wordLimit);
    return n;
  }

  function detailsComplete() {
    const filled = ["department", "supervisor", "title", "abstract"].every((id) => $(id).value.trim());
    return filled && wordCount() <= PORTAL.wordLimit;
  }

  function refresh() {
    const details = state.eligible && detailsComplete();
    markDone(1, state.eligible);
    markDone(2, details);
    markDone(3, state.posterOk);
    setLocked("step2", !state.eligible);
    setLocked("step3", !state.eligible);
    setLocked("step4", !state.eligible);
    const ready = state.eligible && details && state.posterOk && $("declaration").checked;
    $("submitBtn").disabled = !ready;
    const missing = [];
    if (!state.eligible) missing.push("eligibility");
    else {
      if (!details) missing.push("research details");
      if (!state.posterOk) missing.push("a valid A1 poster");
      if (!$("declaration").checked) missing.push("the declaration");
    }
    $("submitHint").textContent = ready ? "Everything checks out." : `Still needed: ${missing.join(", ")}.`;
  }

  // Step 1: eligibility
  async function checkEligibility() {
    const btn = $("checkElig");
    btn.disabled = true;
    btn.textContent = "Checking…";
    try {
      const res = await fetch("/api/check/eligibility", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ student_id: $("student_id").value, email: $("email").value }),
      });
      const data = await res.json();
      state.eligible = data.eligible;
      $("eligResult").innerHTML = data.eligible
        ? notice("ok", `You're eligible, ${data.student.name.split(" ")[0]}.`, [`${data.student.programme} (${data.student.level})`])
        : notice("bad", "We can't accept an entry yet", data.errors);
    } catch {
      state.eligible = false;
      $("eligResult").innerHTML = notice("bad", "Couldn't reach the server. Try again in a moment.");
    } finally {
      btn.disabled = false;
      btn.textContent = "Check eligibility";
      refresh();
    }
  }
  $("checkElig").addEventListener("click", checkEligibility);
  ["student_id", "email"].forEach((id) => $(id).addEventListener("input", () => {
    if (state.eligible) { state.eligible = false; $("eligResult").innerHTML = ""; refresh(); }
  }));
  ["student_id", "email"].forEach((id) => $(id).addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); checkEligibility(); }
  }));

  // Step 2: details
  ["department", "supervisor", "title", "abstract"].forEach((id) => $(id).addEventListener("input", refresh));

  // Step 3: poster
  function sheetHtml(wmm, hmm) {
    const scale = 88 / Math.max(wmm, hmm, A1.h);
    const t = hmm >= wmm ? A1 : { w: A1.h, h: A1.w };
    return `<div class="sheet-wrap" aria-hidden="true">
      <div class="sheet" style="width:${wmm * scale}px;height:${hmm * scale}px"></div>
      <div class="sheet target" style="width:${t.w * scale}px;height:${t.h * scale}px"></div>
    </div>`;
  }

  function renderPoster(data, file) {
    const d = data.details || {};
    let measure = "";
    if (d.type === "pdf") {
      measure = `<div class="measure">${sheetHtml(d.width_mm, d.height_mm)}<dl>
        <dt>File</dt><dd>${esc(file.name)}</dd>
        <dt>Size</dt><dd>${d.width_mm} × ${d.height_mm} mm</dd>
        <dt>Target</dt><dd>A1 · 594 × 841 mm</dd>
        <dt>Layout</dt><dd>${d.orientation}</dd></dl></div>`;
    } else if (d.width_px) {
      const ratio = d.width_px / d.height_px;
      const w = d.width_px >= d.height_px ? 841 : 841 * ratio;
      const h = d.width_px >= d.height_px ? 841 / ratio : 841;
      measure = `<div class="measure">${sheetHtml(w, h)}<dl>
        <dt>File</dt><dd>${esc(file.name)}</dd>
        <dt>Pixels</dt><dd>${d.width_px} × ${d.height_px}</dd>
        <dt>Print quality</dt><dd>${d.print_dpi_at_a1} DPI at A1</dd>
        <dt>Layout</dt><dd>${d.orientation}</dd></dl></div>`;
    }
    const head = data.ok
      ? notice("ok", "Your poster is A1 and ready to submit.")
      : notice("bad", "This poster needs fixing before you can submit", data.errors);
    const warn = data.warnings && data.warnings.length ? notice("warn", "", data.warnings) : "";
    $("posterResult").innerHTML = head + warn + measure;
  }

  async function checkPoster(file) {
    state.posterOk = false;
    state.posterFile = null;
    refresh();
    if (!file) return;
    $("dropLabel").textContent = file.name;
    if (file.size > PORTAL.maxMb * 1024 * 1024) {
      $("posterResult").innerHTML = notice("bad", `This file is over ${PORTAL.maxMb} MB.`);
      return;
    }
    $("posterResult").innerHTML = notice("warn", "Checking poster size…");
    const body = new FormData();
    body.append("poster", file);
    try {
      const res = await fetch("/api/check/poster", { method: "POST", body });
      const data = await res.json();
      state.posterOk = !!data.ok;
      state.posterFile = data.ok ? file : null;
      renderPoster(data, file);
    } catch {
      $("posterResult").innerHTML = notice("bad", "Couldn't check this file. Try again.");
    }
    refresh();
  }

  const drop = $("drop");
  $("poster").addEventListener("change", (e) => checkPoster(e.target.files[0]));
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (file) checkPoster(file);
  });

  // Submit
  $("declaration").addEventListener("change", refresh);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if ($("submitBtn").disabled) return;
    const btn = $("submitBtn");
    btn.disabled = true;
    btn.textContent = "Submitting…";
    const body = new FormData();
    ["student_id", "email", "department", "supervisor", "title", "abstract"].forEach((id) => body.append(id, $(id).value));
    body.append("declaration", $("declaration").checked ? "on" : "");
    body.append("poster", state.posterFile);
    try {
      const res = await fetch("/api/submissions", { method: "POST", body });
      const data = await res.json();
      if (data.ok) {
        form.classList.add("hidden");
        $("doneName").textContent = `Thanks, ${data.name.split(" ")[0]}!`;
        $("doneRef").textContent = data.reference;
        $("done").classList.remove("hidden");
        window.scrollTo({ top: 0, behavior: "smooth" });
        return;
      }
      $("submitResult").innerHTML = notice("bad", "Your entry wasn't submitted", data.errors);
    } catch {
      $("submitResult").innerHTML = notice("bad", "Couldn't reach the server. Your entry wasn't submitted.");
    }
    btn.textContent = "Submit entry";
    refresh();
  });

  refresh();
})();
