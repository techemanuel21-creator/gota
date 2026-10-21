"""A tiny MCP server over stdio for the tests: tools `eco` (read-only) and `apagar` (changes things)."""
import json, sys
TOOLS = [{"name": "eco", "description": "devolve o texto", "inputSchema": {"type": "object"}, "annotations": {"readOnlyHint": True}},
         {"name": "apagar", "description": "apaga algo", "inputSchema": {"type": "object"}}]
for line in sys.stdin:
    msg = json.loads(line)
    rid, method = msg.get("id"), msg.get("method")
    if rid is None:
        continue
    if method == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake", "version": "0"}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        p = msg["params"]
        result = {"content": [{"type": "text", "text": f"{p['name']}: {json.dumps(p.get('arguments'))}"}]}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"message": "método desconhecido"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}), flush=True)