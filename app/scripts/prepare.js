// Builds www/ and capacitor.config.json from app.config.json.
// Nothing here needs editing for normal changes: just edit /index.html
// (or app.config.json) in the repo and push.
const fs = require("fs");
const path = require("path");

const appDir = path.join(__dirname, "..");
const repoRoot = path.join(appDir, "..");
const cfg = JSON.parse(fs.readFileSync(path.join(appDir, "app.config.json"), "utf8"));

const www = path.join(appDir, "www");
fs.rmSync(www, { recursive: true, force: true });
fs.mkdirSync(www, { recursive: true });

for (const f of cfg.webFiles) {
  const src = path.join(repoRoot, f);
  if (!fs.existsSync(src)) throw new Error("Missing web file: " + f);
  const dest = path.join(www, f);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.cpSync(src, dest, { recursive: true });
}

const cap = {
  appId: cfg.appId,
  appName: cfg.appName,
  webDir: "www",
  server: { androidScheme: "https" }
};

// "remote" = the app just opens your live site, so UI updates on Cloudflare
// Pages reach the phone instantly with no new APK. "bundled" = index.html is
// packed inside the APK (works even if the site is down, but needs a new APK
// for every UI change).
if (cfg.mode === "remote") cap.server.url = cfg.remoteUrl;

fs.writeFileSync(path.join(appDir, "capacitor.config.json"), JSON.stringify(cap, null, 2));
console.log("Prepared", cfg.appName, "in", cfg.mode, "mode");
