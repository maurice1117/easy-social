(function () {
  function mediaKind(file) {
    if (file.type.startsWith("image/")) {
      return "image";
    }
    if (file.type.startsWith("video/")) {
      return "video";
    }

    const extension = file.name.split(".").pop().toLowerCase();
    if (["gif", "jpg", "jpeg", "png", "webp"].includes(extension)) {
      return "image";
    }
    if (["mov", "mp4", "ogg", "webm"].includes(extension)) {
      return "video";
    }
    return "";
  }

  function clearPreview(preview, frame, name, input, state) {
    if (state.objectUrl) {
      URL.revokeObjectURL(state.objectUrl);
      state.objectUrl = "";
    }
    frame.replaceChildren();
    name.textContent = "";
    preview.hidden = true;
    if (input) {
      input.value = "";
    }
  }

  function setupComposer(composer) {
    const input = composer.querySelector("[data-media-input]");
    const preview = composer.querySelector("[data-media-preview]");
    const frame = composer.querySelector("[data-media-preview-frame]");
    const name = composer.querySelector("[data-media-preview-name]");
    const clear = composer.querySelector("[data-media-preview-clear]");
    const pollEditor = composer.querySelector("[data-poll-editor]");
    const postTypes = composer.querySelectorAll("[data-post-type]");

    function syncPollEditor() {
      if (pollEditor) {
        const checkedType = composer.querySelector("[data-post-type]:checked");
        pollEditor.hidden = !checkedType || checkedType.value !== "poll";
      }
    }

    postTypes.forEach(function (postType) {
      postType.addEventListener("change", syncPollEditor);
    });
    syncPollEditor();

    if (!input || !preview || !frame || !name || !clear) {
      return;
    }

    const state = { objectUrl: "" };

    input.addEventListener("change", function () {
      const file = input.files && input.files[0];
      clearPreview(preview, frame, name, null, state);

      if (!file) {
        return;
      }

      const kind = mediaKind(file);
      if (!kind) {
        return;
      }

      state.objectUrl = URL.createObjectURL(file);
      const element = document.createElement(kind === "image" ? "img" : "video");
      element.className = "composer-preview-media";
      element.src = state.objectUrl;

      if (kind === "image") {
        element.alt = "Selected image preview";
      } else {
        element.controls = true;
        element.muted = true;
        element.preload = "metadata";
      }

      frame.replaceChildren(element);
      name.textContent = file.name;
      preview.hidden = false;
    });

    clear.addEventListener("click", function () {
      clearPreview(preview, frame, name, input, state);
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form.composer").forEach(setupComposer);
  });
})();
