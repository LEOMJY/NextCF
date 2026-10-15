/* NextCF -- the landing page's script (ADR 0031, the ridge).
 *
 * The page is complete without this file: its words, the handle form and the
 * five sample problems are HTML, and the form is sent by the browser. Nothing
 * here touches the form. What this adds:
 *
 *   1. THE FIELD. Every problem that can be recommended, a dot each, with a
 *      ridge where rating alone gives a 50% chance, and the five standing on
 *      their own dots as poles with flags.
 *   2. THE AXIS. The field's front edge is a rating axis that can be held.
 *      Moving it re-picks the five here, in the browser, by the rule
 *      model.recommend() uses on the server.
 *   3. WORDS ARRIVING. The headline's lines rise once per visit, and the
 *      three statements below rise as they are scrolled to (GSAP).
 *
 * WHICH PICTURE A DEVICE GETS is spec section 7.1's three layers:
 *
 *   layer 1   no script at all: the HTML. Nothing of this file.
 *   layer 2   a STILL of the field, drawn once on a plain 2D canvas. For
 *             somebody whose system asks for less motion, a browser that
 *             cannot draw 3D, or one that says it is saving data. The 3D
 *             library is never downloaded.
 *   layer 3   the field in WebGL (three.js, 167 KB compressed, fetched only
 *             here and only after the page is on screen). Its frame rate is
 *             measured; under 30 it draws less, and still under 30 it steps
 *             down to layer 2.
 *
 * Layer 2 is drawn rather than being an image file, for two reasons. The
 * dots are data that changes every month (static/field.json), and a picture
 * of them would be out of date after every refresh. And the axis under the
 * field has to line up with it at every width, which a drawing made with the
 * same arithmetic does and a stretched image does not.
 *
 * Both layers share one camera (lens), one set of dot positions (scatter)
 * and one description of what is shown (shown, pins). Only the drawing
 * differs: flat() and live().
 */
