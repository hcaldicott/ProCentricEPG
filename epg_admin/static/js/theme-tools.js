(function () {
  const storageKey = "epgAdminTheme";
  const validThemes = ["light", "dark"];

  function systemTheme() {
    if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }
    return "light";
  }

  function currentTheme() {
    const stored = window.localStorage.getItem(storageKey);
    if (validThemes.indexOf(stored) !== -1) {
      return stored;
    }
    return systemTheme();
  }

  function applyTheme(theme) {
    const nextTheme = validThemes.indexOf(theme) !== -1 ? theme : systemTheme();
    document.documentElement.setAttribute("data-theme", nextTheme);
    window.localStorage.setItem(storageKey, nextTheme);

    let renderIcons = false;
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      const dark = nextTheme === "dark";
      const label = dark ? "Switch to light mode" : "Switch to dark mode";
      const iconSlot = button.querySelector("[data-theme-icon]");
      const iconName = dark ? "sun" : "moon";
      button.setAttribute("aria-pressed", dark ? "true" : "false");
      button.setAttribute("aria-label", label);
      button.setAttribute("title", label);
      if (iconSlot) {
        if (iconSlot.getAttribute("data-current-icon") !== iconName) {
          iconSlot.setAttribute("data-current-icon", iconName);
          iconSlot.innerHTML = '<i data-lucide="' + iconName + '"></i>';
          renderIcons = true;
        } else if (iconSlot.querySelector("i[data-lucide]")) {
          renderIcons = true;
        }
      } else {
        button.textContent = dark ? "Light Mode" : "Dark Mode";
      }
    });

    if (renderIcons && window.lucide) {
      window.lucide.createIcons();
    }
  }

  function init() {
    applyTheme(currentTheme());
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      button.addEventListener("click", function () {
        applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
      });
    });
  }

  window.EPGThemeTools = {
    applyTheme: applyTheme,
    currentTheme: currentTheme,
    init: init,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
