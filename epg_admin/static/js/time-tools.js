(function () {
  const utcPattern = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2}) UTC$/;

  function parseUtcTimestamp(value) {
    const match = utcPattern.exec((value || "").trim());
    if (!match) {
      return null;
    }

    return new Date(Date.UTC(
      Number(match[1]),
      Number(match[2]) - 1,
      Number(match[3]),
      Number(match[4]),
      Number(match[5]),
      Number(match[6])
    ));
  }

  function formatLocalTimestamp(date) {
    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(date);
  }

  function addUtcTitle(element, rawValue) {
    const utcTitle = "UTC: " + rawValue;
    const currentTitle = element.getAttribute("title");
    if (currentTitle && currentTitle.indexOf(utcTitle) === -1) {
      element.setAttribute("title", currentTitle + "\n" + utcTitle);
      return;
    }
    element.setAttribute("title", utcTitle);
  }

  function renderLocalTimes(root) {
    const scope = root || document;
    scope.querySelectorAll("[data-utc-timestamp]").forEach(function (element) {
      const rawValue = element.getAttribute("data-utc-timestamp") || element.textContent;
      const date = parseUtcTimestamp(rawValue);
      if (!date) {
        return;
      }

      element.textContent = formatLocalTimestamp(date);
      if (element.tagName.toLowerCase() === "time") {
        element.setAttribute("datetime", date.toISOString());
      }
      addUtcTitle(element, rawValue);
    });
  }

  window.EPGTimeTools = {
    renderLocalTimes: renderLocalTimes,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      renderLocalTimes();
    });
  } else {
    renderLocalTimes();
  }
})();
