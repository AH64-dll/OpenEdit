/* ==========================================================================
   Open Edit Guide — main.js (v2)
   Tiny modules:
   01 Theme toggle + persistence   02 Mobile menu
   03 Develop reveal on scroll     04 Hero timecode + playhead
   05 Copy buttons + toast         06 OS tabs
   07 Scrollspy                    08 FAQ accordion
   09 Helpers
   ========================================================================== */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ================= 09 · Helpers ================= */
  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function $$(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  /* ================= 02 · Mobile menu ================= */
  var menuBtn = document.getElementById("oe-menu-btn");
  var mobileMenu = document.getElementById("oe-mobile-menu");

  if (menuBtn && mobileMenu) {
    menuBtn.addEventListener("click", function () {
      var open = mobileMenu.classList.toggle("open");
      menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
      menuBtn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    });

    $$("a", mobileMenu).forEach(function (link) {
      link.addEventListener("click", function () {
        mobileMenu.classList.remove("open");
        menuBtn.setAttribute("aria-expanded", "false");
        menuBtn.setAttribute("aria-label", "Open menu");
      });
    });
  }

  /* ================= 03 · Develop reveal on scroll ================= */
  // Elements enter unexposed (grayscale + dim) and "develop" to full color.
  var revealEls = $$(".oe-reveal");

  if ("IntersectionObserver" in window && !reduceMotion) {
    var staggerRoots = $$(".oe-stagger");

    // Give each staggered child a small delay (75ms increments), then clear
    // the inline delay once the entrance finishes so hover/press transitions
    // on revealed cards are never delayed afterwards.
    staggerRoots.forEach(function (root) {
      $$(":scope > .oe-reveal", root).forEach(function (child, i) {
        child.style.transitionDelay = i * 75 + "ms";
        child.addEventListener("transitionend", function (e) {
          if (e.target === child && e.propertyName === "filter") {
            child.style.transitionDelay = "";
          }
        });
      });
    });

    // The hero print develops a beat after the headline, not with it.
    $$(".oe-hero-visual").forEach(function (v) {
      v.style.transitionDelay = "150ms";
      v.addEventListener("transitionend", function (e) {
        if (e.target === v && e.propertyName === "filter") {
          v.style.transitionDelay = "";
        }
      });
    });

    var revealObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("in-view");
            revealObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.05, rootMargin: "0px 0px -6% 0px" }
    );

    revealEls.forEach(function (el) {
      revealObserver.observe(el);
    });

    // The observer's bottom rootMargin can leave the final strip of the page
    // un-revealed at max scroll; force-reveal everything near the bottom.
    var pendingReveals = revealEls.slice();
    window.addEventListener(
      "scroll",
      function () {
        if (!pendingReveals.length) return;
        if (window.innerHeight + window.scrollY >= document.body.scrollHeight - 12) {
          pendingReveals.forEach(function (el) {
            el.classList.add("in-view");
          });
          pendingReveals = [];
        }
      },
      { passive: true }
    );
  } else {
    // Reduced motion or no observer support: show everything immediately.
    revealEls.forEach(function (el) {
      el.classList.add("in-view");
    });
  }

  /* ================= 04 · Hero timecode + playhead ================= */
  // The playhead scrubs a 15s timeline on an 8s CSS loop. The readout ticks
  // in sync, formatted MM:SS.cc like the product's 00:00.00.
  var timecodeEl = document.getElementById("oe-timecode");
  var LOOP_MS = 8000;
  var TIMELINE_SECONDS = 15;

  function formatTimecode(seconds) {
    var total = Math.min(Math.max(seconds, 0), TIMELINE_SECONDS);
    var mm = Math.floor(total / 60);
    var ss = Math.floor(total % 60);
    var cc = Math.floor((total - Math.floor(total)) * 100);
    function pad(n) {
      return n < 10 ? "0" + n : String(n);
    }
    return pad(mm) + ":" + pad(ss) + "." + pad(cc);
  }

  if (timecodeEl) {
    if (reduceMotion) {
      timecodeEl.textContent = "00:00.00";
    } else {
      var playheadEl = $(".oe-tl-playhead");
      // Start the CSS playhead animation from this exact moment so playhead
      // and timecode share one clock (no phase lag at loop wrap).
      if (playheadEl) {
        playheadEl.style.animation = "none";
        void playheadEl.offsetWidth;
        playheadEl.style.animation = "";
      }
      var t0 = performance.now();
      window.setInterval(function () {
        var elapsed = (performance.now() - t0) % LOOP_MS;
        timecodeEl.textContent = formatTimecode((elapsed / LOOP_MS) * TIMELINE_SECONDS);
      }, 80);

      // Background tabs freeze the (main-thread) playhead while the
      // performance.now()-driven timecode keeps up; restart both on return
      // so they stay phase-locked.
      document.addEventListener("visibilitychange", function () {
        if (document.visibilityState === "visible" && playheadEl) {
          t0 = performance.now();
          playheadEl.style.animation = "none";
          void playheadEl.offsetWidth; // restart the CSS animation
          playheadEl.style.animation = "";
        }
      });
    }
  }

  /* ================= 05 · Copy buttons + toast ================= */
  var toast = document.getElementById("oe-toast");
  var toastTimer = null;

  function showToast(message) {
    if (!toast) return;
    // Mutate the text node so the aria-live region actually announces.
    toast.textContent = "";
    toast.textContent = message || "Copied to clipboard";
    toast.classList.add("show");
    if (toastTimer) window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () {
      toast.classList.remove("show");
    }, 2000);
  }

  function stripPrompts(text) {
    return text.replace(/^(\$|PS>)\s*/gm, "").trim();
  }

  function fallbackCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    var ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (e) {
      ok = false;
    }
    document.body.removeChild(ta);
    return ok;
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).then(
        function () { return true; },
        function () { return fallbackCopy(text); }
      );
    }
    return Promise.resolve(fallbackCopy(text));
  }

  $$(".oe-copy[data-copy]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var target = document.getElementById(btn.getAttribute("data-copy"));
      if (!target) return;
      var text = stripPrompts(target.textContent);
      var label = $("span", btn);

      copyText(text).then(function (ok) {
        if (!ok) return;
        if (label) label.textContent = "Copied";
        btn.classList.add("copied");
        showToast();
        window.setTimeout(function () {
          btn.classList.remove("copied");
          if (label) label.textContent = "Copy";
        }, 1500);
      });
    });
  });

  /* ================= 06 · OS tabs ================= */
  function activateTab(tablist, name) {
    var tabs = $$('[role="tab"]', tablist);
    var panels = $$('[role="tabpanel"]', tablist.parentElement);

    tabs.forEach(function (tab) {
      var selected = tab.getAttribute("data-tab") === name;
      tab.setAttribute("aria-selected", selected ? "true" : "false");
      tab.setAttribute("tabindex", selected ? "0" : "-1");
    });

    panels.forEach(function (panel) {
      var linked = tablist.querySelector('[aria-controls="' + panel.id + '"]');
      var show = linked && linked.getAttribute("data-tab") === name;
      panel.hidden = !show;
      // Reveal elements inside a freshly shown panel that are already on screen.
      if (show) {
        $$(".oe-reveal", panel).forEach(function (el) {
          if (!el.classList.contains("in-view") && el.getBoundingClientRect().top < window.innerHeight) {
            el.classList.add("in-view");
          }
        });
      }
    });
  }

  $$("[data-tabs]").forEach(function (tabsRoot) {
    var tablist = $('[role="tablist"]', tabsRoot);
    if (!tablist) return;

    var tabs = $$('[role="tab"]', tablist);

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        activateTab(tablist, tab.getAttribute("data-tab"));
      });

      // Roving tabindex with arrow keys.
      tab.addEventListener("keydown", function (e) {
        var idx = tabs.indexOf(tab);
        var next = null;
        if (e.key === "ArrowRight") next = tabs[(idx + 1) % tabs.length];
        else if (e.key === "ArrowLeft") next = tabs[(idx - 1 + tabs.length) % tabs.length];
        if (next) {
          e.preventDefault();
          activateTab(tablist, next.getAttribute("data-tab"));
          next.focus();
        }
      });
    });
  });

  // Topbar CTAs deep-link into the install tabs.
  $$("[data-tab-open]").forEach(function (link) {
    link.addEventListener("click", function () {
      var name = link.getAttribute("data-tab-open");
      var tabsRoot = $("[data-tabs]");
      if (tabsRoot) {
        var tablist = $('[role="tablist"]', tabsRoot);
        if (tablist) activateTab(tablist, name);
      }
    });
  });

  /* ================= 07 · Scrollspy ================= */
  var navLinks = $$(".oe-nav a, .oe-mobile-menu a");
  var spySections = navLinks
    .map(function (link) {
      var hash = link.getAttribute("href");
      return hash && hash.charAt(0) === "#" ? document.getElementById(hash.slice(1)) : null;
    })
    .filter(Boolean);

  function setActive(id) {
    navLinks.forEach(function (link) {
      var hash = link.getAttribute("href");
      link.classList.toggle("active", hash === "#" + id);
    });
  }

  if ("IntersectionObserver" in window && spySections.length) {
    var spyObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) setActive(entry.target.id);
        });
      },
      { rootMargin: "-40% 0px -55% 0px", threshold: 0 }
    );
    spySections.forEach(function (section) {
      spyObserver.observe(section);
    });
  }

  /* ================= 08 · FAQ accordion ================= */
  var accRoot = document.getElementById("oe-acc");

  if (accRoot) {
    var accBtns = $$(".oe-acc-btn", accRoot);

    function closePanel(btn) {
      var panel = document.getElementById(btn.getAttribute("aria-controls"));
      btn.setAttribute("aria-expanded", "false");
      if (panel) panel.classList.remove("open");
    }

    function openPanel(btn) {
      var panel = document.getElementById(btn.getAttribute("aria-controls"));
      btn.setAttribute("aria-expanded", "true");
      if (panel) panel.classList.add("open");
    }

    accBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var isOpen = btn.getAttribute("aria-expanded") === "true";
        // One open at a time.
        accBtns.forEach(function (other) {
          if (other !== btn) closePanel(other);
        });
        if (isOpen) {
          closePanel(btn);
        } else {
          openPanel(btn);
        }
      });
    });
  }
})();
