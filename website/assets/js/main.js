/* OminXOS website — progressive enhancement only. The page is fully usable
   with JavaScript disabled: content, navigation, and layout are static. */
(function () {
  "use strict";

  var reduceMotion =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var header = document.getElementById("site-header");
  var nav = document.getElementById("site-nav");
  var navToggle = document.querySelector(".nav-toggle");
  var navLinks = nav ? Array.prototype.slice.call(nav.querySelectorAll('a[href^="#"]')) : [];
  var sections = navLinks
    .map(function (link) {
      return document.getElementById(link.getAttribute("href").slice(1));
    })
    .filter(Boolean);

  function setNav(open) {
    document.body.classList.toggle("nav-open", open);
    if (navToggle) {
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");
      navToggle.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
    }
  }

  if (navToggle) {
    navToggle.addEventListener("click", function () {
      setNav(!document.body.classList.contains("nav-open"));
    });
  }

  navLinks.forEach(function (link) {
    link.addEventListener("click", function () {
      setNav(false);
    });
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && document.body.classList.contains("nav-open")) {
      setNav(false);
      if (navToggle) navToggle.focus();
    }
  });

  window.addEventListener("resize", function () {
    if (window.innerWidth > 1000) setNav(false);
  });

  function updateActiveSection() {
    if (!sections.length) return;
    var probe = window.scrollY + 150;
    var current = sections[0];
    sections.forEach(function (section) {
      if (section.offsetTop <= probe) current = section;
    });
    navLinks.forEach(function (link) {
      var isActive = link.getAttribute("href") === "#" + current.id;
      link.classList.toggle("is-active", isActive);
      if (isActive) {
        link.setAttribute("aria-current", "location");
      } else {
        link.removeAttribute("aria-current");
      }
    });
  }

  var scrollQueued = false;
  function onScroll() {
    if (scrollQueued) return;
    scrollQueued = true;
    window.requestAnimationFrame(function () {
      scrollQueued = false;
      if (header) header.classList.toggle("is-scrolled", window.scrollY > 8);
      updateActiveSection();
      revealInView();
    });
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* Reveal content as it enters the viewport. A scroll check backs up the
     observer so content is never left hidden after a fast jump or anchor link. */
  var revealItems = Array.prototype.slice.call(document.querySelectorAll("[data-reveal]"));
  var pendingReveals = [];

  function showItem(item) {
    item.classList.add("is-visible");
    var index = pendingReveals.indexOf(item);
    if (index !== -1) pendingReveals.splice(index, 1);
  }

  function revealInView() {
    if (!pendingReveals || !pendingReveals.length) return;
    var limit = window.innerHeight - 24;
    pendingReveals.slice().forEach(function (item) {
      if (item.getBoundingClientRect().top < limit) showItem(item);
    });
  }

  if (reduceMotion || !("IntersectionObserver" in window)) {
    revealItems.forEach(function (item) {
      item.classList.add("is-visible");
    });
  } else {
    var revealObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          showItem(entry.target);
          revealObserver.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -40px 0px", threshold: 0 }
    );
    revealItems.forEach(function (item) {
      pendingReveals.push(item);
      revealObserver.observe(item);
    });
    revealInView();
    window.addEventListener("resize", revealInView);
  }

  /* Count the compatibility figure up once, when it is on screen. */
  var counters = Array.prototype.slice.call(document.querySelectorAll("[data-count]"));

  function animateCount(element) {
    var target = parseInt(element.getAttribute("data-count"), 10);
    if (isNaN(target)) return;
    if (reduceMotion) {
      element.textContent = String(target);
      return;
    }
    var duration = 1300;
    var start = null;
    function step(timestamp) {
      if (start === null) start = timestamp;
      var progress = Math.min((timestamp - start) / duration, 1);
      var eased = 1 - Math.pow(1 - progress, 3);
      element.textContent = String(Math.round(target * eased));
      if (progress < 1) window.requestAnimationFrame(step);
    }
    window.requestAnimationFrame(step);
  }

  if (!("IntersectionObserver" in window)) {
    counters.forEach(function (element) {
      element.textContent = element.getAttribute("data-count");
    });
  } else {
    var countObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          animateCount(entry.target);
          countObserver.unobserve(entry.target);
        });
      },
      { threshold: 0.6 }
    );
    counters.forEach(function (element) {
      countObserver.observe(element);
    });
  }

  /* Subtle pointer parallax on the desktop illustration. */
  var preview = document.querySelector("[data-tilt]");
  var canTilt =
    preview &&
    !reduceMotion &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  if (canTilt) {
    var tiltX = 0;
    var tiltY = 0;
    var tiltQueued = false;
    preview.style.transformStyle = "preserve-3d";

    function paintTilt() {
      tiltQueued = false;
      preview.style.setProperty("--tilt-x", tiltX.toFixed(2) + "deg");
      preview.style.setProperty("--tilt-y", tiltY.toFixed(2) + "deg");
    }

    preview.addEventListener("pointermove", function (event) {
      var rect = preview.getBoundingClientRect();
      var offsetX = (event.clientX - rect.left) / rect.width - 0.5;
      var offsetY = (event.clientY - rect.top) / rect.height - 0.5;
      tiltY = offsetX * 5;
      tiltX = offsetY * -4;
      if (!tiltQueued) {
        tiltQueued = true;
        window.requestAnimationFrame(paintTilt);
      }
    });

    preview.addEventListener("pointerleave", function () {
      tiltX = 0;
      tiltY = 0;
      if (!tiltQueued) {
        tiltQueued = true;
        window.requestAnimationFrame(paintTilt);
      }
    });
  }
})();