(function () {
  "use strict";

  var root = document.documentElement;
  var blob = document.getElementById("ridge-data");
  if (!blob) return;
  var DATA;
  try {
    DATA = JSON.parse(blob.textContent);
  } catch (e) {
    return;
  }
  // From here on the stylesheet may show what only script can draw.
  root.classList.add("js");

  // ---------------------------------------------------------------- data
  // Everything below comes from the server's own constants (web.landing):
  // baseline.json's curve, model.DEFAULT_TARGET, model.BAND, web.SAMPLE_PACK
  // and web.RARITIES. Nothing about the model is written into this file.
  var CURVE = DATA.curve;
  var AIM = DATA.aim;                 // the chance a first plan aims at
  var BAND = DATA.band;               // how near the aim counts as "at" it
  var SAMPLE = DATA.sample;
  var SAMPLE_RATING = DATA.sampleRating;
  var RANKS = DATA.ranks;             // [{key, from, to}], lowest first
  var LOW = RANKS[0].from;            // 800: the lowest rating a problem has
  var HIGH = RANKS[RANKS.length - 1].to;   // 3500: the highest
  var FIELD = null;                   // static/field.json, once it arrives
  var RATINGS = [];

  function sigmoid(x) { return 1 / (1 + Math.exp(-x)); }

  // model.baseline_probability(): the chance from the two ratings alone.
  function chance(userRating, problemRating) {
    return sigmoid(CURVE.intercept + CURVE.slope * (userRating - problemRating) / CURVE.scale);
  }

  // model.recommend(): the five nearest the aim, newest contest first. Under
  // a rating-only curve every problem at one rating has the same chance, so
  // all five come from the one rating nearest the aim, and field.json keeps
  // the five newest at each rating for exactly this.
  function pickByRating(userRating) {
    var best = RATINGS[0], gap = 2;
    RATINGS.forEach(function (r) {
      var d = Math.abs(chance(userRating, r) - AIM);
      if (d < gap) { gap = d; best = r; }
    });
    var p = chance(userRating, best);
    return FIELD.newest[best].map(function (row) {
      return { contest: row[0], index: row[1], name: row[2], rating: best, p: p };
    });
  }

  // web.rarity(): the rank a rating would be.
  function rank(rating) {
    for (var i = 0; i < RANKS.length - 1; i++) {
      if (rating < RANKS[i].to) return RANKS[i].key;
    }
    return RANKS[RANKS.length - 1].key;
  }

  // ---------------------------------------------------------------- page
  var still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  // The page's head marks a first visit in this tab with the class
  // "arriving" and holds the headline back until the lines can rise
  // (index.html, style.css). Without the class this is a return visit, or
  // the three seconds ran out: either way nothing arrives, it is just there.
  var quiet = still || !root.classList.contains("arriving");
  var hasGsap = !!(window.gsap && window.ScrollTrigger && window.SplitText);
  if (hasGsap) gsap.registerPlugin(ScrollTrigger, SplitText);
  var EASE = "expo.out";      // fast out, slow to settle: the page's one curve
  // The stylesheet's narrow layout starts at this width ("the first screen
  // on a narrow page" in style.css), and the field is drawn differently in
  // it: bigger dots, fewer of them, taller poles. Asked with matchMedia, the
  // same question the stylesheet asks, so the two always agree -- the width
  // of the canvas alone would not, since a media query counts the scrollbar.
  var NARROW = window.matchMedia("(max-width: 960px)");

  var main = document.querySelector("main");
  var stage = document.getElementById("stage");
  var land = document.getElementById("land");
  var axis = document.getElementById("axis");
  var slider = document.getElementById("rating");
  var youTag = document.getElementById("you");
  var youPole = document.getElementById("you-pole");
  var youN = document.getElementById("you-n");
  var says = document.getElementById("five-says");
  var reset = document.getElementById("reset");
  var flagsBox = document.getElementById("flags");
  var list = document.querySelector(".five");
  var rows = Array.prototype.slice.call(document.querySelectorAll("#five a"));
  if (!main || !stage || !land || !axis || !slider || rows.length !== SAMPLE.length) {
    root.classList.remove("arriving");
    return;
  }
  var SLIDER_MIN = Number(slider.min), SLIDER_MAX = Number(slider.max), SLIDER_STEP = Number(slider.step) || 10;

  var state = { mode: "sample", rating: SAMPLE_RATING, five: SAMPLE, key: "sample" };
  var view = null;                    // the field, flat() or live(), once it is up

  var flags = SAMPLE.map(function () {
    var f = document.createElement("span");
    f.className = "flag";
    f.innerHTML = "<i></i><span></span>";
    flagsBox.appendChild(f);
    return f;
  });

  // Write five problems into the list's rows and onto the flags. The rows
  // exist already, drawn by the server with the sample in them; this only
  // changes what they say. textContent, never innerHTML: a problem's name is
  // somebody else's text.
  function fill(five) {
    five.forEach(function (prob, i) {
      var a = rows[i], cls = "rank-" + rank(prob.rating), pct = Math.round(prob.p * 100) + "%";
      a.className = cls + (a.classList.contains("is-hot") ? " is-hot" : "");
      a.href = "https://codeforces.com/problemset/problem/" + prob.contest + "/" + prob.index;
      a.querySelector(".id").textContent = prob.contest + prob.index;
      a.querySelector(".name").textContent = prob.name;
      a.querySelector(".rt").textContent = prob.rating;
      a.querySelector(".ch").textContent = pct;
      flags[i].className = "flag " + cls + (flags[i].classList.contains("is-hot") ? " is-hot" : "");
      flags[i].lastChild.textContent = prob.contest + prob.index + " " + pct;
    });
  }

  // The one place the page changes what it shows: the sample, or the five
  // that rating alone gives at `rating`.
  function show(mode, rating) {
    var five = mode === "sample" ? SAMPLE : pickByRating(rating);
    // Many ratings pick the same five (they share a nearest problem rating),
    // so the five only "change" when that rating does.
    var key = mode === "sample" ? "sample" : String(five[0].rating);
    var changed = key !== state.key;
    state.mode = mode; state.rating = rating; state.five = five; state.key = key;
    fill(five);
    youN.textContent = rating;
    // What a screen reader says for the slider. The slider moves in tens, so
    // on the sample its own value is 1490 while the flag, rightly, says the
    // history's real 1491; this makes the two say the same thing.
    slider.setAttribute("aria-valuetext", rating);
    says.textContent = "";
    if (mode === "sample") {
      says.appendChild(document.createTextNode("Sample: one real "));
      says.appendChild(bold(SAMPLE_RATING));
      says.appendChild(document.createTextNode("-rated history."));
    } else {
      says.appendChild(document.createTextNode("Rating alone at "));
      says.appendChild(bold(rating));
      says.appendChild(document.createTextNode(": everybody gets these five."));
    }
    reset.hidden = mode === "sample";
    if (changed && hasGsap && !still) {
      // What changed is the five: they step in, quickly, and a new drag
      // overwrites the one before it.
      gsap.fromTo(rows, { yPercent: 28, opacity: 0.2 },
        { yPercent: 0, opacity: 1, duration: 0.28, stagger: 0.025, ease: EASE, overwrite: true });
    }
    placeAxis();
    if (view) view.set(mode, rating, five, changed);
  }
  function bold(text) {
    var b = document.createElement("b");
    b.textContent = text;
    return b;
  }

  // A row and its flag light together, by mouse, finger or keyboard.
  rows.forEach(function (a, i) {
    function hot(on) {
      flags[i].classList.toggle("is-hot", on);
      if (view) view.hot();
    }
    a.addEventListener("pointerenter", function () { hot(true); });
    a.addEventListener("pointerleave", function () { hot(false); });
    a.addEventListener("focus", function () { hot(true); });
    a.addEventListener("blur", function () { hot(false); });
  });

  // ---------------------------------------------------------------- axis
  // Where a rating sits along the axis, in pixels from its left edge. The
  // field supplies the mapping once it is up (its own front edge); until
  // then the axis is simply its own width.
  var mapX = null;
  function xOf(r) {
    if (mapX) return mapX(r);
    return (r - LOW) / (HIGH - LOW) * axis.clientWidth;
  }
  function placeAxis() {
    var band = axis.querySelector(".ranks");
    // A rank's stretch starts half a step before its first rating, where
    // that rating's column of dots starts (a problem's rating is a round
    // hundred, and its dot is spread inside that hundred).
    var start = xOf(LOW - 50);
    band.style.left = start + "px";
    band.style.right = "auto";
    band.style.width = (xOf(HIGH + 50) - start) + "px";
    Array.prototype.forEach.call(band.children, function (seg) {
      var from = xOf(Number(seg.dataset.from) - 50) - start;
      var to = xOf(Number(seg.dataset.to) === HIGH ? HIGH + 50 : Number(seg.dataset.to) - 50) - start;
      seg.style.left = from + "px";
      seg.style.width = (to - from) + "px";
    });
    Array.prototype.forEach.call(axis.querySelectorAll(".ticks span"), function (t) {
      t.style.left = xOf(Number(t.dataset.r)) + "px";
    });
    // The slider's own thumb is invisible and as wide as the flag, so a
    // press anywhere on the flag holds it. A thumb's CENTRE travels from the
    // slider's lowest value to its highest, which is why the slider is laid
    // out one thumb wider than that stretch of the axis.
    var hold = Math.max(44, youTag.offsetWidth);
    axis.style.setProperty("--hold", hold + "px");
    slider.style.left = (xOf(SLIDER_MIN) - hold / 2) + "px";
    slider.style.width = (xOf(SLIDER_MAX) - xOf(SLIDER_MIN) + hold) + "px";
    var x = xOf(state.rating), w = youTag.offsetWidth / 2;
    youPole.style.left = x + "px";
    // The flag stays on the page at either end; the pole stays on the rating.
    youTag.style.left = Math.max(w, Math.min(axis.clientWidth - w, x)) + "px";
  }

  // ------------------------------------------------------- words arriving
  function countUp(el, to, delay) {
    var o = { v: 0 };
    gsap.to(o, { v: to, duration: 0.9, delay: delay, ease: "power3.out",
      onUpdate: function () { el.textContent = Math.round(o.v) + "%"; } });
  }
  function arrive() {
    // Read before the class goes: taking it off is what lets the headline
    // be seen, and the lines must already be under their masks by then,
    // which they are -- gsap.from() sets a starting state at once, and the
    // browser does not paint in the middle of a function.
    var play = hasGsap && !quiet && root.classList.contains("arriving");
    if (play) {
      // SplitText wraps each line of the headline in its own box, and
      // mask: "lines" gives each box a clipping parent, so a line starting
      // 105% below its place is hidden until it rises. autoSplit splits
      // again if the lines break differently (a font arriving, a resize),
      // and onSplit returns the animation so it can be carried over.
      SplitText.create("#headline", {
        type: "lines", mask: "lines", autoSplit: true,
        onSplit: function (self) {
          return gsap.from(self.lines, { yPercent: 105, duration: 1.0, stagger: 0.09, ease: EASE });
        }
      });
      gsap.from(".pitch > .lede, .pitch > .handle-form", { y: 18, opacity: 0, duration: 0.7, stagger: 0.08, delay: 0.25, ease: EASE });
      gsap.from("#five li", { y: 14, opacity: 0, duration: 0.6, stagger: 0.05, delay: 0.45, ease: EASE });
      rows.forEach(function (a, i) { countUp(a.querySelector(".ch"), Math.round(SAMPLE[i].p * 100), 0.5 + i * 0.05); });
    }
    root.classList.remove("arriving");
  }
  function scenes() {
    if (!hasGsap || still) return;
    // Each statement's lines rise as it is scrolled to, once.
    gsap.utils.toArray(".step").forEach(function (step) {
      SplitText.create(step.querySelector("h2"), {
        type: "lines", mask: "lines", autoSplit: true,
        onSplit: function (self) {
          return gsap.from(self.lines, {
            yPercent: 105, duration: 0.9, stagger: 0.08, ease: EASE,
            scrollTrigger: { trigger: step, start: "top 82%", once: true }
          });
        }
      });
      gsap.from(step.querySelector("p"), {
        y: 16, opacity: 0, duration: 0.7, delay: 0.15, ease: EASE,
        scrollTrigger: { trigger: step, start: "top 82%", once: true }
      });
    });
    // The field stands up as the first screen is scrolled away, and lies
    // back down when it is scrolled back: scrub ties it to the scroll's
    // position, not to time, so it is exactly as fast as the finger.
    ScrollTrigger.create({
      trigger: "#hero", start: "top top", end: "bottom top", scrub: true,
      onUpdate: function (self) { if (view) view.lift(self.progress); }
    });
  }
  // Lines are measured to be split, so the split waits for the real fonts:
  // split in a fallback face, a line would break somewhere else. But never
  // for long -- a font that is slow must not keep the headline hidden.
  var begun = false;
  function begin() {
    if (begun) return;
    begun = true;
    arrive();
    scenes();
    placeAxis();
  }
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(begin);
    window.setTimeout(begin, 1200);
  } else {
    begin();
  }

  // ------------------------------------------------------------ the data
  if (!window.fetch) { stage.classList.add("is-off"); return; }
  fetch(DATA.field).then(function (response) {
    if (!response.ok) throw new Error("field.json: " + response.status);
    return response.json();
  }).then(function (field) {
    FIELD = field;
    RATINGS = Object.keys(field.newest).map(Number).sort(function (a, b) { return a - b; });
    ready();
  }).catch(function () {
    // No data, no field and no axis: the page is its words, its form and
    // the sample, as it is without script.
    stage.classList.add("is-off");
  });

  function ready() {
    stage.classList.add("is-ready");
    fill(SAMPLE);
    placeAxis();
    window.addEventListener("resize", placeAxis);

    slider.addEventListener("input", function () { show("rating", Number(slider.value)); });
    reset.addEventListener("click", function () {
      slider.value = SAMPLE_RATING;
      show("sample", SAMPLE_RATING);
      slider.focus();
    });

    // Holding the field itself moves the rating: sideways only, so a finger
    // going up or down still scrolls the page (touch-action in style.css).
    var held = null;
    land.addEventListener("pointerdown", function (e) {
      if (e.button || !mapX) return;
      held = { x: e.clientX, rating: Number(slider.value), id: e.pointerId };
      land.classList.add("is-held");
    });
    window.addEventListener("pointermove", function (e) {
      if (!held || e.pointerId !== held.id) return;
      var perRating = (mapX(HIGH) - mapX(LOW)) / (HIGH - LOW);
      var next = Math.round((held.rating + (e.clientX - held.x) / perRating) / SLIDER_STEP) * SLIDER_STEP;
      next = Math.max(SLIDER_MIN, Math.min(SLIDER_MAX, next));
      if (next !== Number(slider.value)) { slider.value = next; show("rating", next); }
    });
    function letGo() { held = null; land.classList.remove("is-held"); }
    window.addEventListener("pointerup", letGo);
    window.addEventListener("pointercancel", letGo);

    var points = scatter(FIELD);

    // Spec 7.1's order. The first three stop at the still, and the 3D
    // library is not fetched at all.
    var saving = navigator.connection && navigator.connection.saveData;
    if (still || saving || !canDraw()) { settle(points); return; }

    // import() rather than a <script> tag: the browser fetches the file only
    // when this line runs, so a device that stopped above never pays for it.
    import(DATA.three).then(function (THREE) {
      view = live(THREE, points);
      land.classList.add("is-live");
      view.set(state.mode, state.rating, state.five, false);
      view.enter(quiet);
    }).catch(function () { settle(points); });
  }

  function canDraw() {
    try {
      var c = document.createElement("canvas");
      return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
    } catch (e) { return false; }
  }

  // Layer 2, from wherever it was decided. A canvas that has ever been given
  // a WebGL context cannot be given a 2D one, so the still gets a new canvas.
  function settle(points) {
    var old = document.getElementById("field");
    var fresh = old.cloneNode(false);
    old.parentNode.replaceChild(fresh, old);
    view = flat(points);
    land.classList.add("is-live");
    view.set(state.mode, state.rating, state.five, false);
    view.enter();
  }

  // ----------------------------------------------------- the field's world
  // One unit across is 100 rating. Every rating has its own hundred, from 50
  // under the lowest to 50 over the highest: 28 units, centred on zero.
  var HALF = (HIGH - LOW + 100) / 200;
  var DEPTH = 12;                     // front (newest contest) to back (contest 1)
  function wx(r) { return (r - (LOW + HIGH) / 2) / 100; }
  function wz(contest) { return -(FIELD.top - contest) / FIELD.top * DEPTH; }

  // Every problem's place, worked out once and used by both layers. Across:
  // its rating, spread a little inside the hundred it is rounded to, so a
  // rating is a band of dots and not a single line of them. Back: its
  // contest, newest in front. The spread comes from a seeded generator, not
  // Math.random(): the same dots stand in the same places on every visit
  // and on both layers.
  function scatter(field) {
    var n = field.count;
    var x = new Float32Array(n), z = new Float32Array(n), rate = new Float32Array(n), pick = new Float32Array(n);
    var seed = 20261004;
    function rnd() {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      var t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    }
    var i = 0;
    RATINGS.forEach(function (r) {
      var contest = 0;
      // "2269,3,0,12": the first number is a contest id and each one after
      // it is how far down the next id is (collect.write_field).
      field.field[r].split(",").forEach(function (gap, k) {
        if (i >= n) return;
        contest = k === 0 ? Number(gap) : contest - Number(gap);
        var at = r + (rnd() - 0.5) * 78;
        x[i] = wx(at); z[i] = wz(contest) - rnd() * 0.02; rate[i] = at; pick[i] = rnd();
        i++;
      });
    });
    return { n: i, x: x, z: z, rate: rate, pick: pick };
  }

  // What is shown, as numbers both layers read. `amp` is how far the ridge
  // has risen (0 to 1) and `show` how far back the dots have arrived; both
  // are 1 except during layer 3's entrance.
  var shown = { rating: SAMPLE_RATING, amp: 0, show: 0 };
  // The five. A pole stands where its problem's dot is and holds a flag.
  var pins = SAMPLE.map(function (prob) { return { x: 0, z: 0, rating: prob.rating, level: 0, grow: 0 }; });
  var optics = null;                  // the camera, from lens()

  // THE CAMERA. It looks level, from above the field, and the picture is
  // slid down until the field's front edge is the canvas's bottom edge --
  // what a photographer's shift lens does. Level, so every pole stands
  // upright on the screen and a flag sits square on its pole; a camera
  // tilted down would lean every pole away from the middle.
  //
  // Everything follows from two wishes: the front edge is exactly as wide as
  // the page between its margins, and the ground takes `tall` pixels of the
  // canvas. focal is how many pixels one unit covers at distance 1.
  function lens(w, h) {
    var compact = NARROW.matches;
    var gutter = parseFloat(getComputedStyle(main).paddingLeft) || 16;
    var perUnit = (w - 2 * gutter) / (2 * HALF);   // pixels per 100 rating, at the front edge
    var dist = DEPTH * 1.1;                        // the back edge comes out about half as wide as the front
    var focal = perUnit * dist;
    var tall = Math.min(h * (compact ? 0.4 : 0.44), 260);
    // On a wide page the right-hand block hangs down over the top of the
    // stage, and in a short window the far edge of the ground reached up
    // behind the last of the five (found at 1366 by 768, the commonest
    // laptop size: 42 pixels of dots under "Boarding Queue"). The ground
    // takes only the room there is under the list, down to a floor of 60:
    // a shallower field, never one with text lying on it. In a tall window
    // the room is more than the ground asks for and nothing changes.
    if (!compact && list) {
      var room = land.getBoundingClientRect().bottom - list.getBoundingClientRect().bottom - 12;
      tall = Math.max(60, Math.min(tall, room));
    }
    var eye = tall / (perUnit * (1 - dist / (dist + DEPTH)));
    return {
      compact: compact, gutter: gutter, perUnit: perUnit, dist: dist, focal: focal, eye: eye,
      // The screen row of everything at the camera's own height, however far.
      horizon: (h - 1) - perUnit * eye,
      dot: compact ? 0.16 : 0.058,                 // a dot's width, in units
      keep: compact ? 0.45 : 1,                    // fewer dots where each is bigger
      height: compact ? 2.8 : 1.7                  // how high the ridge stands, in units
    };
  }
  // The axis under the field is the field's own front edge.
  function edge(o, w) {
    var left = w / 2 + o.perUnit * wx(LOW) - o.gutter;
    var right = w / 2 + o.perUnit * wx(HIGH) - o.gutter;
    mapX = function (r) { return left + (r - LOW) / (HIGH - LOW) * (right - left); };
    placeAxis();
  }

  // How high the ridge is at a problem rating: a bell around the rating
  // whose chance is the aim, BAND wide. The same sum is in live()'s shader.
  function ridgeAt(rating, o) {
    var d = (chance(shown.rating, rating) - AIM) / BAND;
    return Math.exp(-0.5 * d * d) * shown.amp * o.height;
  }
  // Give each of the five its pole. Five heights, left to right, so flags on
  // neighbouring poles never cover each other.
  function stand(five, o) {
    var order = five.map(function (prob, i) { return { i: i, x: wx(prob.rating), z: wz(prob.contest) }; })
      .sort(function (a, b) { return a.x - b.x || b.z - a.z; });
    order.forEach(function (at, k) {
      var pin = pins[at.i];
      pin.x = at.x; pin.z = at.z; pin.rating = five[at.i].rating;
      pin.level = (o.compact ? 1.2 : 1.0) + k * (o.compact ? 1.45 : 0.62);
    });
    if (!o.compact) duck(o);
  }
  // ON A WIDE PAGE THE LIST HANGS OVER THE RIGHT OF THE STAGE, and five flags
  // on one pole are taller than the room under it. Moved towards the top
  // of its range, the five stand under the list, and at their full height
  // the top flags were drawn across its names (found 2026-10-12). So
  // poles that stand under the list are shortened to
  // end below it: the lowest keeps its place if it can, the rest are spaced
  // evenly up to the limit, and never closer than one flag's height, since
  // flags covering each other are worse than flags a little high. Poles
  // anywhere else are not touched.
  //
  // The sum is project() in flat() turned round: that gives the screen row
  // of a height, this gives the height that lands on a screen row.
  function duck(o) {
    if (!list) return;
    var landBox = land.getBoundingClientRect(), box = list.getBoundingClientRect();
    var under = [];
    pins.forEach(function (pin, i) {
      var d = o.dist - pin.z;
      var left = landBox.left + landBox.width / 2 + o.focal * pin.x / d;      // the pole, across the page
      if (left < box.right && left + flags[i].offsetWidth > box.left) under.push({ pin: pin, d: d });
    });
    if (!under.length) return;
    under.sort(function (a, b) { return a.pin.level - b.pin.level; });
    var top = under[under.length - 1];
    var flagTall = flags[0].offsetHeight || 18;
    // The row a pole's top may reach: the list's bottom edge, a gap, and
    // the flag that sits on the pole.
    var row = box.bottom - landBox.top + 10 + flagTall;
    // Where the ridge will be once the rating has settled, not where it is
    // in the middle of moving there.
    var bell = (chance(state.rating, top.pin.rating) - AIM) / BAND;
    var room = o.eye - (row - o.horizon) * top.d / o.focal - Math.exp(-0.5 * bell * bell) * o.height;
    if (top.pin.level <= room) return;
    var least = (flagTall + 1) * top.d / o.focal;      // one flag's height, in units
    var steps = under.length - 1;
    var lowest = Math.min(under[0].pin.level, Math.max(least * 0.5, room - least * steps));
    var step = steps ? Math.max(least, (room - lowest) / steps) : 0;
    under.forEach(function (u, k) { u.pin.level = lowest + k * step; });
  }
  function plant(i, at, grow) {
    flags[i].style.transform = "translate(" + at.x.toFixed(1) + "px," + at.y.toFixed(1) +
      "px) translateY(-100%) scale(" + (0.6 + 0.4 * grow).toFixed(3) + ")";
    flags[i].style.opacity = grow < 0.05 ? 0 : 1;
  }

  // ------------------------------------------------- layer 2: the still
  // The field drawn once with the browser's ordinary 2D canvas, and again
  // only when something changes (a resize, the rating moved). No library, no
  // animation. The camera is lens(); putting a point on the screen is two
  // lines of similar triangles (project), which is all a 3D library does
  // for a camera that is not tilted.
  function flat(points) {
    var canvas = document.getElementById("field");
    var ctx = canvas.getContext("2d");
    var ink = getComputedStyle(root).getPropertyValue("--ink").trim() || "#15130c";
    var w = 0, h = 0, dpr = 1, o = null;

    function project(x, y, z) {
      var d = o.dist - z;             // how far in front of the camera
      return { x: w / 2 + o.focal * x / d, y: o.horizon + o.focal * (o.eye - y) / d };
    }
    function line(x1, y1, z1, x2, y2, z2) {
      var a = project(x1, y1, z1), b = project(x2, y2, z2);
      ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
    }
    function fit() {
      w = land.clientWidth; h = land.clientHeight;
      if (!w || !h) return false;
      // A canvas has its own pixel count, separate from its size on the
      // page. On a screen with two device pixels per CSS pixel it needs
      // twice as many each way or everything on it is blurred.
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      o = optics = lens(w, h);
      edge(o, w);
      stand(state.five, o);
      return true;
    }
    function draw() {
      if (!o) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      ctx.strokeStyle = ink; ctx.fillStyle = ink; ctx.lineWidth = 1;

      // The ground: its front and back edges, and a line at each rank's
      // first rating.
      ctx.globalAlpha = 0.22;
      ctx.beginPath();
      line(-HALF, 0, 0, HALF, 0, 0); line(-HALF, 0, -DEPTH, HALF, 0, -DEPTH);
      RANKS.forEach(function (r) { var x = wx(r.from) - 0.5; line(x, 0, 0, x, 0, -DEPTH); });
      line(HALF, 0, 0, HALF, 0, -DEPTH);
      ctx.stroke();

      // The dots. Each is lifted by the ridge at its own rating, drawn
      // smaller the further back it is (the same division as its position),
      // and fainter with distance.
      var x = points.x, z = points.z, rate = points.rate, pick = points.pick;
      for (var i = 0; i < points.n; i++) {
        if (pick[i] > o.keep) continue;
        var bell = (chance(shown.rating, rate[i]) - AIM) / BAND;
        var ridge = Math.exp(-0.5 * bell * bell) * shown.amp;
        var d = o.dist - z[i];
        var far = -z[i] / DEPTH;
        ctx.globalAlpha = (1 - 0.5 * far) * (0.5 + 0.5 * ridge);
        ctx.beginPath();
        ctx.arc(w / 2 + o.focal * x[i] / d, o.horizon + o.focal * (o.eye - ridge * o.height) / d,
          Math.max(0.5, o.dot * (1 + 0.55 * ridge) * o.focal / d / 2), 0, 6.2832);
        ctx.fill();
      }

      // The visitor's own rating, a line from front to back; then the five.
      ctx.globalAlpha = 0.85;
      ctx.beginPath(); line(wx(shown.rating), 0, 0, wx(shown.rating), 0, -DEPTH); ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.beginPath();
      pins.forEach(function (pin, i) {
        var base = ridgeAt(pin.rating, o), top = base + pin.level * pin.grow;
        line(pin.x, base, pin.z, pin.x, top, pin.z);
        plant(i, project(pin.x, top, pin.z), pin.grow);
      });
      ctx.stroke();
    }
    // Several changes in one frame are one drawing: ten thousand dots is a
    // few milliseconds, and a drag sends many events between two frames.
    var asked = false;
    function ask() {
      if (asked) return;
      asked = true;
      requestAnimationFrame(function () { asked = false; draw(); });
    }

    fit();
    window.addEventListener("resize", function () { if (fit()) ask(); });

    return {
      set: function (mode, rating, five, changed) {
        shown.rating = rating;
        if (changed && o) stand(five, o);
        ask();
      },
      hot: function () {},
      lift: function () {},           // a still does not stand up with the scroll
      enter: function () {
        shown.amp = 1; shown.show = 1;
        pins.forEach(function (pin) { pin.grow = 1; });
        draw();
      }
    };
  }

  // ----------------------------------------------- layer 3: the live field
  function live(THREE, points) {
    var canvas = document.getElementById("field");
    var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
    renderer.setClearColor(0x000000, 0);
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    renderer.setPixelRatio(dpr);
    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(30, 2, 0.1, 200);
    var world = new THREE.Group();
    scene.add(world);
    var ink = new THREE.Color(getComputedStyle(root).getPropertyValue("--ink").trim() || "#15130c");
    var w = 0, h = 0, o = null;
    var keepCap = 1;                  // lowered by the frame-rate check, below
    var dead = false;                 // true once this layer has stepped down

    // One draw call for all the dots. Their places go to the graphics card
    // once; every frame only a handful of numbers change (the uniforms), and
    // the card works out each dot's height, size and strength itself -- the
    // vertex shader below is draw()'s loop in flat(), run on the card.
    var pos = new Float32Array(points.n * 3);
    for (var i = 0; i < points.n; i++) { pos[i * 3] = points.x[i]; pos[i * 3 + 2] = points.z[i]; }
    var geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("aRate", new THREE.BufferAttribute(points.rate.subarray(0, points.n), 1));
    geo.setAttribute("aPick", new THREE.BufferAttribute(points.pick.subarray(0, points.n), 1));
    var uni = {
      uRating: { value: SAMPLE_RATING }, uA: { value: CURVE.intercept }, uB: { value: CURVE.slope },
      uScale: { value: CURVE.scale }, uAim: { value: AIM }, uBand: { value: BAND },
      uAmp: { value: 0 }, uHeight: { value: 1.7 }, uDot: { value: 0.058 }, uPx: { value: 800 },
      uShow: { value: 0 }, uDepth: { value: DEPTH }, uKeep: { value: 1 }, uInk: { value: ink }
    };
    var material = new THREE.ShaderMaterial({
      uniforms: uni, transparent: true, depthWrite: false, depthTest: false,
      vertexShader: [
        "attribute float aRate; attribute float aPick;",
        "uniform float uRating, uA, uB, uScale, uAim, uBand, uAmp, uHeight, uDot, uPx, uShow, uDepth, uKeep;",
        "varying float vRidge; varying float vAlpha;",
        "void main() {",
        "  float p = 1.0 / (1.0 + exp(-(uA + uB * (uRating - aRate) / uScale)));",
        "  float d = (p - uAim) / uBand;",
        "  float ridge = exp(-0.5 * d * d) * uAmp;",
        "  vRidge = ridge;",
        "  vec3 at = position; at.y = ridge * uHeight;",
        "  vec4 mv = modelViewMatrix * vec4(at, 1.0);",
        "  gl_Position = projectionMatrix * mv;",
        "  float far = -position.z / uDepth;",
        "  float shown = clamp((uShow * 1.35 - far) / 0.35, 0.0, 1.0);",
        "  vAlpha = shown * mix(1.0, 0.5, far) * step(aPick, uKeep);",
        "  gl_PointSize = uDot * (1.0 + 0.55 * ridge) * uPx / -mv.z;",
        "}"
      ].join("\n"),
      fragmentShader: [
        "precision mediump float;",
        "uniform vec3 uInk; varying float vRidge; varying float vAlpha;",
        "void main() {",
        "  float d = length(gl_PointCoord - 0.5);",
        "  if (d > 0.5) discard;",
        "  float edge = smoothstep(0.5, 0.34, d);",
        "  gl_FragColor = vec4(uInk, edge * vAlpha * mix(0.5, 1.0, vRidge));",
        "}"
      ].join("\n")
    });
    var dots = new THREE.Points(geo, material);
    // three.js skips anything it works out to be off screen, from the places
    // it was given. The shader moves the dots after that sum is done.
    dots.frustumCulled = false;
    world.add(dots);

    function lines(coords, opacity) {
      var g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(coords), 3));
      var l = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: ink, transparent: true, opacity: opacity, depthTest: false }));
      l.frustumCulled = false;
      world.add(l);
      return l;
    }
    var grid = [-HALF, 0, 0, HALF, 0, 0, -HALF, 0, -DEPTH, HALF, 0, -DEPTH, HALF, 0, 0, HALF, 0, -DEPTH];
    RANKS.forEach(function (r) { var x = wx(r.from) - 0.5; grid.push(x, 0, 0, x, 0, -DEPTH); });
    lines(grid, 0.22);
    var mine = lines([0, 0, 0, 0, 0, -DEPTH], 0.85);
    var poles = lines(new Array(pins.length * 6).fill(0), 1);

    var v = new THREE.Vector3();
    function project(x, y, z) {
      v.set(x, y, z).applyMatrix4(world.matrixWorld).project(camera);
      return { x: (v.x * 0.5 + 0.5) * w, y: (-v.y * 0.5 + 0.5) * h };
    }

    function fit() {
      w = land.clientWidth; h = land.clientHeight;
      if (!w || !h) return;
      o = optics = lens(w, h);
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.clearViewOffset();
      camera.fov = 2 * Math.atan(h / 2 / o.focal) * 180 / Math.PI;
      camera.position.set(0, o.eye, o.dist);
      camera.lookAt(0, o.eye, 0);
      // The shift: a level camera puts its horizon in the middle of the
      // picture, and this slides the picture until it is on lens()'s row.
      camera.setViewOffset(w, h, 0, Math.round(h / 2 - o.horizon), w, h);
      camera.updateProjectionMatrix();
      camera.updateMatrixWorld();
      uni.uPx.value = o.focal * dpr;
      uni.uDot.value = o.dot;
      uni.uKeep.value = Math.min(o.keep, keepCap);
      uni.uHeight.value = o.height;
      edge(o, w);
      stand(state.five, o);
    }

    function frame() {
      mine.position.x = wx(shown.rating);
      uni.uRating.value = shown.rating;
      uni.uAmp.value = shown.amp;
      uni.uShow.value = shown.show;
      world.updateMatrixWorld();
      var arr = poles.geometry.attributes.position.array;
      pins.forEach(function (pin, i) {
        var base = ridgeAt(pin.rating, o), top = base + pin.level * pin.grow;
        arr.set([pin.x, base, pin.z, pin.x, top, pin.z], i * 6);
        plant(i, project(pin.x, top, pin.z), pin.grow);
      });
      poles.geometry.attributes.position.needsUpdate = true;
      renderer.render(scene, camera);
    }

    // DRAW ONLY WHILE SOMETHING IS MOVING. A field that stands still costs
    // nothing: no frame is drawn until something calls wake(), and the loop
    // stops by itself a moment after the last call.
    var until = 0, ticking = false;
    function wake(ms) {
      if (dead) return;
      until = Math.max(until, performance.now() + (ms || 600));
      if (!ticking) { ticking = true; requestAnimationFrame(loop); }
    }
    function loop(now) {
      if (dead) return;
      frame();
      measure(now);
      if (performance.now() < until) requestAnimationFrame(loop);
      else { ticking = false; meter.last = 0; }
    }

    // THE FRAME-RATE CHECK (spec 7.1, step 4). Over the first second of real
    // drawing: under 30 frames a second, draw less -- one device pixel per
    // CSS pixel and fewer than half the dots -- and measure a second time;
    // still under, give the picture up for the still.
    //
    // "Under 30" is tested as under 28. Some screens and power-saving modes
    // hold a page to exactly 30, which measures as 29.9 one second and 30.1
    // the next, and that is a device doing as it was told, not one that
    // cannot keep up. A gap of a quarter of a second between two frames is
    // not counted at all: that is a tab in the background, where the browser
    // stops calling, and says nothing about the device.
    var meter = { last: 0, frames: 0, time: 0, from: performance.now() + 300, stepped: false, done: false };
    function measure(now) {
      if (meter.done || document.hidden || now < meter.from) { meter.last = 0; return; }
      if (meter.last && now - meter.last < 250) { meter.frames++; meter.time += now - meter.last; }
      meter.last = now;
      if (meter.time < 1000) return;
      var fps = meter.frames / meter.time * 1000;
      meter.frames = 0; meter.time = 0;
      if (fps >= 28) { meter.done = true; return; }
      if (!meter.stepped) {
        meter.stepped = true;
        dpr = 1; renderer.setPixelRatio(1); keepCap = 0.45;
        fit();
        wake(1500);                   // long enough to be measured again
        return;
      }
      meter.done = true;
      retire();
    }
    function retire() {
      dead = true;
      window.removeEventListener("resize", onResize);
      if (hasGsap) { gsap.killTweensOf(shown); gsap.killTweensOf(pins); }
      geo.dispose(); material.dispose(); renderer.dispose();
      settle(points);
    }

    function onResize() { fit(); wake(100); }
    fit();
    window.addEventListener("resize", onResize);

    // Every tween keeps the field drawing for as long as it is still moving.
    function touch() { wake(200); }

    return {
      set: function (mode, rating, five, changed) {
        if (still || !hasGsap) { shown.rating = rating; } else {
          gsap.to(shown, { rating: rating, duration: 0.35, ease: "power3.out", overwrite: "auto", onUpdate: touch });
        }
        if (changed) {
          if (still || !hasGsap) { stand(five, o); pins.forEach(function (pin) { pin.grow = 1; }); } else {
            // The old five go down, the new five come up where they stand.
            gsap.to(pins, { grow: 0, duration: 0.12, ease: "power2.in", overwrite: true, onUpdate: touch,
              onComplete: function () {
                stand(five, o);
                gsap.to(pins, { grow: 1, duration: 0.45, stagger: 0.035, ease: EASE, overwrite: true, onUpdate: touch });
              } });
          }
        }
        wake(300);
      },
      hot: function () { wake(200); },
      lift: function (progress) { world.rotation.x = progress * 0.5; wake(200); },
      enter: function (quietly) {
        stand(state.five, o);
        if (quietly || !hasGsap) {
          shown.amp = 1; shown.show = 1;
          pins.forEach(function (pin) { pin.grow = 1; });
          // Nothing moves on a return visit, but the check above still needs
          // a second of drawing to measure.
          wake(1400);
          return;
        }
        // The problemset arrives front to back, the ridge rises out of it,
        // and the five stand up on their own dots.
        gsap.to(shown, { show: 1, duration: 1.3, ease: "power2.out", onUpdate: touch });
        gsap.to(shown, { amp: 1, duration: 1.1, delay: 0.5, ease: EASE, onUpdate: touch });
        gsap.to(pins, { grow: 1, duration: 0.7, delay: 0.9, stagger: 0.07, ease: EASE, onUpdate: touch });
        wake(300);
      }
    };
  }
})();
