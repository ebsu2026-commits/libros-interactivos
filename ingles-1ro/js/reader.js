(function () {
  "use strict";

  var state = {
    data: null,
    currentPage: 1,
    zonesVisible: false,
  };

  var els = {};

  function $(id) { return document.getElementById(id); }

  function init() {
    els.pageImage = $("pageImage");
    els.hotspotLayer = $("hotspotLayer");
    els.pageContainer = $("pageContainer");
    els.loadingMsg = $("loadingMsg");
    els.prevBtn = $("prevBtn");
    els.nextBtn = $("nextBtn");
    els.firstBtn = $("firstBtn");
    els.goBtn = $("goBtn");
    els.pageInput = $("pageInput");
    els.pageTotal = $("pageTotal");
    els.unitSelect = $("unitSelect");
    els.toggleZones = $("toggleZones");

    els.prevBtn.addEventListener("click", function () { goTo(state.currentPage - 1); });
    els.nextBtn.addEventListener("click", function () { goTo(state.currentPage + 1); });
    els.firstBtn.addEventListener("click", function () { goTo(1); });
    els.goBtn.addEventListener("click", function () { goTo(parseInt(els.pageInput.value, 10)); });
    els.pageInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") goTo(parseInt(els.pageInput.value, 10));
    });
    els.unitSelect.addEventListener("change", function () {
      var page = parseInt(els.unitSelect.value, 10);
      if (page) goTo(page);
    });
    els.toggleZones.addEventListener("click", function () {
      state.zonesVisible = !state.zonesVisible;
      els.pageContainer.classList.toggle("zones-visible", state.zonesVisible);
      els.toggleZones.classList.toggle("active", state.zonesVisible);
      els.toggleZones.textContent = state.zonesVisible ? "🔊 Ocultar zonas de audio" : "🔊 Ver zonas de audio";
    });

    document.addEventListener("keydown", function (e) {
      if (document.activeElement === els.pageInput) return;
      if (e.key === "ArrowLeft") goTo(state.currentPage - 1);
      if (e.key === "ArrowRight") goTo(state.currentPage + 1);
    });

    if (!window.BOOK_DATA) {
      els.loadingMsg.textContent = "No se pudo cargar el libro. Verifica que data/pages.js exista y que index.html lo incluya antes de reader.js.";
      return;
    }
    var data = window.BOOK_DATA;
    state.data = data;
    els.pageTotal.textContent = "/ " + data.totalPages;
    els.pageInput.max = data.totalPages;
    buildUnitSelect(data.units);
    var startPage = 1;
    var saved = parseInt(localStorage.getItem("libro-1ro-ing-page") || "1", 10);
    if (saved >= 1 && saved <= data.totalPages) startPage = saved;
    goTo(startPage);
  }

  function buildUnitSelect(units) {
    var frag = document.createDocumentFragment();
    var optAll = document.createElement("option");
    optAll.value = "";
    optAll.textContent = "— Ir a unidad —";
    frag.appendChild(optAll);
    units.forEach(function (u) {
      var opt = document.createElement("option");
      opt.value = u.page;
      opt.textContent = "Unidad " + u.unit;
      frag.appendChild(opt);
    });
    els.unitSelect.appendChild(frag);
  }

  function goTo(pageNo) {
    if (!state.data) return;
    pageNo = Math.max(1, Math.min(state.data.totalPages, pageNo || 1));
    state.currentPage = pageNo;
    localStorage.setItem("libro-1ro-ing-page", String(pageNo));
    renderPage(pageNo);
  }

  function renderPage(pageNo) {
    stopAudio();
    var page = state.data.pages[pageNo - 1];
    els.loadingMsg.classList.remove("hidden");
    els.pageImage.onload = function () { els.loadingMsg.classList.add("hidden"); };
    els.pageImage.src = page.image;
    els.pageInput.value = pageNo;
    els.prevBtn.disabled = pageNo <= 1;
    els.nextBtn.disabled = pageNo >= state.data.totalPages;

    els.hotspotLayer.innerHTML = "";
    page.blocks.forEach(function (b) {
      if (!b.speak) return;
      var left = (b.bbox[0] / page.width) * 100;
      var top = (b.bbox[1] / page.height) * 100;
      var width = ((b.bbox[2] - b.bbox[0]) / page.width) * 100;
      var height = ((b.bbox[3] - b.bbox[1]) / page.height) * 100;
      var div = document.createElement("div");
      div.className = "hotspot";
      div.style.left = left + "%";
      div.style.top = top + "%";
      div.style.width = width + "%";
      div.style.height = height + "%";
      div.title = b.text;
      div.addEventListener("click", function () { speak(b, div); });
      els.hotspotLayer.appendChild(div);
    });

    // sync unit dropdown with current page range
    var units = state.data.units;
    var current = "";
    for (var i = 0; i < units.length; i++) {
      if (pageNo >= units[i].page) current = String(units[i].page);
    }
    els.unitSelect.value = current;
  }

  // Strips leading list markers ("1.", "a)", "F.", etc.) so a numbered/lettered
  // zone speaks only its content, not the marker — applies at the start of the
  // text and after any inner whitespace, so "a) Serious b) Funny" -> "Serious Funny".
  // ".M."-style abbreviations (a.m., U.S.) never match: the marker's punctuation
  // must be followed by whitespace, which those don't have.
  function cleanForSpeech(text) {
    return text
      .replace(/(^|\s)(\d{1,3}|[a-zA-Z])[.)]\s+/g, "$1")
      .replace(/\s+/g, " ")
      .trim();
  }

  // Pre-baked neural-voice MP3s (see tools/build.py) are the primary path — same
  // audio every time, fully offline, no dependency on voices installed on the
  // viewing machine. speechSynthesis is only a fallback for a block that somehow
  // has no "audio" file yet (e.g. a page added before the next audio rebuild).
  function stopAudio() {
    if (state.audioEl) {
      state.audioEl.pause();
      state.audioEl.currentTime = 0;
    }
    window.speechSynthesis && window.speechSynthesis.cancel();
    document.querySelectorAll(".hotspot.speaking").forEach(function (n) { n.classList.remove("speaking"); });
  }

  function speak(block, el) {
    stopAudio();
    el.classList.add("speaking");

    if (block.audio) {
      if (!state.audioEl) state.audioEl = new Audio();
      var audioEl = state.audioEl;
      audioEl.onended = function () { el.classList.remove("speaking"); };
      audioEl.onerror = function () {
        el.classList.remove("speaking");
        speakViaSystemVoice(block.text, el);
      };
      audioEl.src = block.audio;
      audioEl.play().catch(function () {
        el.classList.remove("speaking");
        speakViaSystemVoice(block.text, el);
      });
      return;
    }

    speakViaSystemVoice(block.text, el);
  }

  function speakViaSystemVoice(text, el) {
    if (!window.speechSynthesis) { el.classList.remove("speaking"); return; }
    var spoken = cleanForSpeech(text) || text;
    var utter = new SpeechSynthesisUtterance(spoken);
    utter.lang = (state.data && state.data.lang === "fr") ? "fr-FR" : "en-US";
    utter.rate = 0.95;
    el.classList.add("speaking");
    utter.onend = function () { el.classList.remove("speaking"); };
    utter.onerror = function () { el.classList.remove("speaking"); };
    window.speechSynthesis.speak(utter);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
