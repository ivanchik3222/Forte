// Run from the repository when the ML registry changes. The committed snapshot
// keeps standalone frontend/Docker builds independent of the ML directory.
const fs = require("node:fs");
const path = require("node:path");
const source = path.resolve(__dirname, "../../ML/regulations/rules_v1.json");
const target = path.resolve(__dirname, "../src/data/regulations.json");
const registry = JSON.parse(fs.readFileSync(source, "utf8"));
fs.writeFileSync(target, JSON.stringify(registry, null, 2) + "\n");
console.log(`Synced ${registry.version}: ${registry.rules.length} rules`);
