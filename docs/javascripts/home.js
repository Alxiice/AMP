/* Home page behaviour: reveal on scroll, screenshot tour, counters. No-op on other pages. */
(function () {
  const root = document.querySelector(".amp-hero");
  if (!root) return;
  document.body.classList.add("amp-home");
  document.documentElement.classList.add("js");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Reveal sections as they scroll in
  const reveal = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      e.target.classList.add("is-visible");
      reveal.unobserve(e.target);
    }
  }, { threshold: 0.15 });
  document.querySelectorAll(".amp-reveal").forEach((el) => reveal.observe(el));

  // Screenshot tour: tabs, auto-advance, pause on hover/focus
  const tour = document.querySelector(".amp-showcase");
  if (tour) {
    const tabs = [...tour.querySelectorAll(".amp-showcase__tab")];
    const frames = [...tour.querySelectorAll(".amp-showcase__frame")];
    const caption = tour.querySelector(".amp-showcase__caption");
    const interval = Number(tour.dataset.interval) || 5000;
    let current = 0;
    let timer = null;

    const show = (i) => {
      current = (i + tabs.length) % tabs.length;
      tabs.forEach((t, n) => {
        t.classList.toggle("is-active", n === current);
        t.setAttribute("aria-selected", String(n === current));
      });
      frames.forEach((f, n) => f.classList.toggle("is-active", n === current));
      caption.textContent = tabs[current].dataset.caption;
    };
    const start = () => {
      if (reduced) return;
      stop();
      timer = setInterval(() => show(current + 1), interval);
      tour.classList.remove("is-paused");
    };
    const stop = () => {
      clearInterval(timer);
      timer = null;
      tour.classList.add("is-paused");
    };

    tabs.forEach((t, n) => t.addEventListener("click", () => { show(n); start(); }));
    tour.addEventListener("mouseenter", stop);
    tour.addEventListener("mouseleave", start);
    tour.addEventListener("focusin", stop);
    tour.addEventListener("focusout", start);
    if (reduced) tour.classList.add("is-paused");

    // only run while visible
    new IntersectionObserver(([e]) => (e.isIntersecting ? start() : stop()), { threshold: 0.3 }).observe(tour);
  }

  // Tilt screenshots towards the cursor, like a plane pressed where the mouse is (the idea of
  // vanilla-tilt.js / Apple TV's parallax icons): rotation only, the centre doesn't move.
  const MAX_TILT = 8; // degrees at the edges
  if (!reduced && window.matchMedia("(hover: hover)").matches) {
    document.querySelectorAll("[data-tilt]").forEach((el) => {
      el.addEventListener("pointermove", (e) => {
        const r = el.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width - 0.5;  // -0.5 (left) … 0.5 (right)
        const y = (e.clientY - r.top) / r.height - 0.5;  // -0.5 (top) … 0.5 (bottom)
        el.classList.add("is-tilting");
        el.style.setProperty("--rx", `${(-y * 2 * MAX_TILT).toFixed(2)}deg`);
        el.style.setProperty("--ry", `${(x * 2 * MAX_TILT).toFixed(2)}deg`);
      });
      el.addEventListener("pointerleave", () => {
        el.classList.remove("is-tilting");
        el.style.setProperty("--rx", "0deg");
        el.style.setProperty("--ry", "0deg");
      });
    });
  }

  // Count the numbers up once they are on screen
  const counters = document.querySelectorAll("[data-count]");
  const countObs = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      countObs.unobserve(e.target);
      const el = e.target;
      const target = Number(el.dataset.count);
      const decimals = Number(el.dataset.decimals || 0);
      if (reduced || target === 0) continue;
      const t0 = performance.now();
      const step = (now) => {
        const p = Math.min(1, (now - t0) / 1400);
        const eased = 1 - Math.pow(1 - p, 3);
        el.textContent = (target * eased).toFixed(decimals);
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }
  }, { threshold: 0.6 });
  counters.forEach((el) => countObs.observe(el));
})();
