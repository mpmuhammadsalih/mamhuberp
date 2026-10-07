document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("pdt-user-form");
  const usernameInput = document.getElementById("username");
  const usernameHint = document.getElementById("usernameHint");
  const checkUrl = form && form.getAttribute("data-check-url");
  if (!usernameInput || !usernameHint || !checkUrl) return;

  let checkTimer;
  usernameInput.addEventListener("input", () => {
    const value = usernameInput.value.trim();
    usernameHint.style.display = "none";
    usernameHint.textContent = "";
    if (checkTimer) clearTimeout(checkTimer);
    if (!value) return;
    checkTimer = setTimeout(() => {
      fetch(checkUrl + "?username=" + encodeURIComponent(value), { credentials: "same-origin" })
        .then((r) => r.json())
        .then((data) => {
          if (data.exists) {
            usernameHint.textContent = "Username already exists.";
            usernameHint.style.color = "#b91c1c";
            usernameHint.style.display = "block";
          }
        })
        .catch(() => {});
    }, 400);
  });
});
