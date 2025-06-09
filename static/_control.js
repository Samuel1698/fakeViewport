import { stopLogsAutoRefresh, startLogsAutoRefresh } from "./_logs.js";
import { isDesktopView } from "./_sections.js";

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
    if (isDesktopView() && action != "quit"){
      stopLogsAutoRefresh();
      startLogsAutoRefresh(1_000);
    }
    // reset the message after 5 seconds
    setTimeout(() => {
      msgEls.forEach((el) => {
        el.textContent = "";
        el.classList.remove("Green", "Red");
        if (isDesktopView() && action != "quit") {
          stopLogsAutoRefresh();
          startLogsAutoRefresh();
        }
      });
    }, 15_000);
  } catch (e) {
    msgEls.forEach((el) => {
      el.textContent = "✗ " + e;
      el.classList.add("Red");
    });
  }
}
