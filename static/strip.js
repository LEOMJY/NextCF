/* NextCF -- the field over the five, on the results page (ADR 0031, the tool
 * pages, amended 2026-11-07).
 *
 * The landing page's field, drawn once and still: every rated problem a dot
 * (static/field.json), across by rating, back by contest with the newest in
 * front, lifted into a ridge where rating alone gives this visitor the chance
 * their five aim at. The five stand in it as poles with flags, each on its
 * own problem's dot -- so a 1300 and an 800 at 51% stand far apart, which is
 * the point of the model. A solved problem's flag turns green.
 *
 * Nothing here moves on its own: the tool pages move only to show that
 * something changed (spec section 7.1). The picture is redrawn when the
 * window changes size and when the island swaps the five; the one transition
 * is a flag's colour, in style.css.
 *
 * WHERE THE NUMBERS COME FROM. The curve, the band and the ranks are the
 * server's (web.strip_data), read where the landing page reads them. The
 * five, the visitor's rating and the aim are the island's (the same recs
 * the table is drawn from): first from the page's #topic-island-data, then
 * from the "nextcf:recs" event TopicIsland.jsx sends each time they change.
 *
 * The page is complete without this file. The figure stays hidden until it
 * has been drawn, so no script, or a field file that fails to arrive, leaves
 * nothing behind but the table that says everything the picture does.
 */
