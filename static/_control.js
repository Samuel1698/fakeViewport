import { loadInfo } from "./_info.js";

// send control and update inline message
export async function control(action) {
  const msgEls = document.querySelectorAll(".statusMessage span");
  msgEls.forEach((el) => {
    el.textContent = "";
    el.classList.remove("Green", "Red");
  });
  try {
    const res = await fetch(`/api/control/${action}`, { method: "POST" });
    const js = await res.json();

    if (js.status === "ok") {
      msgEls.forEach((el) => {
        el.textContent = "✓ " + js.message;
        el.classList.add("Green");
      });
    } else {
      msgEls.forEach((el) => {
        el.textContent = "✗ " + js.message;
        el.classList.add("Red");
      });
    }
    await loadInfo();
    // reset the message after 15 seconds
    setTimeout(() => {
      msgEls.forEach((el) => {
        el.textContent = "";
        el.classList.remove("Green", "Red");
      });
    }, 5_000);
    setTimeout(loadInfo, 5_000);
  } catch (e) {
    msgEls.forEach((el) => {
      el.textContent = "✗ " + e;
      el.classList.add("Red");
    });
  }
}
