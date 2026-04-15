(function () {
  "use strict";

  function initPasswordGenerator(config) {
    const passwordInput = document.getElementById(config.passwordInputId);
    const generateButton = document.getElementById(config.generateButtonId);
    const toastController = window.EPGToast
      ? window.EPGToast.createController({
          toastId: config.toastId,
          closeButtonId: config.toastCloseId,
          messageNodeId: config.toastMessageId,
          timeoutMs: config.toastTimeoutMs,
        })
      : null;

    if (!passwordInput || !generateButton || !toastController) {
      return;
    }

    function generatePassword(length) {
      const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
      const randomValues = new Uint32Array(length);
      window.crypto.getRandomValues(randomValues);
      let out = "";
      for (let i = 0; i < length; i += 1) {
        out += chars[randomValues[i] % chars.length];
      }
      return out;
    }

    generateButton.addEventListener("click", async function () {
      const password = generatePassword(22);
      passwordInput.type = "text";
      passwordInput.value = password;
      passwordInput.dataset.generated = "1";

      try {
        await navigator.clipboard.writeText(password);
        toastController.show("Generated password copied to clipboard.", "is-success");
      } catch (err) {
        toastController.show("Generated password ready. Copy failed, copy manually.", "is-danger");
      }
    });

    passwordInput.addEventListener("input", function (event) {
      if (passwordInput.dataset.generated === "1" && event.isTrusted) {
        passwordInput.dataset.generated = "0";
        passwordInput.type = "password";
      }
    });
  }

  window.EPGPasswordTools = {
    initPasswordGenerator: initPasswordGenerator,
  };
})();
