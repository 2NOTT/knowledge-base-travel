import asyncio
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from config.bailian_mcp_config import mcp_config
from processor.query_processor.nodes.node_web_search_mcp import NodeWebSearchMcp


class MCPCompatibilityTests(unittest.TestCase):
    def test_search_uses_legacy_mcp_initialization(self):
        methods = []

        class SearchServer(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                self.send_response(405)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                method = request["method"]
                methods.append(method)
                if method == "notifications/initialized":
                    self.send_response(202)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if method == "initialize":
                    result = {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "course-search", "version": "1.0"},
                    }
                elif method == "tools/list":
                    result = {"tools": [{
                        "name": "bailian_web_search",
                        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
                    }]}
                elif method == "tools/call":
                    result = {"content": [{"type": "text", "text": json.dumps({"pages": [
                        {"title": "Travel source", "url": "https://example.com/travel", "snippet": "Source content"}
                    ]})}]}
                else:
                    self.send_response(500)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                body = json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        with ThreadingHTTPServer(("127.0.0.1", 0), SearchServer) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with (
                    patch.object(mcp_config, "mcp_base_url", f"http://127.0.0.1:{server.server_port}/mcp"),
                    patch.object(mcp_config, "api_key", "test-key"),
                ):
                    result = asyncio.run(NodeWebSearchMcp()._mcp_call("travel"))
                self.assertEqual(methods[0], "initialize")
                self.assertEqual(NodeWebSearchMcp._parse_result(result)[0]["title"], "Travel source")
            finally:
                server.shutdown()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
