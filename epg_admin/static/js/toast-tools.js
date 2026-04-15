(function () {
  "use strict";

  const DEFAULT_TIMEOUT_MS = 6000;
  const DEFAULT_BASE_BOTTOM_REM = 1;
  const DEFAULT_STACK_GAP_REM = 5.5;

  function createController(config) {
    const toast = document.getElementById(config.toastId);
    const closeButton = document.getElementById(config.closeButtonId);
    const messageNode = config.messageNodeId ? document.getElementById(config.messageNodeId) : null;
    const timeoutMs = Number(config.timeoutMs) > 0 ? Number(config.timeoutMs) : DEFAULT_TIMEOUT_MS;
    let timer = null;

    if (!toast || !closeButton) {
      return null;
    }

    function clearTimer() {
      if (timer) {
        window.clearTimeout(timer);
        timer = null;
      }
    }

    function hide() {
      toast.classList.add("is-hidden");
      clearTimer();
    }

    function show(message, tone) {
      if (messageNode && typeof message === "string") {
        messageNode.textContent = message;
      }

      toast.classList.remove("is-hidden", "is-success", "is-danger", "is-warning", "is-info");
      if (tone) {
        toast.classList.add(tone);
      }

      clearTimer();
      timer = window.setTimeout(hide, timeoutMs);
    }

    closeButton.addEventListener("click", hide);

    return {
      show: show,
      hide: hide,
    };
  }

  function initStackedToasts(selector, config) {
    const toasts = document.querySelectorAll(selector);
    const closeSelector = (config && config.closeSelector) || ".delete";
    const timeoutMs =
      config && Number(config.timeoutMs) > 0 ? Number(config.timeoutMs) : DEFAULT_TIMEOUT_MS;
    const baseBottomRem =
      config && Number(config.baseBottomRem) >= 0
        ? Number(config.baseBottomRem)
        : DEFAULT_BASE_BOTTOM_REM;
    const stackGapRem =
      config && Number(config.stackGapRem) > 0 ? Number(config.stackGapRem) : DEFAULT_STACK_GAP_REM;

    toasts.forEach(function (toast, index) {
      const closeButton = toast.querySelector(closeSelector);
      let timer = null;

      function clearTimer() {
        if (timer) {
          window.clearTimeout(timer);
          timer = null;
        }
      }

      function hide() {
        toast.classList.add("is-hidden");
        clearTimer();
      }

      if (closeButton) {
        closeButton.addEventListener("click", hide);
      }

      toast.style.bottom = (baseBottomRem + index * stackGapRem) + "rem";
      clearTimer();
      timer = window.setTimeout(hide, timeoutMs);
    });
  }

  window.EPGToast = {
    createController: createController,
    initStackedToasts: initStackedToasts,
    DEFAULT_TIMEOUT_MS: DEFAULT_TIMEOUT_MS,
  };
})();
