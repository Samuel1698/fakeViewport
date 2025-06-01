import { fetchJSON } from "./_info.js";
export const CACHE_TTL = 60 * 15 * 1000; // 15 minutes
let updateCache = {
  timestamp: 0,
  data: null, // { current, latest, changelog, releaseUrl }
};
// ----------------------------------------------------------------------------- 
// Helper function
// ----------------------------------------------------------------------------- 
function cmpVersions(a, b) {
  const pa = a.split(".").map(Number),
    pb = b.split(".").map(Number);
  for (let i = 0, n = Math.max(pa.length, pb.length); i < n; i++) {
    const x = pa[i] || 0,
      y = pb[i] || 0;
    if (x > y) return 1;
    if (x < y) return -1;
  }
  return 0;
}
//  Fetch both /api/update and /api/update/changelog in parallel,
//  cache for an hour, return { current, latest, changelog, releaseUrl }
export async function loadUpdateData() {
  const now = Date.now();
  if (updateCache.data && now - updateCache.timestamp < CACHE_TTL) {
    return updateCache.data;
  }

  // parallel fetch
  const [verRes, logRes] = await Promise.all([
    fetchJSON("/api/update"),
    fetch("/api/update/changelog").then((r) => r.json()),
  ]);

  if (!verRes?.data) {
    throw new Error("Failed to fetch version info");
  }
  if (logRes.status !== "ok") {
    throw new Error("Failed to fetch changelog");
  }

  const { current, latest } = verRes.data;
  const { changelog, release_url: releaseUrl } = logRes.data;

  updateCache = {
    timestamp: now,
    data: { current, latest, changelog, releaseUrl },
  };
  return updateCache.data;
}
// Just reads from the cache populated by checkForUpdate()
// and populates your modal.
export function showChangelog() {
  const info = updateCache.data;
  if (!info) {
    console.error("No update data; did you call checkForUpdate()?");
    return;
  }
  const { latest, changelog, releaseUrl } = info;

  const title = document.querySelector("#update .container h2");
  if (latest.includes("failed-to-fetch")) {
    title.textContent = "Failed to Fetch Changelog";
  } else {
    title.textContent = `Release v${latest}`;
  }

  document.getElementById("changelog-body").innerHTML = marked.parse(changelog);
  document.getElementById("changelog-link").href = releaseUrl;
  document.getElementById("update").removeAttribute("hidden");
}
// ----------------------------------------------------------------------------- 
// Send command to apply update
// ----------------------------------------------------------------------------- 
export async function applyUpdate(btn) {
  const updateMessage = document.querySelector("#updateMessage span");
  const originalBtnText = btn.querySelector("span").textContent;
  const originalBtnDisabled = btn.disabled;

  // Reset message state
  updateMessage.textContent = "";
  updateMessage.className = "";
  btn.disabled = true;
  updateMessage.textContent = "Fetching Update...";
  updateMessage.classList.add("Green");
  try {
    // First check versions before attempting update
    const { current, latest } = await loadUpdateData();
    if (cmpVersions(latest, current) <= 0) {
      updateMessage.textContent = "✓ Your system is already up to date";
      updateMessage.classList.add("Green");
      btn.querySelector("span").textContent = "Up to date";
      btn.disabled = true; // Keep button disabled

      setTimeout(() => {
        updateMessage.textContent = "";
        updateMessage.className = "";
      }, 5000);
      return;
    }
    updateMessage.textContent = "Fetching Update...";
    updateMessage.classList.add("Green");

    // First API call - apply update
    const updateResponse = await fetch("/api/update/apply", { method: "POST" });

    if (!updateResponse.ok) {
      throw new Error(`Update failed with status ${updateResponse.status}`);
    }

    const updateData = await updateResponse.json();
    const outcome = updateData?.data?.outcome || updateData?.outcome;

    // Handle different outcome cases
    if (outcome === "already-current") {
      updateMessage.textContent = "✓ Your system is already up to date";
      updateMessage.classList.remove("Red");
      updateMessage.classList.add("Green");
      btn.querySelector("span").textContent = "Up to date";
      setTimeout(() => {
        btn.querySelector("span").textContent = originalBtnText;
        btn.disabled = originalBtnDisabled;
        updateMessage.textContent = "";
        updateMessage.className = "";
      }, 10_000);
      return;
    }

    // Handle successful updates
    if (outcome.startsWith("updated-to-")) {
      updateMessage.textContent =
        "✓ Update successful, preparing to restart...";
      updateMessage.classList.remove("Red");
      updateMessage.classList.add("Green");

      // Start restart sequence
      try {
        const [restartResponse, selfRestartResponse] = await Promise.all([
          fetch(`/api/control/restart`, { method: "POST" }),
          fetch(`/api/self/restart`, { method: "POST" }),
        ]);

        if (!restartResponse.ok || !selfRestartResponse.ok) {
          throw new Error("Restart commands failed");
        }

        const [restartData, selfRestartData] = await Promise.all([
          restartResponse.json(),
          selfRestartResponse.json(),
        ]);

        if (restartData.status === "ok" && selfRestartData.status === "ok") {
          updateMessage.textContent = "✓ System restarting...";
          setTimeout(() => location.reload(), 5000);
        } else {
          updateMessage.textContent =
            "✓ Update complete - please restart manually";
          btn.querySelector("span").textContent = "Restart required";
        }
      } catch (restartError) {
        updateMessage.textContent =
          "✓ Update complete - automatic restart failed";
        btn.querySelector("span").textContent = "Restart required";
        console.error("Restart failed:", restartError);
      }
    }
    // Handle failure case
    else if (outcome === "update-failed") {
      throw new Error("Update process failed");
    }
    // Unknown response
    else {
      throw new Error("Unexpected update response");
    }
  } catch (error) {
    console.error("Update failed:", error);
    updateMessage.classList.remove("Green");
    updateMessage.classList.add("Red");

    // More specific error messages
    if (error.message.includes("Failed to fetch")) {
      updateMessage.textContent =
        "✗ Network error - please check your connection";
    } else if (error.message.includes("Update process failed")) {
      updateMessage.textContent = "✗ Update failed - please try again";
    } else {
      updateMessage.textContent = "✗ Update error - please check logs";
    }

    // Revert button state
    btn.querySelector("span").textContent = "Retry";
    btn.disabled = false;
  }
}
// Call on page-load (and once per hour via setInterval)
// to reveal the banner if latest > current.
export async function checkForUpdate() {
  try {
    const { current, latest } = await loadUpdateData();
    const banner = document.getElementById("updateBtn");
    const updateButton = document.querySelector(
      '#update button[type="submit"]'
    );

    if (cmpVersions(latest, current) <= 0) {
      // Hide banner and disable button if already up-to-date
      if (banner) banner.setAttribute("hidden", "");
      if (updateButton) {
        updateButton.disabled = true;
        updateButton.querySelector("span").textContent = "Up to date";
      }
      return;
    }

    // Show banner and enable button if update available
    if (banner) banner.removeAttribute("hidden");
    if (updateButton) {
      updateButton.disabled = false;
      updateButton.querySelector("span").textContent = "Apply Update";
    }
  } catch (err) {
    console.error("Update check failed:", err);
  }
}
// Initialize the update button 
export function initUpdateButton() {
  const pushUpdate = document.querySelector('#update button[type="submit"]');
  if (pushUpdate) {
    pushUpdate.addEventListener("click", () => applyUpdate(pushUpdate));
    // Set initial state
    pushUpdate.disabled = true;
    pushUpdate.querySelector("span").textContent = "Checking...";
  }
}