import { homedir } from "node:os"
import { isAbsolute, resolve } from "node:path"
import { Plugin } from "@opencode/plugin"

const searches = new Set(["grep", "glob"])

const target = (base: string, value: unknown) => {
  const path = typeof value === "string" && value !== "" ? value : "."
  if (path === "~") return homedir()
  if (path.startsWith("~/")) return resolve(homedir(), path.slice(2))
  return isAbsolute(path) ? resolve(path) : resolve(base, path)
}

export default Plugin.define({
  id: "meeting-notes-guard",
  async setup(ctx) {
    await ctx.tool.hook("execute.before", async (event) => {
      if (!searches.has(event.tool)) return
      const input = event.input && typeof event.input === "object" ? (event.input as Record<string, unknown>) : {}
      await ctx.permission.assert({
        sessionID: event.sessionID,
        agent: event.agent,
        source: { type: "tool", messageID: event.messageID, id: event.id },
        action: "read",
        resources: [target(ctx.location.directory, input.path)],
      })
    })
  },
})
