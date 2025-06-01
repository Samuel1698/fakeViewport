import { loadInfo } from "./_info.js";

// send control and update inline message
export async function control(action, btn) {
  // disable the button immediately
  btn.setAttribute("disabled", "");
  setTimeout(() => {
    btn.removeAttribute("disabled");
  }, 5_000);

  const msgEl = document.querySelector("#statusMessage span");
  msgEl.textContent = "";
  msgEl.classList.remove("Green", "Red");
  try {
    const res = await fetch(`/api/control/${action}`, { method: "POST" });
    const js = await res.json();

    if (js.status === "ok") {
      msgEl.textContent = "✓ " + js.message;
      msgEl.classList.add("Green");
    } else {
      msgEl.textContent = "✗ " + js.message;
      msgEl.classList.add("Red");
    }
    await loadInfo();
    // reset the message after 15 seconds
    setTimeout(() => {
      msgEl.textContent = "";
      msgEl.classList.remove("Green", "Red");
    }, 5_000);
    setTimeout(loadInfo, 5_000);
  } catch (e) {
    msgEl.textContent = "✗ " + e;
    msgEl.classList.add("Red");
  }
}
