import fs from "node:fs";
import path from "node:path";

const root = process.env.OPENCLAW_PACKAGE_ROOT;
if (!root) throw new Error("OPENCLAW_PACKAGE_ROOT is required");
const dist = path.join(root, "dist");
const key = 'Symbol.for("openclaw.detachedCronTimerContext")';

function rewrite(file, edits) {
  let source = fs.readFileSync(file, "utf8");
  for (const [from, to, label] of edits) {
    if (source.split(from).length !== 2) throw new Error(`${label} contract changed in ${path.basename(file)}`);
    source = source.replace(from, to);
  }
  fs.writeFileSync(file, source);
}

const entry = path.join(dist, "index.js");
const entryAnchor = 'import process from "node:process";\n';
rewrite(entry, [
  [
    entryAnchor,
    entryAnchor +
      'import { AsyncResource as OpenClawDetachedAsyncResource } from "node:async_hooks";\n' +
      `globalThis[${key}] ??= new OpenClawDetachedAsyncResource("openclaw.detached-cron-timer");\n`,
    "entry process import",
  ],
]);

const owners = fs
  .readdirSync(dist, { withFileTypes: true })
  .filter((item) => item.isFile() && item.name.endsWith(".mjs"))
  .map((item) => path.join(dist, item.name))
  .filter((file) => fs.readFileSync(file, "utf8").includes("function setCronTimer(state, delayMs) {"));
if (owners.length !== 1) throw new Error(`expected one cron timer module, found ${owners.length}`);

const detached = (run) => `(globalThis[${key}] ? globalThis[${key}].runInAsyncScope(${run}) : runOutsideGatewayRootWorkAdmission(${run}))`;
rewrite(owners[0], [
  [
    "\tstate.timer = setTimeout(() => {\n\t\trunOutsideGatewayRootWorkAdmission(() => {\n\t\t\tonTimer(state).catch((err) => {\n\t\t\t\tstate.deps.log.error({ err: String(err) }, \"cron: timer tick failed\");\n\t\t\t});\n\t\t});\n\t}, delayMs);",
    `\tstate.timer = setTimeout(() => {\n\t\t${detached('() => {\n\t\t\tonTimer(state).catch((err) => {\n\t\t\t\tstate.deps.log.error({ err: String(err) }, "cron: timer tick failed");\n\t\t\t});\n\t\t}')};\n\t}, delayMs);`,
    "cron timer",
  ],
  [
    "return runOutsideGatewayRootWorkAdmission(() => requestImmediateCronRecheck(state));",
    `return ${detached("() => requestImmediateCronRecheck(state)")};`,
    "cron recheck",
  ],
]);
console.log(`detached cron timer context in ${path.basename(owners[0])}`);
