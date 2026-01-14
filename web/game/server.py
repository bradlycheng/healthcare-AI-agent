#!/usr/bin/env python3
"""
HTTP Server with CORS headers for Godot 4 HTML5 exports
Run with: python server.py
Then open: http://localhost:8000
"""
import http.server
import socketserver
import gzip
import os

PORT = 8000

class GzipHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    # Files to compress on-the-fly
    COMPRESS_EXTENSIONS = {'.wasm', '.js', '.pck', '.json'}
    
    def end_headers(self):
        self.send_my_headers()
        super().end_headers()

    def send_my_headers(self):
        # Required headers for Godot 4 WebAssembly
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
    
    def do_GET(self):
        # Check if client accepts gzip encoding
        accept_encoding = self.headers.get('Accept-Encoding', '')
        path = self.translate_path(self.path)
        
        # Only compress if file exists and has compressible extension
        should_compress = (
            'gzip' in accept_encoding and
            os.path.isfile(path) and
            any(path.endswith(ext) for ext in self.COMPRESS_EXTENSIONS)
        )
        
        if should_compress:
            try:
                # Read original file
                with open(path, 'rb') as f:
                    content = f.read()
                
                # Compress content
                compressed = gzip.compress(content, compresslevel=6)
                
                # Send response with compressed content
                self.send_response(200)
                self.send_header('Content-Type', self.guess_type(path))
                self.send_header('Content-Encoding', 'gzip')
                self.send_header('Content-Length', str(len(compressed)))
                self.end_headers()
                self.wfile.write(compressed)
                
                # Log compression ratio
                ratio = (1 - len(compressed) / len(content)) * 100
                print(f"Served {os.path.basename(path)}: {len(content):,} → {len(compressed):,} bytes ({ratio:.1f}% smaller)")
                return
            except Exception as e:
                print(f"Gzip error for {path}: {e}")
                # Fall back to standard handler if compression fails
        
        # Use default handler for non-compressed files
        super().do_GET()

if __name__ == '__main__':
    with socketserver.TCPServer(("", PORT), GzipHTTPRequestHandler) as httpd:
        print("=" * 40)
        print("ChaseMan Server Running!")
        print(f"Open your browser to: http://localhost:{PORT}")
        print("Gzip compression: ENABLED (for .wasm, .js, .pck, .json)")
        print("Press Ctrl+C to stop the server")
        print("=" * 40)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
