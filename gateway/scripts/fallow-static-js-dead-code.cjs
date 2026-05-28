#!/usr/bin/env node
/**
 * Runs `fallow dead-code` with `--file` for each non-deprecated `.js` under
 * `sds_gateway/static/js/` so reported issues are limited to that tree while
 * the full project graph (webpack + templates) still resolves usage.
 */
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const base = path.join(root, "sds_gateway/static/js");
const deprecated = path.join(base, "deprecated") + path.sep;

function walk(dir, out) {
	for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
		const p = path.join(dir, ent.name);
		if (p.startsWith(deprecated)) continue;
		if (ent.isDirectory()) walk(p, out);
		else if (p.endsWith(".js")) out.push(path.relative(root, p));
	}
}

const files = [];
walk(base, files);
const args = ["dead-code"];
for (const f of files) {
	args.push("--file", f);
}
const bin = path.join(root, "node_modules", ".bin", "fallow");
const r = spawnSync(bin, args, { cwd: root, stdio: "inherit" });
process.exit(r.status === null ? 1 : r.status);
