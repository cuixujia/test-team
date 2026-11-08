import path from "path"
import { tool } from "@opencode-ai/plugin"

export default tool({
  description:
    "展示一份 markdown 文件供用户查看。入参必须是已存在文件的绝对路径，返回其路径信息。只读、无副作用，不校验文件内容。",
  args: {
    path: tool.schema
      .string()
      .describe("markdown 文件的绝对路径，必须以 / 开头，扩展名为 .md"),
  },
  async execute(args) {
    const raw = args.path.trim()

    if (!raw.startsWith("/")) {
      return {
        title: "show_markdown",
        output: JSON.stringify({
          ok: false,
          error: "INVALID_PATH",
          message: `path 必须是绝对路径（以 / 开头），收到：${raw}`,
        }),
      }
    }

    const ext = path.extname(raw).toLowerCase()
    if (ext !== ".md" && ext !== ".markdown") {
      return {
        title: "show_markdown",
        output: JSON.stringify({
          ok: false,
          error: "INVALID_EXTENSION",
          message: `只接受 .md 文件，收到：${raw}`,
        }),
      }
    }

    let resolved = ""
    try {
      resolved = path.resolve(raw)
      const f = Bun.file(resolved)
      if (!(await f.exists())) {
        return {
          title: "show_markdown",
          output: JSON.stringify({
            ok: false,
            error: "FILE_NOT_FOUND",
            message: `文件不存在：${resolved}（若为 table 未生成，请先确认 export 是否成功）`,
          }),
        }
      }
      const stat = await f.stat()
      return {
        title: path.basename(resolved),
        output: JSON.stringify({
          schemaVersion: 1,
          ok: true,
          path: resolved,
          display_name: path.basename(resolved),
          size_bytes: stat?.size ?? null,
          modified_time: stat?.mtime ? new Date(stat.mtime).toISOString() : null,
        }),
      }
    } catch (e) {
      return {
        title: "show_markdown",
        output: JSON.stringify({
          ok: false,
          error: "ACCESS_FAILED",
          message: `读取文件信息失败：${resolved}（${e instanceof Error ? e.message : String(e)}）`,
        }),
      }
    }
  },
})