(function () {
  "use strict";

  var figure = document.getElementById("strip");
  var blob = document.getElementById("strip-data");
  var islandBlob = document.getElementById("topic-island-data");
  var canvas = document.getElementById("strip-field");
  if (!figure || !blob || !islandBlob || !canvas || !canvas.getContext) return;
  var DATA, recs;
  try {
    DATA = JSON.parse(blob.textContent);
    recs = JSON.parse(islandBlob.textContent).recs;
  } catch (e) {
    return;
  }

  var ctx = canvas.getContext("2d");
  var flagsBox = document.getElementById("strip-flags");
  var band = document.getElementById("strip-band");
  var edge = document.getElementById("strip-edge");
  var says = document.getElementById("strip-says");
  var island = document.getElementById("topic-island");

  var RANKS = DATA.ranks;                      // [{key, from, to}], lowest first
  var LOW = RANKS[0].from;                     // 800
  var HIGH = RANKS[RANKS.length - 1].to;       // 3500
  var HALF = (HIGH - LOW + 100) / 200;         // half the field's width, in units of 100 rating
  var DEPTH = 12;                              // front (newest contest) to back (contest 1)
  // The stylesheet's narrow layout starts here; asked the same way it asks.
  var NARROW = window.matchMedia("(max-width: 640px)");

  function sigmoid(x) { return 1 / (1 + Math.exp(-x)); }
  // model.baseline_probability(): the chance from the two ratings alone.
  function chance(userRating, problemRating) {
    return sigmoid(DATA.curve.intercept + DATA.curve.slope * (userRating - problemRating) / DATA.curve.scale);
  }
  // How high the ridge stands at a problem rating, 0 to 1: a bell around the
  // rating where rating alone gives the aim, BAND wide -- ridge.js's sum.
  function ridge(rating) {
    var d = (chance(recs.computed, rating) - recs.target / 100) / DATA.band;
    return Math.exp(-0.5 * d * d);
  }

  // ------------------------------------------------------- the field's world
  // One unit across is 100 rating, centred on zero; back is the contest.
  var TOP = 1;
  function wx(r) { return (r - (LOW + HIGH) / 2) / 100; }
  function wz(contest) { return -(TOP - contest) / TOP * DEPTH; }

  // Every problem's place, as ridge.js works it out: spread a little inside
  // the hundred its rating is rounded to, by a seeded generator, so the same
  // dots stand in the same places on every visit and on both pages.
  var points = null;
  function scatter(field) {
    var seed = 20261004, out = [];
    function rnd() {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      var t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    }
    Object.keys(field.field).map(Number).sort(function (a, b) { return a - b; }).forEach(function (r) {
      var contest = 0;
      // "2269,3,0,12": a contest id, then how far down each next id is.
      field.field[r].split(",").forEach(function (gap, k) {
        contest = k === 0 ? Number(gap) : contest - Number(gap);
        var at = r + (rnd() - 0.5) * 78;
        out.push({ x: wx(at), z: wz(contest) - rnd() * 0.02, rate: at, pick: rnd() });
      });
    });
    return out;
  }

  // ------------------------------------------------------------ the camera
  // Level, from above the field's front edge, which spans the canvas; how far
  // back the field reaches up the canvas is a share of its height. The same
  // projection as ridge.js's still, with this strip's proportions.
  var w = 0, h = 0, o = null;
  function lens() {
    var D = 30, f = (w / 2 - 6) * D / HALF;
    var front = h - 4, deep = h * (NARROW.matches ? 0.3 : 0.4);
    var E = deep / (f * (1 / D - 1 / (D + DEPTH)));
    return {
      D: D, f: f, E: E, horizon: front - f * E / D,
      lift: (h * 0.2) * D / f,                       // the ridge's height, in units
      keep: NARROW.matches ? 0.22 : 0.3              // the share of dots drawn: quieter than the landing page
    };
  }
  function project(x, y, z) {
    var d = o.D - z;
    return { x: w / 2 + o.f * x / d, y: o.horizon + o.f * (o.E - y) / d };
  }
  function frontX(r) { return project(wx(r), 0, 0).x; }

  // ------------------------------------------------------- what is drawn
  // A flag per problem, made as the five arrive and kept by id, so a flag
  // that turns green is the same element and its colour can change smoothly.
  var flags = {};
  function flagFor(problem) {
    var f = flags[problem.id];
    if (!f) {
      f = document.createElement("span");
      f.innerHTML = "<i></i><span></span>";
      flagsBox.appendChild(f);
      flags[problem.id] = f;
    }
    f.className = "flag" + (problem.rank ? " rank-" + problem.rank : "") + (problem.solved ? " solved" : "");
    // textContent: an id is short and ours, but nothing typed by anybody
    // else ever goes into innerHTML here.
    f.lastChild.textContent = problem.id + " " + problem.percent + "%";
    return f;
  }

  // The front edge, in HTML so its words are sharp: the rank colours, a few
  // ratings, and where the visitor is.
  RANKS.forEach(function (r) {
    var s = document.createElement("span");
    s.className = "rank-" + r.key; s.dataset.from = r.from; s.dataset.to = r.to;
    band.appendChild(s);
  });
  var TICKS = [LOW].concat(RANKS.slice(1).map(function (r) { return r.from; })).concat([HIGH]);
  TICKS.forEach(function (r) {
    var t = document.createElement("span");
    t.className = "strip-tick"; t.dataset.r = r; t.textContent = r;
    edge.appendChild(t);
  });
  var you = document.createElement("span");
  you.className = "strip-you";
  you.innerHTML = "<b></b>";
  edge.appendChild(you);

  function draw() {
    if (recs.state !== "ok" || !recs.problems || !recs.problems.length || recs.computed == null) {
      figure.hidden = true;
      return;
    }
    figure.hidden = false;
    w = canvas.clientWidth; h = canvas.clientHeight;
    if (!w || !h) return;
    // A canvas's own pixel count is separate from its size on the page: on a
    // screen with two device pixels per CSS pixel it needs twice as many.
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    o = lens();
    var ink = getComputedStyle(document.documentElement).getPropertyValue("--ink").trim() || "#15130c";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = ink; ctx.fillStyle = ink; ctx.lineWidth = 1;
    function line(x1, y1, z1, x2, y2, z2) {
      var a = project(x1, y1, z1), b = project(x2, y2, z2);
      ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
    }

    // The ground: its front and back edges, and a line where each rank starts.
    ctx.globalAlpha = 0.18;
    ctx.beginPath();
    line(-HALF, 0, 0, HALF, 0, 0); line(-HALF, 0, -DEPTH, HALF, 0, -DEPTH);
    RANKS.forEach(function (r) { var x = wx(r.from) - 0.5; line(x, 0, 0, x, 0, -DEPTH); });
    line(HALF, 0, 0, HALF, 0, -DEPTH);
    ctx.stroke();

    // The dots, lifted by the ridge at their rating; smaller and fainter
    // further back, lighter away from the ridge.
    points.forEach(function (p) {
      if (p.pick > o.keep) return;
      var lift = ridge(p.rate), d = o.D - p.z, far = -p.z / DEPTH;
      var q = project(p.x, lift * o.lift, p.z);
      ctx.globalAlpha = (1 - 0.6 * far) * (0.16 + 0.74 * lift);
      ctx.beginPath();
      ctx.arc(q.x, q.y, Math.max(0.5, 1.05 * (1 + 0.5 * lift) * o.D / d), 0, 6.2832);
      ctx.fill();
    });

    // The visitor's rating, a line from front to back.
    ctx.globalAlpha = 0.85;
    ctx.beginPath(); line(wx(recs.computed), 0, 0, wx(recs.computed), 0, -DEPTH); ctx.stroke();

    // The five: a pole on each one's own dot, a flag on top. The flags hang
    // at even steps, left to right, from one line -- the highest of the five
    // dots -- so two neighbours are always a whole step apart, however deep
    // their dots stand. Near the right edge a flag hangs to the left of its
    // pole instead of off the page.
    var shown = {};
    var order = recs.problems.map(function (p) {
      return { p: p, x: wx(p.rating), z: wz(p.contest || TOP) };
    }).sort(function (a, b) { return a.x - b.x || b.z - a.z; });
    var bases = order.map(function (at) { return project(at.x, ridge(at.p.rating) * o.lift, at.z); });
    var top = Math.min.apply(null, bases.map(function (b) { return b.y; }));
    var first = NARROW.matches ? 26 : 30, step = NARROW.matches ? 25 : 22;
    ctx.globalAlpha = 1; ctx.lineWidth = 1.5;
    ctx.beginPath();
    order.forEach(function (at, k) {
      var base = bases[k], y = top - (first + k * step);
      ctx.moveTo(base.x, base.y); ctx.lineTo(base.x, y);
      var f = flagFor(at.p), fw = f.offsetWidth;
      var left = base.x + fw > w - 2 ? base.x - fw : base.x;
      f.style.transform = "translate(" + left.toFixed(1) + "px," + y.toFixed(1) + "px) translateY(-100%)";
      shown[at.p.id] = true;
    });
    ctx.stroke();
    // Flags of problems no longer among the five go.
    Object.keys(flags).forEach(function (id) {
      if (!shown[id]) { flags[id].remove(); delete flags[id]; }
    });

    // The front edge's words, in line with the drawing.
    Array.prototype.forEach.call(band.children, function (s) {
      var to = Number(s.dataset.to), a = frontX(Number(s.dataset.from) - 50), b = frontX(to - 50 + (to === HIGH ? 100 : 0));
      s.style.left = a.toFixed(1) + "px"; s.style.width = Math.max(0, b - a).toFixed(1) + "px";
    });
    var youX = frontX(recs.computed);
    you.style.left = youX.toFixed(1) + "px";
    you.firstChild.textContent = "you " + recs.computed;
    Array.prototype.forEach.call(edge.querySelectorAll(".strip-tick"), function (t) {
      var r = Number(t.dataset.r);
      // A phone keeps the ends and every other boundary.
      t.hidden = NARROW.matches && [1400, 1900, 2100].indexOf(r) >= 0;
      if (t.hidden) return;
      var x = frontX(r === HIGH ? r : r - 50), half = t.offsetWidth / 2;
      x = Math.max(half, Math.min(w - half, x));
      t.style.left = x.toFixed(1) + "px";
      // A rating the "you" line would cross is left out.
      if (youX > x - half - 4 && youX < x + half + 4) t.hidden = true;
    });
    says.textContent = "Every rated problem on Codeforces is a dot, newest contests in front. " +
      "The ridge is where rating alone gives you " + recs.target + "%. Your five stand where they really are.";
  }

  // Several reasons to redraw in one frame are one drawing.
  var asked = false;
  function ask() {
    if (asked || !points) return;
    asked = true;
    requestAnimationFrame(function () { asked = false; draw(); });
  }

  // A row of the five and its flag point at each other: a pointer or the
  // keyboard on a row lights its flag. Listened for on the island, whose
  // rows React redraws; a row's id is "p-" and the problem's.
  function hot(row) {
    var id = row && row.id && row.id.indexOf("p-") === 0 ? row.id.slice(2) : null;
    Object.keys(flags).forEach(function (key) { flags[key].classList.toggle("is-hot", key === id); });
  }
  if (island) {
    island.addEventListener("pointerover", function (e) { hot(e.target.closest("tr")); });
    island.addEventListener("pointerleave", function () { hot(null); });
    island.addEventListener("focusin", function (e) { hot(e.target.closest("tr")); });
    island.addEventListener("focusout", function () { hot(null); });
  }

  // The island has swapped the five, or ticked one.
  window.addEventListener("nextcf:recs", function (e) {
    if (e.detail) { recs = e.detail; ask(); }
  });
  window.addEventListener("resize", ask);

  fetch(DATA.field).then(function (response) {
    if (!response.ok) throw new Error("HTTP " + response.status);
    return response.json();
  }).then(function (field) {
    TOP = field.top;
    points = scatter(field);
    draw();
    // The flags' widths depend on their font, which may still be arriving.
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(ask);
  }).catch(function () {
    // No field, no picture: the figure stays hidden and the table stands.
  });
})();
