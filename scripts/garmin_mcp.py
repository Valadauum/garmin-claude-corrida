"""Cliente mínimo do servidor MCP garmin-personal-mcp (stdio).

Serve para chamar as ferramentas do Garmin fora do Claude, em scripts.
Requer a chave já salva com `uvx garmin-personal-mcp auth`.

Uso como linha de comando:
    python garmin_mcp.py tools
    python garmin_mcp.py call garmin_get_day '{"date": "2026-11-05"}'
    python garmin_mcp.py call garmin_search_activities '{"start": "2026-01-01", "limit": 100}' -o atividades.json

Uso como módulo:
    from garmin_mcp import GarminMCP
    with GarminMCP() as g:
        dia = g.call_json("garmin_get_day", {})
"""
import argparse
import json
import subprocess
import sys


class GarminMCP:
    def __init__(self, command=("uvx", "garmin-personal-mcp")):
        self.command = list(command)
        self._id = 0
        self.proc = None

    def __enter__(self):
        self.proc = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "garmin-claude-corrida", "version": "1"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self

    def __exit__(self, *exc):
        if self.proc:
            self.proc.stdin.close()
            self.proc.terminate()

    def _send(self, msg):
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def _rpc(self, method, params=None):
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}})
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("o servidor fechou a conexão; confira `uvx garmin-personal-mcp auth --check`")
            msg = json.loads(line)
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg["result"]

    def tools(self):
        return self._rpc("tools/list")["tools"]

    def call(self, tool, args=None):
        """Devolve o texto da resposta. Levanta RuntimeError se a ferramenta falhar."""
        res = self._rpc("tools/call", {"name": tool, "arguments": args or {}})
        text = "\n".join(c.get("text", "") for c in res.get("content", []))
        if res.get("isError"):
            raise RuntimeError(text)
        return text

    def call_json(self, tool, args=None):
        return json.loads(self.call(tool, args))

    def all_activities(self, start, end, page=100, **filters):
        """Pagina garmin_search_activities (limit alto dá HTTP 500 no Garmin)."""
        out, offset = [], 0
        while True:
            res = self.call_json("garmin_search_activities",
                                 dict(start=start, end=end, limit=page, offset=offset, **filters)).get("results", [])
            out += res
            if len(res) < page:
                return out
            offset += page


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tools", help="lista as ferramentas e parâmetros")
    c = sub.add_parser("call", help="chama uma ferramenta")
    c.add_argument("tool")
    c.add_argument("args", nargs="?", default="{}", help="argumentos em JSON")
    c.add_argument("-o", "--out", help="salva a resposta neste arquivo")
    a = ap.parse_args()
    with GarminMCP() as g:
        if a.cmd == "tools":
            for t in g.tools():
                props = t.get("inputSchema", {}).get("properties", {})
                print(f"{t['name']}({', '.join(props)})")
        else:
            text = g.call(a.tool, json.loads(a.args))
            if a.out:
                with open(a.out, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"salvo em {a.out} ({len(text)} caracteres)")
            else:
                sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
