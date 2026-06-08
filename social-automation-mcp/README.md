# social-automation-mcp

MCP server for social media automation, built with Node.js and TypeScript.

---

## Installation

```bash
cd social-automation-mcp
npm install
```

---

## Build and run

**Compile TypeScript:**
```bash
npm run build
```

**Start the compiled server:**
```bash
npm start
```

**Run in dev mode (without compiling):**
```bash
npm run dev
```

---

## Register in Claude Desktop

Edit the Claude Desktop config file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "social-automation": {
      "command": "node",
      "args": ["/absolute/path/to/social-mcps/social-automation-mcp/build/index.js"]
    }
  }
}
```

On Windows:
```json
{
  "mcpServers": {
    "social-automation": {
      "command": "node",
      "args": ["C:/Users/TuUsuario/social-mcps/social-automation-mcp/build/index.js"]
    }
  }
}
```

Run `npm run build` before starting Claude Desktop.

---

## Project structure

```
social-automation-mcp/
├── src/
│   ├── index.ts        ← MCP server entry point
│   └── tools/          ← one file per tool
├── build/              ← compiled output (gitignored)
├── package.json
├── tsconfig.json
└── .gitignore
```
